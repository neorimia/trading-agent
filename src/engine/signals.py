"""Funcții pure de semnal — folosite de strategii și de testul de look-ahead.

Nu importă NautilusTrader și nu văd bare cu timestamp > T.
"""

from __future__ import annotations

from decimal import Decimal

from src.data.sources import Bar
from src.engine.proposal_types import ParsedProposal, ProposalContext


def ema(values: list[Decimal], period: int) -> Decimal | None:
    if period <= 0:
        raise ValueError("ema period must be positive")
    if len(values) < period:
        return None
    k = Decimal(2) / Decimal(period + 1)
    current = sum(values[:period], Decimal("0")) / Decimal(period)
    for value in values[period:]:
        current = (value * k) + (current * (Decimal("1") - k))
    return current


def ema_cross_direction(
    closes: list[Decimal],
    fast_period: int,
    slow_period: int,
) -> str | None:
    """Întoarce long/exit după crossover, sau None dacă indicatorii nu sunt gata.

    long = fast >= slow (tendință urcătoare). exit = fast < slow (ieșire long-only).
    """
    if fast_period >= slow_period:
        raise ValueError("fast_ema_period must be < slow_ema_period")
    fast = ema(closes, fast_period)
    slow = ema(closes, slow_period)
    if fast is None or slow is None:
        return None
    if fast >= slow:
        return "long"
    return "exit"


def market_summary_from_bars(
    bars: list[Bar],
    *,
    fast_period: int,
    slow_period: int,
    lookback: int,
) -> str:
    """Rezumat construit exclusiv din `bars` (apelantul trebuie să taie la T)."""
    if not bars:
        return "no bars"
    window = bars[-lookback:] if lookback > 0 else bars
    closes = [bar.close for bar in window]
    last = bars[-1]
    fast = ema(closes, min(fast_period, len(closes))) if len(closes) >= fast_period else None
    slow = ema(closes, min(slow_period, len(closes))) if len(closes) >= slow_period else None
    ret_1 = ""
    if len(closes) >= 2 and closes[-2] != 0:
        change = (closes[-1] - closes[-2]) / closes[-2] * Decimal("100")
        ret_1 = f" ret_1={format(change, '.3f')}%"
    close_list = ",".join(format(price, "f") for price in closes[-min(5, len(closes)) :])
    return (
        f"instrument={last.instrument} close={format(last.close, 'f')} "
        f"high={format(last.high, 'f')} low={format(last.low, 'f')} "
        f"ema_fast={format(fast, 'f') if fast is not None else 'na'} "
        f"ema_slow={format(slow, 'f') if slow is not None else 'na'}"
        f"{ret_1} last_closes={close_list}"
    )


def iter_prefixes(bars: list[Bar]) -> list[list[Bar]]:
    """Fiecare prefix bars[:i+1] — helper pentru look-ahead și cache fill."""
    return [bars[: index + 1] for index in range(len(bars))]


def baseline_proposal(
    bars_upto_t: list[Bar],
    *,
    fast_period: int,
    slow_period: int,
) -> ParsedProposal | None:
    closes = [bar.close for bar in bars_upto_t]
    direction = ema_cross_direction(closes, fast_period, slow_period)
    if direction is None:
        return None
    last = bars_upto_t[-1]
    return ParsedProposal(
        instrument=last.instrument,
        direction=direction,  # type: ignore[arg-type]
        confidence=1.0,
        rationale=f"ema_cross fast={fast_period} slow={slow_period}",
    )


def proposal_context_at(
    bars_upto_t: list[Bar],
    *,
    fast_period: int,
    slow_period: int,
    lookback: int,
) -> ProposalContext:
    last = bars_upto_t[-1]
    return ProposalContext(
        instrument=last.instrument,
        as_of=last.timestamp,
        market_summary=market_summary_from_bars(
            bars_upto_t,
            fast_period=fast_period,
            slow_period=slow_period,
            lookback=lookback,
        ),
        external_context=None,
    )
