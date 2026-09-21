"""Donchian channel breakout confirmat de volum, activ doar în regim de trend.

Ipoteză: un close peste maximul canalului Donchian anterior (N bare), pe volum
statistic ridicat (z-score) și cu ADX confirmând trend, e mai probabil o continuare
decât un fake-out. Nu tranzacționează dacă regimul curent e `range`.

Nu importă `src.execution`. `evaluate()` e pură.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pydantic import Field

from src.data.sources import Bar
from src.engine.indicators import atr, donchian_channel, volume_zscore
from src.engine.regime import classify_regime
from src.engine.strategy_spec import StrategyParams, StrategySignal, StrategySpec, StrategyStatus

SUPPORTED_ASSETS: tuple[str, ...] = ("ETHUSD", "BTCUSD")
SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("1h", "4h", "1d")


class DonchianBreakoutParams(StrategyParams):
    channel_period: int = Field(default=20, gt=1, le=200)
    volume_z_period: int = Field(default=20, gt=1, le=200)
    min_volume_z: Decimal = Field(default=Decimal("1.0"), ge=Decimal("-5"), le=Decimal("10"))
    adx_period: int = Field(default=14, gt=1, le=100)
    min_adx: Decimal = Field(default=Decimal("20"), ge=0, le=100)
    atr_period: int = Field(default=14, gt=1, le=100)
    atr_stop_mult: Decimal = Field(default=Decimal("2"), gt=0, le=10)
    atr_target_mult: Decimal = Field(default=Decimal("3"), gt=0, le=20)


class DonchianBreakoutSpec(StrategySpec):
    def __init__(
        self,
        *,
        id: str,
        version: int,
        status: StrategyStatus,
        updated_at: datetime,
        params: DonchianBreakoutParams,
    ) -> None:
        self.id = id
        self.name = "Donchian breakout + volume"
        self.description = (
            "Intră la ieșirea din canalul Donchian anterior, confirmată de volum peste "
            "medie și de un regim ADX de trend. Nu tranzacționează în regim range."
        )
        self.hypothesis = (
            "Un close peste maximul Donchian(N-1) însoțit de volume z-score ridicat, în "
            "regim de trend (ADX confirmat), e mai degrabă continuare decât fake-out."
        )
        self.version = version
        self.status = status
        self.updated_at = updated_at
        self.supported_assets = SUPPORTED_ASSETS
        self.supported_timeframes = SUPPORTED_TIMEFRAMES
        self.cooldown_bars = 5
        self.max_simultaneous_positions = 1
        self.max_exposure_override = None
        self.params = params

    def warmup_bars(self) -> int:
        p = self.params
        return max(
            p.channel_period + 1,
            p.volume_z_period,
            p.adx_period * 2 + 1,
            p.atr_period + 1,
        )

    def evaluate(self, bars_upto_t: list[Bar]) -> StrategySignal:
        if len(bars_upto_t) < self.warmup_bars():
            return StrategySignal(side="hold", reason="insufficient_history", confidence=0.0)
        prior = bars_upto_t[:-1]
        channel = donchian_channel(prior, self.params.channel_period)
        if channel is None:
            return StrategySignal(side="hold", reason="channel_not_ready", confidence=0.0)
        high, _low, mid = channel
        current = bars_upto_t[-1]
        regime = classify_regime(
            bars_upto_t, adx_period=self.params.adx_period, trend_threshold=self.params.min_adx
        )
        volumes = [bar.volume for bar in bars_upto_t]
        vol_z = volume_zscore(volumes, self.params.volume_z_period)

        if current.close > high:
            if regime != "trend":
                return StrategySignal(
                    side="hold",
                    reason=f"breakout_but_regime={regime}",
                    confidence=0.0,
                    invalidation="regime_not_trend",
                )
            if vol_z is None or vol_z < self.params.min_volume_z:
                return StrategySignal(
                    side="hold",
                    reason=f"breakout_without_volume_confirmation vol_z={vol_z}",
                    confidence=0.0,
                )
            atr_value = atr(bars_upto_t, self.params.atr_period)
            stop = current.close - atr_value * self.params.atr_stop_mult if atr_value else None
            target = current.close + atr_value * self.params.atr_target_mult if atr_value else None
            confidence = min(1.0, float(vol_z) / 3.0)
            return StrategySignal(
                side="buy",
                reason=f"donchian_breakout close>{high:.4f} vol_z={vol_z:.2f}",
                confidence=max(0.1, confidence),
                stop_price=stop,
                take_profit_price=target,
                invalidation="close_below_channel_mid",
            )
        if current.close < mid:
            return StrategySignal(
                side="sell",
                reason=f"close<channel_mid ({current.close:.4f}<{mid:.4f})",
                confidence=0.6,
                invalidation="close_reclaims_channel_mid",
            )
        return StrategySignal(side="hold", reason="inside_channel", confidence=0.0)


def default_params() -> DonchianBreakoutParams:
    return DonchianBreakoutParams()


def _now() -> datetime:
    return datetime.now(timezone.utc)
