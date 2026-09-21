"""EMA trend filter — long-only, EMA cross confirmat opțional de ADX, cu cooldown.

Ipoteză: pe crypto major (ETH/BTC), un trend confirmat de EMA persistă suficient cât un
long-only cu costurile Kraken curente să nu fie doar zgomot — dar doar cât timp ADX
confirmă că e efectiv un trend, nu o piață laterală.

Nu importă `src.execution`. `evaluate()` e pură — vezi `src.engine.strategy_spec`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pydantic import Field, field_validator

from src.data.sources import Bar
from src.engine.indicators import adx, atr
from src.engine.signals import ema
from src.engine.strategy_spec import StrategyParams, StrategySignal, StrategySpec, StrategyStatus

SUPPORTED_ASSETS: tuple[str, ...] = ("ETHUSD", "BTCUSD")
SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("1h", "4h", "1d")


class EmaTrendFilterParams(StrategyParams):
    fast_ema_period: int = Field(default=10, gt=0, le=200)
    slow_ema_period: int = Field(default=20, gt=1, le=400)
    # 0 = filtrul ADX e dezactivat (comportament EMA-cross pur). Crescut => cere trend
    # confirmat înainte de a intra.
    adx_period: int = Field(default=14, gt=1, le=100)
    min_adx: Decimal = Field(default=Decimal("15"), ge=0, le=100)
    atr_period: int = Field(default=14, gt=1, le=100)
    atr_stop_mult: Decimal = Field(default=Decimal("2"), gt=0, le=10)
    atr_target_mult: Decimal = Field(default=Decimal("3"), gt=0, le=20)

    @field_validator("slow_ema_period")
    @classmethod
    def _slow_after_fast(cls, value: int, info) -> int:
        fast = info.data.get("fast_ema_period")
        if fast is not None and value <= fast:
            raise ValueError("slow_ema_period must be strictly greater than fast_ema_period")
        return value


class EmaTrendFilterSpec(StrategySpec):
    def __init__(
        self,
        *,
        id: str,
        version: int,
        status: StrategyStatus,
        updated_at: datetime,
        params: EmaTrendFilterParams,
    ) -> None:
        self.id = id
        self.name = "EMA trend filter"
        self.description = (
            "Long-only EMA crossover, cu confirmare opțională de tărie a trendului (ADX) "
            "și cooldown după fiecare ieșire."
        )
        self.hypothesis = (
            "Pe ETH/BTC, un trend confirmat de EMA(fast)>=EMA(slow) persistă suficient de "
            "mult încât un long-only cu costurile Kraken curente (maker 16bps/taker 26bps) "
            "să nu fie doar zgomot — mai ales dacă ADX confirmă că e efectiv un trend."
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
        needed = [p.slow_ema_period, p.atr_period + 1]
        if p.min_adx > 0:
            needed.append(p.adx_period * 2 + 1)
        return max(needed)

    def evaluate(self, bars_upto_t: list[Bar]) -> StrategySignal:
        if len(bars_upto_t) < self.warmup_bars():
            return StrategySignal(side="hold", reason="insufficient_history", confidence=0.0)
        closes = [bar.close for bar in bars_upto_t]
        fast = ema(closes, self.params.fast_ema_period)
        slow = ema(closes, self.params.slow_ema_period)
        if fast is None or slow is None:
            return StrategySignal(side="hold", reason="ema_not_ready", confidence=0.0)
        current = bars_upto_t[-1]
        if fast >= slow:
            trend_strength = adx(bars_upto_t, self.params.adx_period) if self.params.min_adx > 0 else None
            if trend_strength is not None and trend_strength < self.params.min_adx:
                return StrategySignal(
                    side="hold",
                    reason=f"ema_bullish_but_adx_{trend_strength:.2f}_below_{self.params.min_adx}",
                    confidence=0.0,
                    invalidation="adx_below_min_adx",
                )
            atr_value = atr(bars_upto_t, self.params.atr_period)
            stop = current.close - atr_value * self.params.atr_stop_mult if atr_value else None
            target = current.close + atr_value * self.params.atr_target_mult if atr_value else None
            confidence = 0.5 if trend_strength is None else min(1.0, float(trend_strength) / 50.0)
            return StrategySignal(
                side="buy",
                reason=f"ema_fast>=ema_slow (fast={fast:.4f} slow={slow:.4f})",
                confidence=max(0.1, confidence),
                stop_price=stop,
                take_profit_price=target,
                invalidation="fast_ema_crosses_below_slow_ema",
            )
        return StrategySignal(
            side="sell",
            reason=f"ema_fast<ema_slow (fast={fast:.4f} slow={slow:.4f})",
            confidence=0.6,
            invalidation="fast_ema_crosses_above_slow_ema",
        )


def default_params() -> EmaTrendFilterParams:
    return EmaTrendFilterParams()


def _now() -> datetime:
    return datetime.now(timezone.utc)
