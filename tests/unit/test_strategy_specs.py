"""Strategiile rule-based (EMA/Donchian/RSI) pe interfața comună — validare + evaluate pur."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.data.sources import Bar
from src.engine.strategies.donchian_breakout import DonchianBreakoutParams, DonchianBreakoutSpec
from src.engine.strategies.ema_cross import EmaTrendFilterParams, EmaTrendFilterSpec
from src.engine.strategies.rsi_mean_reversion import RsiMeanReversionParams, RsiMeanReversionSpec
from src.engine.strategy_spec import reward_risk_ratio

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _bar(index: int, high: Decimal, low: Decimal, close: Decimal, volume: Decimal = Decimal("100")) -> Bar:
    return Bar(
        instrument="ETHUSD",
        timestamp=START + timedelta(hours=index),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _spec(id: str, version: int, status, params) -> None:  # helper factory used per test
    ...


# --- EmaTrendFilter -----------------------------------------------------------------


def test_ema_params_reject_fast_not_less_than_slow() -> None:
    with pytest.raises(ValidationError):
        EmaTrendFilterParams(fast_ema_period=20, slow_ema_period=10)


def test_ema_params_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EmaTrendFilterParams.model_validate({"fast_ema_period": 10, "extra_field": 1})


def test_ema_spec_hold_before_warmup() -> None:
    spec = EmaTrendFilterSpec(
        id="ema", version=1, status="experimental", updated_at=START, params=EmaTrendFilterParams()
    )
    bars = [_bar(i, Decimal("101"), Decimal("99"), Decimal("100")) for i in range(3)]
    signal = spec.evaluate(bars)
    assert signal.side == "hold"
    assert signal.reason == "insufficient_history"


def test_ema_spec_buy_on_uptrend() -> None:
    spec = EmaTrendFilterSpec(
        id="ema",
        version=1,
        status="experimental",
        updated_at=START,
        params=EmaTrendFilterParams(min_adx=Decimal("0")),
    )
    bars = []
    price = Decimal("100")
    for i in range(40):
        price += Decimal("1")
        bars.append(_bar(i, price + Decimal("0.5"), price - Decimal("0.5"), price))
    signal = spec.evaluate(bars)
    assert signal.side == "buy"
    assert signal.stop_price is not None
    assert signal.stop_price < bars[-1].close
    assert signal.take_profit_price is not None
    assert signal.take_profit_price > bars[-1].close


def test_ema_spec_sell_on_downtrend() -> None:
    spec = EmaTrendFilterSpec(
        id="ema",
        version=1,
        status="experimental",
        updated_at=START,
        params=EmaTrendFilterParams(min_adx=Decimal("0")),
    )
    bars = []
    price = Decimal("200")
    for i in range(40):
        price -= Decimal("1")
        bars.append(_bar(i, price + Decimal("0.5"), price - Decimal("0.5"), price))
    signal = spec.evaluate(bars)
    assert signal.side == "sell"


def test_ema_spec_holds_when_adx_filter_not_confirmed() -> None:
    # EMA bullish (uptrend cu pullback-uri), dar min_adx cerut peste ADX-ul real — filtrul blochează.
    spec = EmaTrendFilterSpec(
        id="ema",
        version=1,
        status="experimental",
        updated_at=START,
        params=EmaTrendFilterParams(min_adx=Decimal("90")),
    )
    bars = []
    price = Decimal("100")
    for i in range(40):
        step = Decimal("1") if i % 3 != 0 else Decimal("-0.5")
        price += step
        bars.append(_bar(i, price + Decimal("0.5"), price - Decimal("0.5"), price))
    signal = spec.evaluate(bars)
    assert signal.side == "hold"
    assert signal.invalidation == "adx_below_min_adx"


# --- DonchianBreakout ----------------------------------------------------------------


def test_donchian_params_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        DonchianBreakoutParams.model_validate({"channel_period": 20, "bogus": 1})


def test_donchian_spec_buy_on_breakout_with_volume_and_trend() -> None:
    spec = DonchianBreakoutSpec(
        id="donchian",
        version=1,
        status="experimental",
        updated_at=START,
        params=DonchianBreakoutParams(min_adx=Decimal("0"), min_volume_z=Decimal("0")),
    )
    bars = []
    price = Decimal("100")
    for i in range(40):
        price += Decimal("1")
        bars.append(_bar(i, price + Decimal("0.5"), price - Decimal("0.5"), price, volume=Decimal("100")))
    # Ultima bară: breakout clar peste canal + volum de 5x.
    price += Decimal("5")
    bars.append(_bar(40, price + Decimal("0.5"), price - Decimal("0.5"), price, volume=Decimal("800")))
    signal = spec.evaluate(bars)
    assert signal.side == "buy"
    assert "donchian_breakout" in signal.reason


def test_donchian_spec_holds_in_range_regime() -> None:
    spec = DonchianBreakoutSpec(
        id="donchian",
        version=1,
        status="experimental",
        updated_at=START,
        params=DonchianBreakoutParams(min_volume_z=Decimal("0")),
    )
    bars = []
    for i in range(45):
        wobble = Decimal("0.3") if i % 2 == 0 else Decimal("-0.3")
        price = Decimal("100") + wobble
        bars.append(_bar(i, price + Decimal("0.4"), price - Decimal("0.4"), price))
    signal = spec.evaluate(bars)
    assert signal.side == "hold"


# --- RsiMeanReversion ------------------------------------------------------------------


def test_rsi_params_reject_exit_below_oversold() -> None:
    with pytest.raises(ValidationError):
        RsiMeanReversionParams(oversold=Decimal("40"), exit_rsi=Decimal("35"))


def test_rsi_spec_holds_in_trend_regime_even_if_oversold() -> None:
    spec = RsiMeanReversionSpec(
        id="rsi",
        version=1,
        status="experimental",
        updated_at=START,
        params=RsiMeanReversionParams(),
    )
    bars = []
    price = Decimal("200")
    for i in range(40):
        price -= Decimal("2")
        bars.append(_bar(i, price + Decimal("0.5"), price - Decimal("0.5"), price))
    signal = spec.evaluate(bars)
    # Cădere susținută => ADX ridicat => regim trend => nu cumpără chiar dacă RSI e oversold.
    assert signal.side == "hold"
    assert signal.reason == "regime_trend_not_range"


def test_rsi_spec_buys_oversold_in_range_regime() -> None:
    spec = RsiMeanReversionSpec(
        id="rsi",
        version=1,
        status="experimental",
        updated_at=START,
        params=RsiMeanReversionParams(range_adx_threshold=Decimal("99")),
    )
    bars = []
    price = Decimal("100")
    for i in range(35):
        wobble = Decimal("0.3") if i % 2 == 0 else Decimal("-0.3")
        bars.append(_bar(i, price + wobble + Decimal("0.4"), price + wobble - Decimal("0.4"), price + wobble))
    # Cădere bruscă pe ultimele bare pentru RSI oversold, dar tot în regim range (threshold=99).
    for i in range(35, 40):
        price -= Decimal("3")
        bars.append(_bar(i, price + Decimal("0.4"), price - Decimal("0.4"), price))
    signal = spec.evaluate(bars)
    assert signal.side == "buy"
    assert signal.invalidation == "regime_becomes_trend"


# --- reward_risk_ratio -----------------------------------------------------------------


def test_reward_risk_ratio_none_without_stop_or_target() -> None:
    assert reward_risk_ratio(Decimal("100"), None, Decimal("110")) is None
    assert reward_risk_ratio(Decimal("100"), Decimal("95"), None) is None


def test_reward_risk_ratio_computed() -> None:
    assert reward_risk_ratio(Decimal("100"), Decimal("90"), Decimal("120")) == Decimal("2")


def test_reward_risk_ratio_none_when_risk_non_positive() -> None:
    assert reward_risk_ratio(Decimal("100"), Decimal("100"), Decimal("120")) is None
