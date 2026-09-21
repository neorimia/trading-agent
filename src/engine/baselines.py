"""Baseline-uri simple pentru comparație — o strategie nu e „mai bună" doar pe total return.

Fiecare funcție e pură (bars → cifră), fără costuri de tranzacționare (buy&hold cu o
singură intrare) sau cu costuri simplificate documentate explicit. Randomul e un control
statistic opțional (util doar ca reper de „zgomot", nu ca baseline serios).
"""

from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal

from src.data.sources import Bar

RANDOM_CONTROL_SEED = 42


def buy_and_hold_return_pct(bars: list[Bar]) -> Decimal | None:
    """Randament simplu (%) cumpărând la prima bară și ținând până la ultima. Ignoră
    comisioanele de intrare/ieșire (o singură tranzacție, deci impactul e mic; documentat
    ca aproximare)."""
    if len(bars) < 2 or bars[0].close <= 0:
        return None
    return (bars[-1].close / bars[0].close - Decimal("1")) * Decimal("100")


def buy_and_hold_equity_curve(
    bars: list[Bar], starting_cash: Decimal
) -> list[tuple[datetime, Decimal]]:
    if not bars or bars[0].close <= 0:
        return []
    first_close = bars[0].close
    return [(bar.timestamp, starting_cash * (bar.close / first_close)) for bar in bars]


def cash_return_pct() -> Decimal:
    """Cash rămâne 0% prin definiție (ignorăm dobânda pe stablecoin/cash — nemodelată)."""
    return Decimal("0")


def equal_weight_return_pct(returns_by_symbol: dict[str, Decimal]) -> Decimal | None:
    """Randament simplu mediu (%) peste mai multe active cu greutăți egale. Primește
    randamentele deja calculate per simbol (ex. din `buy_and_hold_return_pct`), nu barele —
    rulările per-simbol pot avea lungimi/date diferite, deci alinierea se face de apelant."""
    if not returns_by_symbol:
        return None
    values = list(returns_by_symbol.values())
    return sum(values, Decimal("0")) / Decimal(len(values))


def random_control_return_pct(
    bars: list[Bar],
    *,
    trade_rate: float,
    seed: int = RANDOM_CONTROL_SEED,
) -> Decimal | None:
    """Control statistic: pentru fiecare bară, cu probabilitate `trade_rate` (rata de
    semnale non-hold a strategiei reale, ca să fie comparabil ca frecvență) intri/ieși
    long, fără costuri modelate. Seed fix => reproductibil. NU e un baseline serios —
    doar arată dacă strategia reală bate zgomotul pur la aceeași frecvență de tranzacții.
    """
    if len(bars) < 2 or trade_rate <= 0:
        return None
    rng = random.Random(seed)
    equity = Decimal("1")
    in_position = False
    for previous, current in zip(bars, bars[1:]):
        if rng.random() < trade_rate:
            in_position = not in_position
        if in_position and previous.close > 0:
            equity *= current.close / previous.close
    return (equity - Decimal("1")) * Decimal("100")
