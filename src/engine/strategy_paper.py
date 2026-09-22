"""Paper trading loop — Faza 5. Nu modifică calea de backtest.

Flux: bar → llm_client → risk → audit → approval → order_gateway → audit.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent
from src.data.sources import Bar
from src.engine.paper_config import PaperTradingConfig
from src.engine.portfolio_tracker import PortfolioTracker
from src.engine.proposal_cache import ProposalClient
from src.engine.proposal_types import ParsedProposal, RejectedProposal
from src.engine.signals import proposal_context_at
from src.execution.broker import BrokerClient, BrokerState, SimulatedBroker
from src.execution.human_approval import ApprovalGate
from src.execution.order_gateway import OrderGateway
from src.execution.reconciliation import LocalPortfolioSnapshot, Reconciliation
from src.execution.safety import HaltAndFlatten, PeriodicReconciler
from src.execution.types import OrderRequest, OrderResult
from src.monitor.heartbeat import Heartbeat
from src.monitor.watchdog import Watchdog
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.kill_switch import KillSwitch
from src.runtime_io import write_text_atomic
from src.risk.risk_engine import RiskEngine

if TYPE_CHECKING:
    from src.execution.postgres_store import PostgresPortfolioStore


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
        broker_state_path: Path | None = None,
        tracker_state_path: Path | None = None,
        postgres_portfolio: "PostgresPortfolioStore | None" = None,
        cash_asset: str = "USD",
        strategy_version_id: UUID | None = None,
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
        self._broker_state_path = broker_state_path or local_state_path.with_name(
            "simulated_broker.json"
        )
        self._tracker_state_path = tracker_state_path or local_state_path.with_name(
            "paper_tracker.json"
        )
        self._process_id = process_id
        self._postgres = postgres_portfolio
        self._cash_asset = cash_asset
        self._strategy_version_id = strategy_version_id
        self._history: list[Bar] = []
        self._in_flight: list[str] = []
        self._last_price: Decimal | None = None
        self._flatten = HaltAndFlatten(watchdog, gateway.cancel_all)
        self._periodic = PeriodicReconciler(reconciliation, self._flatten)

    def restore_persisted_state(self) -> None:
        if self._tracker_state_path.is_file():
            raw = json.loads(self._tracker_state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._tracker.restore(raw)
        if isinstance(self._broker, SimulatedBroker) and self._broker_state_path.is_file():
            restored = BrokerState.model_validate_json(
                self._broker_state_path.read_text(encoding="utf-8")
            )
            self._broker.restore(restored)
            if restored.last_price:
                self._last_price = next(iter(restored.last_price.values()))
        if self._local_state_path.is_file():
            snap = LocalPortfolioSnapshot.model_validate_json(
                self._local_state_path.read_text(encoding="utf-8")
            )
            self._in_flight = list(snap.pending_client_order_ids)

    def seed_history(self, bars: list[Bar]) -> None:
        """Warm lookback without proposals or orders."""
        seen = {bar.timestamp for bar in self._history}
        for bar in bars:
            if bar.timestamp in seen:
                continue
            self._history.append(bar)
            seen.add(bar.timestamp)
            self._last_price = bar.close
            self._tracker.on_bar(bar.timestamp, bar.close, volume=bar.volume)
            if isinstance(self._broker, SimulatedBroker):
                self._broker.set_last_price(bar.instrument, bar.close)
        if bars:
            self._write_last_bar(bars[-1])
            self._persist_local_state()

    def run_stream(
        self,
        poll_bars: Callable[[datetime | None], list[Bar]],
        *,
        poll_interval_s: float = 30.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        should_stop: Callable[[], bool] | None = None,
        max_polls: int | None = None,
    ) -> PaperRunResult:
        """Poll closed bars until stop/HALT. Does not cap at session_count_target."""
        self.restore_persisted_state()
        self.reconcile_startup()
        result = PaperRunResult()
        last_ts = self._last_processed_bar_ts()
        polls = 0
        while True:
            if should_stop is not None and should_stop():
                break
            if self._kill.is_active():
                break
            self._heartbeat.write(self._process_id)
            polls += 1
            try:
                bars = sorted(poll_bars(last_ts), key=lambda item: item.timestamp)
            except Exception:
                if max_polls is not None and polls >= max_polls:
                    break
                sleep_fn(poll_interval_s)
                continue
            if last_ts is None:
                if bars:
                    self.seed_history(bars)
                    last_ts = bars[-1].timestamp
            else:
                for bar in bars:
                    if bar.timestamp <= last_ts:
                        self._ensure_history(bar)
                        continue
                    try:
                        record = self.run_bar(bar)
                    except Exception as exc:  # noqa: BLE001 - fail-closed, not fail-crash
                        correlation = uuid4()
                        self._audit.record(
                            AuditEvent.now(
                                correlation_id=correlation,
                                event_type="run_bar_error",
                                payload={"error": repr(exc), "bar_timestamp": bar.timestamp.isoformat()},
                            )
                        )
                        self._record_halt(correlation, "run_bar_error")
                        last_ts = bar.timestamp
                        break
                    last_ts = bar.timestamp
                    if record is not None:
                        result.sessions.append(record)
                    if self._kill.is_active():
                        break
            if max_polls is not None and polls >= max_polls:
                break
            if should_stop is not None and should_stop():
                break
            if self._kill.is_active():
                break
            sleep_fn(poll_interval_s)
        return result

    def _ensure_history(self, bar: Bar) -> None:
        if any(existing.timestamp == bar.timestamp for existing in self._history):
            return
        self._history.append(bar)
        self._history.sort(key=lambda item: item.timestamp)
        self._last_price = bar.close
        self._tracker.on_bar(bar.timestamp, bar.close, volume=bar.volume)
        if isinstance(self._broker, SimulatedBroker):
            self._broker.set_last_price(bar.instrument, bar.close)

    def _last_processed_bar_ts(self) -> datetime | None:
        if not self._last_bar_path.is_file():
            return None
        try:
            raw = json.loads(self._last_bar_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict) or not raw.get("bar_timestamp"):
            return None
        moment = datetime.fromisoformat(str(raw["bar_timestamp"]).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc)

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
        self._tracker.on_bar(bar.timestamp, bar.close, volume=bar.volume)
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
        if self._postgres is not None:
            self._postgres.record_signal(
                proposal, strategy_version_id=self._strategy_version_id
            )
        portfolio_state = self._tracker.snapshot(bar.close)
        decision = self._risk.evaluate(proposal, portfolio_state)
        self._audit.record(
            AuditEvent.now(
                correlation_id=correlation,
                event_type="risk_decision",
                payload=_payload(decision),
            )
        )
        if self._postgres is not None:
            self._postgres.record_risk_event(
                decision,
                portfolio_state=portfolio_state,
                correlation_id=correlation,
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
        result = self._gateway.submit(order, correlation_id=correlation)
        self._audit.record(
            AuditEvent.now(
                correlation_id=correlation,
                event_type="order_submitted",
                payload=_payload(result),
            )
        )
        # human_approvals.order_id links only when EXECUTION_STORE_BACKEND=postgres
        # too — that backend is what inserts the `orders` row `order_id` references
        # (PostgresIdempotencyStore.reserve keys orders.order_id = correlation_id).
        # On the files/rollback execution path there is no `orders` row to link to,
        # so this stays a no-op rather than fabricating a foreign key target.
        if self._postgres is not None and self._approval.approval_store is not None:
            self._approval.approval_store.link_order(
                correlation_id=correlation, order_id=correlation
            )
        record.order_status = result.status
        self._apply_order_result(correlation, decision.side, result, bar.timestamp)
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

    def _apply_order_result(
        self, correlation: UUID, side: str, result: OrderResult, bar_timestamp: datetime
    ) -> None:
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
                    commission=result.fee,
                    timestamp=bar_timestamp,
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
        if self._postgres is not None:
            price = self._last_price if self._last_price is not None else Decimal("1")
            self._postgres.record_halt_event(
                reason, portfolio_state=self._tracker.snapshot(price), correlation_id=correlation
            )
        self._in_flight.clear()

    def _write_last_bar(self, bar: Bar) -> None:
        write_text_atomic(
            self._last_bar_path,
            json.dumps(
                {
                    "instrument": bar.instrument,
                    "bar_timestamp": bar.timestamp.isoformat(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "close": str(bar.close),
                }
            ),
        )

    def _local_snapshot(self) -> LocalPortfolioSnapshot:
        price = self._last_price if self._last_price is not None else Decimal("1")
        state = self._tracker.snapshot(price)
        return LocalPortfolioSnapshot(
            positions=dict(state.open_quantity),
            pending_client_order_ids=list(self._in_flight),
        )

    def _persist_local_state(self) -> None:
        write_text_atomic(self._local_state_path, self._local_snapshot().model_dump_json())
        if isinstance(self._broker, SimulatedBroker):
            write_text_atomic(
                self._broker_state_path,
                self._broker.snapshot().model_dump_json(),
            )
        write_text_atomic(
            self._tracker_state_path,
            json.dumps(self._tracker.dump_state()),
        )
        if self._postgres is not None:
            self._persist_postgres_snapshot()

    def _persist_postgres_snapshot(self) -> None:
        """Same fields as the JSON files above, written to `balances`/`positions`
        instead (design §8.4). Always additive — the JSON files above are the
        rollback path and are written unconditionally regardless of backend."""
        assert self._postgres is not None
        price = self._last_price if self._last_price is not None else Decimal("1")
        state = self._tracker.dump_state()
        broker_qty = None
        if isinstance(self._broker, SimulatedBroker):
            broker_qty = self._broker.snapshot().positions.get(self._config.instrument)
        self._postgres.persist_snapshot(
            instrument=self._config.instrument,
            cash_asset=self._cash_asset,
            cash=Decimal(str(state["cash"])),
            open_quantity=Decimal(str(state["open_qty"])),
            avg_entry_price=Decimal(str(state["avg_price"])),
            last_price=price,
            broker_open_quantity=broker_qty,
        )
