"""RSI mean reversion — tranzacționează doar în regim range (ADX scăzut).

Ipoteză: în regim range, extremele RSI pe ETH/BTC tind să revină la medie; același
extrem într-un regim de trend e mai degrabă continuare, deci strategia trebuie să nu
tranzacționeze acolo. Invalidată explicit dacă regimul devine trend.

Nu importă `src.execution`. `evaluate()` e pură.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pydantic import Field, field_validator

from src.data.sources import Bar
from src.engine.indicators import atr, rsi
from src.engine.regime import classify_regime
from src.engine.strategy_spec import StrategyParams, StrategySignal, StrategySpec, StrategyStatus

SUPPORTED_ASSETS: tuple[str, ...] = ("ETHUSD", "BTCUSD")
SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("1h", "1d")


class RsiMeanReversionParams(StrategyParams):
    rsi_period: int = Field(default=14, gt=1, le=100)
    oversold: Decimal = Field(default=Decimal("30"), ge=1, le=49)
    exit_rsi: Decimal = Field(default=Decimal("50"), ge=50, le=99)
    adx_period: int = Field(default=14, gt=1, le=100)
    range_adx_threshold: Decimal = Field(default=Decimal("20"), ge=0, le=100)
    atr_period: int = Field(default=14, gt=1, le=100)
    atr_stop_mult: Decimal = Field(default=Decimal("1.5"), gt=0, le=10)
    atr_target_mult: Decimal = Field(default=Decimal("2"), gt=0, le=20)

    @field_validator("exit_rsi")
    @classmethod
    def _exit_above_oversold(cls, value: Decimal, info) -> Decimal:
        oversold = info.data.get("oversold")
        if oversold is not None and value <= oversold:
            raise ValueError("exit_rsi must be strictly greater than oversold")
        return value


class RsiMeanReversionSpec(StrategySpec):
    def __init__(
        self,
        *,
        id: str,
        version: int,
        status: StrategyStatus,
        updated_at: datetime,
        params: RsiMeanReversionParams,
    ) -> None:
        self.id = id
        self.name = "RSI mean reversion (sideways only)"
        self.description = (
            "Cumpără extreme RSI oversold doar cât timp piața e clasificată range (ADX "
            "scăzut); invalidată dacă regimul devine trend."
        )
        self.hypothesis = (
            "În regim range, RSI extrem pe ETH/BTC revine la medie; același extrem în "
            "trend e mai degrabă continuare — strategia nu trebuie să tranzacționeze acolo."
        )
        self.version = version
        self.status = status
        self.updated_at = updated_at
        self.supported_assets = SUPPORTED_ASSETS
        self.supported_timeframes = SUPPORTED_TIMEFRAMES
        self.cooldown_bars = 3
        self.max_simultaneous_positions = 1
        self.max_exposure_override = None
        self.params = params

    def warmup_bars(self) -> int:
        p = self.params
        return max(p.rsi_period + 1, p.adx_period * 2 + 1, p.atr_period + 1)

    def evaluate(self, bars_upto_t: list[Bar]) -> StrategySignal:
        if len(bars_upto_t) < self.warmup_bars():
            return StrategySignal(side="hold", reason="insufficient_history", confidence=0.0)
        closes = [bar.close for bar in bars_upto_t]
        current_rsi = rsi(closes, self.params.rsi_period)
        if current_rsi is None:
            return StrategySignal(side="hold", reason="rsi_not_ready", confidence=0.0)
        regime = classify_regime(
            bars_upto_t,
            adx_period=self.params.adx_period,
            trend_threshold=self.params.range_adx_threshold,
        )
        current = bars_upto_t[-1]
        if regime == "trend":
            return StrategySignal(
                side="hold",
                reason="regime_trend_not_range",
                confidence=0.0,
                invalidation="adx_confirms_trend",
            )
        if current_rsi <= self.params.oversold:
            atr_value = atr(bars_upto_t, self.params.atr_period)
            stop = current.close - atr_value * self.params.atr_stop_mult if atr_value else None
            target = current.close + atr_value * self.params.atr_target_mult if atr_value else None
            depth = float(self.params.oversold - current_rsi)
            confidence = max(0.1, min(1.0, depth / 30.0 + 0.3))
            return StrategySignal(
                side="buy",
                reason=f"rsi={current_rsi:.2f}<=oversold={self.params.oversold} regime=range",
                confidence=confidence,
                stop_price=stop,
                take_profit_price=target,
                invalidation="regime_becomes_trend",
            )
        if current_rsi >= self.params.exit_rsi:
            return StrategySignal(
                side="sell",
                reason=f"rsi={current_rsi:.2f}>=exit_rsi={self.params.exit_rsi}",
                confidence=0.5,
            )
        return StrategySignal(side="hold", reason="rsi_inside_band", confidence=0.0)


def default_params() -> RsiMeanReversionParams:
    return RsiMeanReversionParams()


def _now() -> datetime:
    return datetime.now(timezone.utc)
