"""Stress-test determinist — PnL proxied din notional, fără LLM."""

from __future__ import annotations

from decimal import Decimal

from src.engine.stress import herfindahl_hirschman, stress_portfolio


def test_stress_linear_shock_on_total_exposure() -> None:
    report = stress_portfolio({"ETHUSD": Decimal("1000"), "BTCUSD": Decimal("1000")})
    down10 = next(item for item in report["scenarios"] if item["name"] == "crypto_spot_down_10")
    assert Decimal(down10["estimated_pnl"]) == Decimal("-200")
    assert report["options_available"] is False
    assert report["hedge_universe"] == "spot_only_kraken"


def test_hhi_concentration_single_name() -> None:
    hhi = herfindahl_hirschman({"ETHUSD": Decimal("1000")})
    assert hhi == Decimal("1")
    report = stress_portfolio({"ETHUSD": Decimal("1000")})
    assert report["duplicated_bets"] == "high"


def test_empty_book_has_zero_exposure() -> None:
    report = stress_portfolio({})
    assert report["total_exposure"] == "0"
    assert report["hhi"] == "0"
