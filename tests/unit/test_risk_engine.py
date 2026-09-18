"""RiskEngine.evaluate — fiecare limită din risk_limits.yaml, inclusiv cazuri la prag."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from src.engine.proposal_types import ParsedProposal
from src.risk.config_schema import load_risk_limits
from src.risk.kill_switch import KillSwitch
from src.risk.portfolio_state import PortfolioState, load_instrument_rules
from src.risk.risk_engine import RiskEngine

REPO_ROOT = Path(__file__).resolve().parents[2]


def _engine(tmp_path: Path) -> RiskEngine:
    limits = load_risk_limits(REPO_ROOT / "config" / "risk_limits.yaml")
    rules, classes = load_instrument_rules(REPO_ROOT / "config" / "universe.yaml")
    return RiskEngine(limits, rules, classes, KillSwitch(tmp_path / "halt.flag"))


def _proposal(**overrides: object) -> ParsedProposal:
    payload: dict[str, object] = {
        "instrument": "AAPL",
        "direction": "long",
        "confidence": 0.5,
        "rationale": "unit test",
    }
    payload.update(overrides)
    return ParsedProposal.model_validate(payload)


def _state(**overrides: object) -> PortfolioState:
    payload: dict[str, object] = {
        "exposure_per_instrument": {"AAPL": Decimal("0")},
        "exposure_per_asset_class": {"equity": Decimal("0")},
        "daily_realized_loss": Decimal("0"),
        "current_drawdown": Decimal("0"),
        "orders_today": 0,
        "last_price": {"AAPL": Decimal("100")},
        "open_quantity": {"AAPL": Decimal("0")},
    }
    payload.update(overrides)
    return PortfolioState.model_validate(payload)


def test_long_approved_under_all_limits(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(), _state())
    assert decision.approved is True
    assert decision.side == "buy"
    assert decision.quantity == Decimal("10")
    assert decision.reject_reason is None
    assert decision.requires_human_approval is True
    assert decision.quantity * Decimal("100") == Decimal("1000")


def test_notional_at_exact_cap_is_allowed(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(), _state())
    assert decision.approved is True
    assert decision.quantity * Decimal("100") == Decimal("1000")


def test_exposure_per_instrument_at_limit_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(
        _proposal(),
        _state(exposure_per_instrument={"AAPL": Decimal("2000")}),
    )
    assert decision.approved is False
    assert decision.reject_reason == "below_min_notional_or_no_capacity"
    assert decision.quantity == Decimal("0")


def test_exposure_per_instrument_just_under_limit_is_sized_to_remaining(
    tmp_path: Path,
) -> None:
    decision = _engine(tmp_path).evaluate(
        _proposal(),
        _state(exposure_per_instrument={"AAPL": Decimal("1900")}),
    )
    assert decision.approved is True
    assert decision.quantity == Decimal("1")
    assert decision.quantity * Decimal("100") == Decimal("100")


def test_exposure_per_asset_class_at_limit_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(
        _proposal(),
        _state(exposure_per_asset_class={"equity": Decimal("5000")}),
    )
    assert decision.approved is False
    assert decision.reject_reason == "below_min_notional_or_no_capacity"


def test_daily_loss_at_threshold_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(
        _proposal(),
        _state(daily_realized_loss=Decimal("200")),
    )
    assert decision.approved is False
    assert decision.reject_reason == "max_daily_loss"


def test_daily_loss_over_threshold_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(
        _proposal(),
        _state(daily_realized_loss=Decimal("201")),
    )
    assert decision.approved is False
    assert decision.reject_reason == "max_daily_loss"


def test_drawdown_at_threshold_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(
        _proposal(),
        _state(current_drawdown=Decimal("500")),
    )
    assert decision.approved is False
    assert decision.reject_reason == "max_drawdown"


def test_orders_per_day_at_limit_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(), _state(orders_today=10))
    assert decision.approved is False
    assert decision.reject_reason == "max_orders_per_day"


def test_orders_per_day_just_under_limit_allowed(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(), _state(orders_today=9))
    assert decision.approved is True


def test_remaining_capacity_below_min_notional_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(
        _proposal(),
        _state(exposure_per_instrument={"AAPL": Decimal("1950")}),
    )
    assert decision.approved is False
    assert decision.reject_reason == "below_min_notional_or_no_capacity"


def test_unknown_instrument_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(instrument="NVDA"), _state())
    assert decision.approved is False
    assert decision.reject_reason == "instrument_not_in_universe"


def test_avoid_is_no_action(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(direction="avoid"), _state())
    assert decision.approved is False
    assert decision.reject_reason == "no_action_proposed"
    assert decision.quantity == Decimal("0")
    assert decision.side == "buy"
    assert decision.requires_human_approval is True


def test_exit_maps_to_sell_open_quantity(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(
        _proposal(direction="exit"),
        _state(open_quantity={"AAPL": Decimal("7")}),
    )
    assert decision.approved is True
    assert decision.side == "sell"
    assert decision.quantity == Decimal("7")
    assert decision.requires_human_approval is True


def test_exit_without_open_position_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(direction="exit"), _state())
    assert decision.approved is False
    assert decision.reject_reason == "no_open_position"


def test_halt_rejects_long_unconditionally(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    engine._kill_switch.trigger("manual")
    decision = engine.evaluate(_proposal(), _state())
    assert decision.approved is False
    assert decision.reject_reason == "halted"
    assert decision.requires_human_approval is True


def test_halt_rejects_exit_unconditionally(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    engine._kill_switch.trigger("manual")
    decision = engine.evaluate(
        _proposal(direction="exit"),
        _state(open_quantity={"AAPL": Decimal("4")}),
    )
    assert decision.approved is False
    assert decision.reject_reason == "halted"


def test_missing_price_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(), _state(last_price={}))
    assert decision.approved is False
    assert decision.reject_reason == "missing_price"


def test_rejected_decision_always_requires_human_approval(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(instrument="ZZZ"), _state())
    assert decision.approved is False
    assert decision.requires_human_approval is True
