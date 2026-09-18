"""End-to-end paper flow: proposal → risc → aprobare → ordin → audit. Zero rețea."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from src.audit.audit_log import AuditLog
from src.data.sources import Bar, CsvBarDataSource
from src.engine.paper_config import load_paper_trading_config
from src.engine.portfolio_tracker import PortfolioTracker
from src.engine.proposal_types import ParsedProposal, ProposalContext, RejectedProposal
from src.engine.strategy_paper import PaperTradingLoop
from src.execution.broker import SimulatedBroker
from src.execution.human_approval import ApprovalGate, ScriptedApprovalOperator
from src.execution.idempotency_store import IdempotencyStore
from src.execution.order_gateway import OrderGateway
from src.execution.reconciliation import Reconciliation
from src.monitor.heartbeat import Heartbeat
from src.monitor.watchdog import Watchdog
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.config_schema import load_risk_limits
from src.risk.kill_switch import KillSwitch
from src.risk.portfolio_state import load_instrument_rules
from src.risk.risk_engine import RiskEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"


class FixedProposalClient:
    def __init__(self, direction: str = "long") -> None:
        self._direction = direction

    def request_proposal(
        self,
        context: ProposalContext,
        timeout_s: float | None = None,  # noqa: ARG002
    ) -> ParsedProposal | RejectedProposal:
        return ParsedProposal(
            instrument=context.instrument,
            direction=self._direction,  # type: ignore[arg-type]
            confidence=0.8,
            rationale="integration fixture",
        )


def _bars() -> list[Bar]:
    return CsvBarDataSource(FIXTURE).fetch_bars(
        "ETHUSD",
        datetime(2024, 11, 1, tzinfo=timezone.utc),
        datetime(2024, 12, 16, tzinfo=timezone.utc),
        "1d",
    )


def build_loop(
    tmp_path: Path,
    *,
    client: object | None = None,
    broker: SimulatedBroker | None = None,
    approved: bool = True,
) -> tuple[PaperTradingLoop, AuditLog, SimulatedBroker, KillSwitch]:
    config = load_paper_trading_config(REPO_ROOT / "config" / "paper_trading.yaml")
    halt = KillSwitch(tmp_path / "halt.flag")
    limits = load_risk_limits(REPO_ROOT / "config" / "risk_limits.yaml")
    rules, classes = load_instrument_rules(REPO_ROOT / "config" / "universe.yaml")
    risk = RiskEngine(limits, rules, classes, halt)
    breaker = CircuitBreaker(limits.circuit_breaker, halt)
    tracker = PortfolioTracker(config.starting_cash, config.instrument, "crypto")
    sim = broker if broker is not None else SimulatedBroker()
    gateway = OrderGateway(IdempotencyStore(tmp_path / "idemp.sqlite"), sim)
    audit = AuditLog(tmp_path / "audit.sqlite")
    last_bar = tmp_path / "last_bar.json"
    recon_path = tmp_path / "recon.json"
    watchdog = Watchdog(kill_switch=halt, last_bar_path=last_bar, reconciliation_path=recon_path)
    loop = PaperTradingLoop(
        config=config,
        risk_engine=risk,
        circuit_breaker=breaker,
        kill_switch=halt,
        proposal_client=client or FixedProposalClient("long"),
        tracker=tracker,
        gateway=gateway,
        broker=sim,
        approval_gate=ApprovalGate(
            tmp_path / "approvals",
            timeout_s=1.0,
            poll_interval_s=0.01,
            operator=ScriptedApprovalOperator(approved=approved),
        ),
        audit=audit,
        heartbeat=Heartbeat(tmp_path / "hb.json"),
        watchdog=watchdog,
        reconciliation=Reconciliation(recon_path),
        last_bar_path=last_bar,
        local_state_path=tmp_path / "local.json",
    )
    return loop, audit, sim, halt


def test_proposal_risk_approval_order_audit(tmp_path: Path) -> None:
    loop, audit, broker, halt = build_loop(tmp_path)
    bars = _bars()
    result = loop.run_bars(bars, max_sessions=1)
    assert len(result.sessions) == 1
    session = result.sessions[0]
    assert session.proposal_direction == "long"
    assert session.risk_approved is True
    assert session.human_approved is True
    assert session.order_status == "filled"
    assert session.halted is False
    assert halt.is_active() is False
    types = [event.event_type for event in audit.list_events()]
    assert "reconciliation_ok" in types
    assert "proposal" in types
    assert "risk_decision" in types
    assert "human_approval" in types
    assert "order_submitted" in types
    assert "fill" in types
    assert broker.snapshot().positions["ETHUSD"] > 0
    ids = {event.correlation_id for event in audit.list_events() if event.event_type == "proposal"}
    assert session.correlation_id in ids
    assert isinstance(session.correlation_id, UUID)


def test_human_reject_does_not_submit(tmp_path: Path) -> None:
    loop, audit, broker, _halt = build_loop(tmp_path, approved=False)
    result = loop.run_bars(_bars(), max_sessions=1)
    assert result.sessions[0].human_approved is False
    assert result.sessions[0].order_status is None
    assert "ETHUSD" not in broker.snapshot().positions or broker.snapshot().positions["ETHUSD"] == 0
    types = [event.event_type for event in audit.list_events()]
    assert "order_submitted" not in types
    assert "human_approval" in types


def test_avoid_never_reaches_gateway(tmp_path: Path) -> None:
    loop, audit, broker, _halt = build_loop(tmp_path, client=FixedProposalClient("avoid"))
    result = loop.run_bars(_bars(), max_sessions=1)
    assert result.sessions[0].risk_approved is False
    assert result.sessions[0].order_status is None
    types = [event.event_type for event in audit.list_events()]
    assert "order_submitted" not in types
    assert "human_approval" not in types
