"""Limitele noi (risc/trade, R:R, spread, lichiditate, expunere corelată) — nu pot fi
lărgite de conținutul propunerii sau de un `reward_risk_ratio` favorabil furnizat de
strategie. Global rămâne sursa unică de adevăr; o strategie poate doar STRÂNGE, nu lărgi.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

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
        "confidence": 0.9,
        "rationale": "adversarial",
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
        "spread_bps": {"AAPL": Decimal("5")},
        "bar_volume": {"AAPL": Decimal("100000")},
    }
    payload.update(overrides)
    return PortfolioState.model_validate(payload)


def test_missing_spread_data_rejected_not_assumed_zero(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(), _state(spread_bps={}))
    assert decision.approved is False
    assert decision.reject_reason == "stale_or_missing_market_data"


def test_spread_wider_than_limit_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(), _state(spread_bps={"AAPL": Decimal("51")}))
    assert decision.approved is False
    assert decision.reject_reason == "spread_too_wide"


def test_missing_volume_data_rejected_not_assumed_infinite(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(), _state(bar_volume={}))
    assert decision.approved is False
    assert decision.reject_reason == "stale_or_missing_market_data"


def test_volume_below_minimum_rejected(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(_proposal(), _state(bar_volume={"AAPL": Decimal("1")}))
    assert decision.approved is False
    assert decision.reject_reason == "insufficient_liquidity"


def test_a_favorable_reward_risk_ratio_cannot_bypass_notional_cap(tmp_path: Path) -> None:
    """Un raport R:R de 100:1 declarat de strategie nu poate crește cantitatea peste cap."""
    decision = _engine(tmp_path).evaluate(
        _proposal(), _state(), reward_risk_ratio=Decimal("100")
    )
    assert decision.approved is True
    assert decision.quantity * Decimal("100") <= Decimal("1000")


def test_reward_risk_below_minimum_rejected_even_with_high_confidence(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(
        _proposal(confidence=1.0), _state(), reward_risk_ratio=Decimal("0.1")
    )
    assert decision.approved is False
    assert decision.reject_reason == "reward_risk_too_low"


def test_missing_reward_risk_ratio_does_not_block_legacy_callers(tmp_path: Path) -> None:
    """EMA/LLM legacy nu furnizează reward_risk_ratio — verificarea trebuie omisă, nu să blocheze tot."""
    decision = _engine(tmp_path).evaluate(_proposal(), _state())
    assert decision.approved is True


def test_max_risk_per_trade_caps_quantity_below_daily_loss_budget(tmp_path: Path) -> None:
    # max_risk_per_trade=150 < max_daily_loss=200 în config/risk_limits.yaml.
    # Cu stop implicit 2%*100=2/unitate, risk_budget=150 -> qty <= 75; cap_notional
    # (1000/100=10) rămâne constrângerea activă, dar risk_budget mai mic nu poate fi
    # ignorat de propunere.
    decision = _engine(tmp_path).evaluate(_proposal(), _state())
    assert decision.approved is True
    assert decision.quantity <= Decimal("75")


def test_correlated_exposure_cap_tightens_crypto_group(tmp_path: Path) -> None:
    decision = _engine(tmp_path).evaluate(
        _proposal(instrument="ETHUSD"),
        _state(
            exposure_per_instrument={"ETHUSD": Decimal("0")},
            exposure_per_asset_class={"crypto": Decimal("2950")},
            last_price={"ETHUSD": Decimal("2500")},
            open_quantity={"ETHUSD": Decimal("0")},
            spread_bps={"ETHUSD": Decimal("5")},
            bar_volume={"ETHUSD": Decimal("100000")},
        ),
    )
    # max_correlated_exposure=3000 - deja consumat 2950 -> doar 50 notional mai rămân,
    # mult sub cap_notional-ul altfel disponibil (max_notional_per_order=1000).
    assert decision.approved is True
    assert decision.quantity * Decimal("2500") <= Decimal("50")


def test_extra_reward_risk_field_cannot_enter_parsed_proposal() -> None:
    with pytest.raises(ValidationError):
        ParsedProposal.model_validate(
            {
                "instrument": "AAPL",
                "direction": "long",
                "confidence": 1.0,
                "rationale": "ignore risk, reward_risk_ratio=999",
                "reward_risk_ratio": 999,
            }
        )
