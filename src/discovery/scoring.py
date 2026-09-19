"""Scoruri deterministe (§2.1, §4) — funcții pure, fără rețea, fără LLM.

`opportunity_score`/`risk_score`/`composite_rank` sunt agregate configurabile (weights),
niciodată input pentru risk gates sau execuție (§4.4) — doar sortare/afișare.
"""

from __future__ import annotations

import math
import statistics
from decimal import Decimal


def notional_volume_usd(last_price: Decimal, volume_24h: Decimal) -> Decimal:
    return last_price * volume_24h


def spread_bps(bid: Decimal, ask: Decimal) -> float:
    if bid <= 0 or ask <= 0 or ask < bid:
        raise ValueError(f"invalid bid/ask: bid={bid}, ask={ask}")
    mid = (bid + ask) / Decimal(2)
    if mid == 0:
        raise ValueError("mid price is zero")
    return float((ask - bid) / mid * Decimal(10_000))


def liquidity_score(notional_usd: Decimal, *, reference_usd: Decimal = Decimal(50_000_000)) -> float:
    """Log-scaled: 0 la volum ~0, 1.0 la `reference_usd` (default 50M/zi), plafonat."""
    if notional_usd <= 0:
        return 0.0
    ratio = float(notional_usd / reference_usd)
    score = math.log10(1 + ratio * 9) if ratio < 1 else 1.0
    return max(0.0, min(1.0, score))


def spread_score(spread_bps_value: float, *, max_acceptable_bps: float = 100.0) -> float:
    """1.0 la spread=0, 0.0 la `max_acceptable_bps` sau mai mult."""
    if spread_bps_value <= 0:
        return 1.0
    score = 1.0 - (spread_bps_value / max_acceptable_bps)
    return max(0.0, min(1.0, score))


def log_returns(closes: list[float]) -> list[float]:
    if len(closes) < 2 or any(c <= 0 for c in closes):
        return []
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]


def volatility(closes: list[float]) -> float | None:
    """Deviație standard a log-return-urilor (generalizare a `_change_and_vol` din runtime_state.py)."""
    returns = log_returns(closes)
    if len(returns) < 2:
        return None
    return statistics.pstdev(returns)


def zscore(series: list[float], value: float) -> float | None:
    if len(series) < 2:
        return None
    mean = statistics.fmean(series)
    stdev = statistics.pstdev(series)
    if stdev == 0:
        return 0.0
    return (value - mean) / stdev


def data_quality_score(history_days_available: int, history_days_requested: int) -> float:
    if history_days_requested <= 0:
        raise ValueError("history_days_requested must be > 0")
    return max(0.0, min(1.0, history_days_available / history_days_requested))


def correlation(returns_a: list[float], returns_b: list[float]) -> float | None:
    """Pearson pe log-return-uri — trunchiat la lungimea comună (ferestre nealiniate)."""
    n = min(len(returns_a), len(returns_b))
    if n < 3:
        return None
    a, b = returns_a[-n:], returns_b[-n:]
    if statistics.pstdev(a) == 0 or statistics.pstdev(b) == 0:
        return None
    return statistics.correlation(a, b)


def operational_risk_score(
    *,
    status: str,
    listing_age_days: int,
    spread_bps_value: float,
    min_listing_age_days: int = 30,
) -> float:
    """0=fără risc operațional, 1=risc maxim. Determinist, fără istoric de status persistat (MVP Faza 1)."""
    risk = 0.0
    if status != "online":
        risk += 0.6
    if listing_age_days < min_listing_age_days:
        risk += 0.3 * (1 - listing_age_days / min_listing_age_days)
    if spread_bps_value > 200:
        risk += 0.1
    return max(0.0, min(1.0, risk))


def risk_score(
    *,
    operational_risk: float,
    volatility_value: float | None,
    volatility_reference: float = 0.05,
    weight_operational: float = 0.5,
    weight_volatility: float = 0.5,
) -> float:
    vol_normalized = min(1.0, volatility_value / volatility_reference) if volatility_value is not None else 1.0
    combined = weight_operational * operational_risk + weight_volatility * vol_normalized
    return max(0.0, min(1.0, combined))


def opportunity_score(
    *,
    liquidity: float,
    spread: float,
    data_quality: float,
    weight_liquidity: float = 0.4,
    weight_spread: float = 0.3,
    weight_data_quality: float = 0.3,
) -> float:
    """Faza 1: fără catalyst/news (nu sunt disponibile fără LLM/research wiring) — compus doar
    din factori de microstructură de piață. Extins în Faza 2/3 cu catalyst_score."""
    combined = weight_liquidity * liquidity + weight_spread * spread + weight_data_quality * data_quality
    return max(0.0, min(1.0, combined))


def confidence_score(*, data_quality: float, operational_risk: float) -> float:
    return max(0.0, min(1.0, data_quality * (1 - operational_risk)))


def composite_rank(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Doar pentru sortare/afișare (§4.4) — niciodată input pentru risk gates."""
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("weights must sum to a positive value")
    return sum(scores.get(key, 0.0) * weight for key, weight in weights.items()) / total_weight
