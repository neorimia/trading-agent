"""Paper trading loop — Faza 5. Nu modifică calea de backtest.

Flux: bar → llm_client → risk → audit → approval → order_gateway → audit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent
from src.data.sources import Bar
from src.engine.paper_config import PaperTradingConfig
from src.engine.portfolio_tracker import PortfolioTracker
from src.engine.proposal_cache import ProposalClient
from src.engine.proposal_types import ParsedProposal, RejectedProposal
from src.engine.signals import proposal_context_at
from src.execution.broker import BrokerClient, SimulatedBroker
from src.execution.human_approval import ApprovalGate
from src.execution.order_gateway import OrderGateway
from src.execution.reconciliation import LocalPortfolioSnapshot, Reconciliation
from src.execution.safety import HaltAndFlatten, PeriodicReconciler
from src.execution.types import OrderRequest, OrderResult
from src.monitor.heartbeat import Heartbeat
from src.monitor.watchdog import Watchdog
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.kill_switch import KillSwitch
from src.risk.risk_engine import RiskEngine


def _payload(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        dumped = model.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if isinstance(model, dict):
        return model
    return {"value": str(model)}


@dataclass
class SessionRecord:
    session_index: int
    correlation_id: UUID
    bar_timestamp: datetime
    instrument: str
    proposal_direction: str | None
    rejected_reason: str | None
    risk_approved: bool | None
    human_approved: bool | None
    order_status: str | None
    halted: bool
    notes: str = ""


@dataclass
class PaperRunResult:
    sessions: list[SessionRecord] = field(default_factory=list)
    restart_reconciled: bool | None = None


class PaperTradingLoop:
    def __init__(
        self,
        *,
        config: PaperTradingConfig,
        risk_engine: RiskEngine,
        circuit_breaker: CircuitBreaker,
        kill_switch: KillSwitch,
        proposal_client: ProposalClient,
        tracker: PortfolioTracker,
        gateway: OrderGateway,
        broker: BrokerClient,
        approval_gate: ApprovalGate,
        audit: AuditLog,
        heartbeat: Heartbeat,
        watchdog: Watchdog,
        reconciliation: Reconciliation,
        last_bar_path: Path,
        local_state_path: Path,
        process_id: str = "paper-engine",
    ) -> None:
        self._config = config
        self._risk = risk_engine
        self._breaker = circuit_breaker
        self._kill = kill_switch
        self._proposals = proposal_client
        self._tracker = tracker
        self._gateway = gateway
        self._broker = broker
        self._approval = approval_gate
        self._audit = audit
        self._heartbeat = heartbeat
        self._watchdog = watchdog
        self._reconciliation = reconciliation
        self._last_bar_path = last_bar_path
        self._local_state_path = local_state_path
        self._process_id = process_id
        self._history: list[Bar] = []
        self._in_flight: list[str] = []
        self._last_price: Decimal | None = None
        self._flatten = HaltAndFlatten(watchdog, gateway.cancel_all)
        self._periodic = PeriodicReconciler(reconciliation, self._flatten)

    def reconcile_startup(self) -> None:
        report = self._periodic.run(
            self._local_snapshot(),
            self._broker.snapshot(),
        )
        correlation = uuid4()
        event_type = "reconciliation_ok" if report.matched else "reconciliation_mismatch"
        self._audit.record(
            AuditEvent.now(
                correlation_id=correlation,
                event_type=event_type,
                payload=_payload(report),
            )
        )
        if not report.matched:
            self._record_halt(correlation, "reconciliation_mismatch")

    def run_bars(self, bars: list[Bar], *, max_sessions: int | None = None) -> PaperRunResult:
        self.reconcile_startup()
        result = PaperRunResult()
        target = max_sessions if max_sessions is not None else self._config.session_count_target
        for bar in bars:
            if len(result.sessions) >= target:
                break
            record = self.run_bar(bar)
            if record is not None:
                result.sessions.append(record)
            if self._kill.is_active():
                break
        return result

    def run_bar(self, bar: Bar) -> SessionRecord | None:
        self._heartbeat.write(self._process_id)
        self._history.append(bar)
        self._last_price = bar.close
        self._tracker.on_bar(bar.timestamp, bar.close)
        if isinstance(self._broker, SimulatedBroker):
            self._broker.set_last_price(bar.instrument, bar.close)
        self._write_last_bar(bar)
        self._persist_local_state()

        drift = self._periodic.run(self._local_snapshot(), self._broker.snapshot())
        if not drift.matched:
            correlation = uuid4()
            self._audit.record(
                AuditEvent.now(
                    correlation_id=correlation,
                    event_type="reconciliation_mismatch",
                    payload=_payload(drift),
                )
            )
            self._record_halt(correlation, "reconciliation_mismatch")
            return SessionRecord(
                session_index=len(self._history),
                correlation_id=correlation,
                bar_timestamp=bar.timestamp,
                instrument=bar.instrument,
                proposal_direction=None,
                rejected_reason=None,
                risk_approved=None,
                human_approved=None,
                order_status=None,
                halted=True,
                notes="reconciliation_mismatch",
            )

        if self._watchdog.check_stale_data(self._config.stale_data_threshold_s):
            correlation = uuid4()
            self._halt(correlation, "stale_data")
            return SessionRecord(
                session_index=len(self._history),
                correlation_id=correlation,
                bar_timestamp=bar.timestamp,
                instrument=bar.instrument,
                proposal_direction=None,
                rejected_reason=None,
                risk_approved=None,
                human_approved=None,
                order_status=None,
                halted=True,
                notes="stale_data",
            )
        if len(self._history) < self._config.lookback_bars:
            return None

        correlation = uuid4()
        if self._kill.is_active() or self._breaker.state == "HALTED":
            return SessionRecord(
                session_index=len(self._history),
                correlation_id=correlation,
                bar_timestamp=bar.timestamp,
                instrument=bar.instrument,
                proposal_direction=None,
                rejected_reason="halted",
                risk_approved=False,
                human_approved=None,
                order_status=None,
                halted=True,
                notes="halted",
            )

        context = proposal_context_at(
            self._history,
            fast_period=self._config.fast_ema_period,
            slow_period=self._config.slow_ema_period,
            lookback=self._config.lookback_bars,
        )
        proposal = self._proposals.request_proposal(context)
        if isinstance(proposal, RejectedProposal):
            self._audit.record(
                AuditEvent.now(
                    correlation_id=correlation,
                    event_type="rejected_proposal",
                    payload=_payload(proposal),
                )
            )
            return SessionRecord(
                session_index=len(self._history),
                correlation_id=correlation,
                bar_timestamp=bar.timestamp,
                instrument=bar.instrument,
                proposal_direction=None,
                rejected_reason=proposal.reason,
                risk_approved=None,
                human_approved=None,
                order_status=None,
                halted=False,
            )
        if not isinstance(proposal, ParsedProposal):
            return None

        self._audit.record(
            AuditEvent.now(
                correlation_id=correlation,
                event_type="proposal",
                payload=_payload(proposal),
            )
        )
        decision = self._risk.evaluate(proposal, self._tracker.snapshot(bar.close))
        self._audit.record(
            AuditEvent.now(
                correlation_id=correlation,
                event_type="risk_decision",
                payload=_payload(decision),
            )
        )
        record = SessionRecord(
            session_index=len(self._history),
            correlation_id=correlation,
            bar_timestamp=bar.timestamp,
            instrument=bar.instrument,
            proposal_direction=proposal.direction,
            rejected_reason=decision.reject_reason,
            risk_approved=decision.approved,
            human_approved=None,
            order_status=None,
            halted=False,
        )
        if not decision.approved or decision.quantity <= 0:
            return record

        approval = self._approval.request(decision, correlation)
        self._audit.record(
            AuditEvent.now(
                correlation_id=correlation,
                event_type="human_approval",
                payload=_payload(approval),
            )
        )
        record.human_approved = approval.approved
        if not approval.approved:
            record.notes = approval.reason
            return record

        order = OrderRequest(
            client_order_id=uuid4(),
            instrument=decision.instrument,
            side=decision.side,
            quantity=decision.quantity,
            order_type="market",
        )
        result = self._gateway.submit(order)
        self._audit.record(
            AuditEvent.now(
                correlation_id=correlation,
                event_type="order_submitted",
                payload=_payload(result),
            )
        )
        record.order_status = result.status
        self._apply_order_result(correlation, decision.side, result)
        if self._kill.is_active():
            record.halted = True
        self._persist_local_state()
        report = self._periodic.run(
            self._local_snapshot(),
            self._broker.snapshot(),
        )
        if not report.matched:
            self._audit.record(
                AuditEvent.now(
                    correlation_id=correlation,
                    event_type="reconciliation_mismatch",
                    payload=_payload(report),
                )
            )
            self._record_halt(correlation, "reconciliation_mismatch")
            record.halted = True
        return record

    def _apply_order_result(self, correlation: UUID, side: str, result: OrderResult) -> None:
        order_id = str(result.client_order_id)
        if result.status in {"unknown", "timeout"}:
            if order_id not in self._in_flight:
                self._in_flight.append(order_id)
            self._breaker.record_event("unknown_result")
            self._halt(correlation, f"order_{result.status}")
            return
        if result.status == "rejected":
            self._breaker.record_event("error")
            return
        if result.status in {"filled", "partially_filled"}:
            if result.status == "partially_filled" and order_id not in self._in_flight:
                self._in_flight.append(order_id)
            elif result.status == "filled" and order_id in self._in_flight:
                self._in_flight.remove(order_id)
            if result.filled_quantity > 0 and result.fill_price is not None:
                self._tracker.record_order_submit()
                self._tracker.on_fill(
                    side=side,
                    quantity=result.filled_quantity,
                    price=result.fill_price,
                    commission=Decimal("0"),
                )
                self._audit.record(
                    AuditEvent.now(
                        correlation_id=correlation,
                        event_type="fill",
                        payload=_payload(result),
                    )
                )
            self._breaker.record_event("success")

    def _halt(self, correlation: UUID, reason: str) -> None:
        self._flatten.trigger(reason)
        self._record_halt(correlation, reason)

    def _record_halt(self, correlation: UUID, reason: str) -> None:
        if not self._kill.is_active():
            self._flatten.trigger(reason)
        self._audit.record(
            AuditEvent.now(
                correlation_id=correlation,
                event_type="halt",
                payload={"reason": reason},
            )
        )
        self._in_flight.clear()

    def _write_last_bar(self, bar: Bar) -> None:
        self._last_bar_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_bar_path.write_text(
            json.dumps(
                {
                    "instrument": bar.instrument,
                    "bar_timestamp": bar.timestamp.isoformat(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "close": str(bar.close),
                }
            ),
            encoding="utf-8",
        )

    def _local_snapshot(self) -> LocalPortfolioSnapshot:
        price = self._last_price if self._last_price is not None else Decimal("1")
        state = self._tracker.snapshot(price)
        return LocalPortfolioSnapshot(
            positions=dict(state.open_quantity),
            pending_client_order_ids=list(self._in_flight),
        )

    def _persist_local_state(self) -> None:
        self._local_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._local_state_path.write_text(
            self._local_snapshot().model_dump_json(),
            encoding="utf-8",
        )
