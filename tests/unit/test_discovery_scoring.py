"""Funcții pure din src/discovery/scoring.py — determinism, fără rețea (design §4)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.discovery import scoring


def test_notional_volume_usd() -> None:
    assert scoring.notional_volume_usd(Decimal("100"), Decimal("10")) == Decimal("1000")


def test_spread_bps_basic() -> None:
    bps = scoring.spread_bps(Decimal("99"), Decimal("101"))
    assert bps == pytest.approx(200.0, rel=1e-6)


def test_spread_bps_rejects_crossed_book() -> None:
    with pytest.raises(ValueError):
        scoring.spread_bps(Decimal("101"), Decimal("99"))


def test_liquidity_score_monotonic_and_bounded() -> None:
    low = scoring.liquidity_score(Decimal("1000"))
    high = scoring.liquidity_score(Decimal("50000000"))
    assert 0.0 <= low < high <= 1.0
    assert high == pytest.approx(1.0)


def test_spread_score_zero_spread_is_perfect() -> None:
    assert scoring.spread_score(0.0) == 1.0
    assert scoring.spread_score(1000.0) == 0.0


def test_volatility_needs_at_least_three_closes() -> None:
    assert scoring.volatility([100.0, 101.0]) is None
    result = scoring.volatility([100.0, 101.0, 99.0, 102.0])
    assert result is not None
    assert result > 0


def test_volatility_is_deterministic() -> None:
    closes = [100.0, 102.0, 98.0, 101.0, 103.0]
    assert scoring.volatility(closes) == scoring.volatility(closes)


def test_zscore_flat_series_is_zero() -> None:
    assert scoring.zscore([1.0, 1.0, 1.0], 1.0) == 0.0


def test_zscore_insufficient_series_is_none() -> None:
    assert scoring.zscore([1.0], 5.0) is None


def test_data_quality_score_caps_at_one() -> None:
    assert scoring.data_quality_score(200, 90) == 1.0
    assert scoring.data_quality_score(45, 90) == pytest.approx(0.5)


def test_correlation_perfectly_correlated_returns() -> None:
    a = [0.01, 0.02, -0.01, 0.03, -0.02]
    assert scoring.correlation(a, a) == pytest.approx(1.0)


def test_correlation_insufficient_data_is_none() -> None:
    assert scoring.correlation([0.01], [0.02]) is None


def test_operational_risk_score_penalizes_offline_status() -> None:
    online = scoring.operational_risk_score(status="online", listing_age_days=400, spread_bps_value=5.0)
    offline = scoring.operational_risk_score(status="cancel_only", listing_age_days=400, spread_bps_value=5.0)
    assert offline > online


def test_risk_score_bounded() -> None:
    assert 0.0 <= scoring.risk_score(operational_risk=0.9, volatility_value=0.5) <= 1.0
    assert scoring.risk_score(operational_risk=0.0, volatility_value=None) == pytest.approx(0.5)


def test_opportunity_score_bounded() -> None:
    score = scoring.opportunity_score(liquidity=1.0, spread=1.0, data_quality=1.0)
    assert score == pytest.approx(1.0)


def test_composite_rank_weights_must_be_positive() -> None:
    with pytest.raises(ValueError):
        scoring.composite_rank({"a": 1.0}, {"a": 0.0})


def test_composite_rank_is_weighted_average() -> None:
    rank = scoring.composite_rank({"a": 1.0, "b": 0.0}, {"a": 1.0, "b": 1.0})
    assert rank == pytest.approx(0.5)
