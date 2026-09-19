"""Stress-test determinist de portofoliu. Fără LLM, fără ordine."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

DEFAULT_SHOCKS: tuple[tuple[str, Decimal], ...] = (
    ("crypto_spot_down_10", Decimal("-0.10")),
    ("crypto_bear_20", Decimal("-0.20")),
    ("funding_squeeze_proxy", Decimal("-0.08")),
    ("stablecoin_depeg_proxy", Decimal("-0.05")),
    ("macro_risk_off", Decimal("-0.12")),
)


def _dstr(value: Decimal) -> str:
    return format(value, "f")


def herfindahl_hirschman(weights: dict[str, Decimal]) -> Decimal:
    total = sum(weights.values(), Decimal("0"))
    if total <= 0:
        return Decimal("0")
    return sum((share / total) ** 2 for share in weights.values())


def stress_portfolio(
    exposure_per_instrument: dict[str, Decimal],
    *,
    shocks: tuple[tuple[str, Decimal], ...] = DEFAULT_SHOCKS,
) -> dict[str, Any]:
    """PnL proxied = -notional * |shock| pentru șocuri negative (long-only spot)."""
    total = sum(exposure_per_instrument.values(), Decimal("0"))
    hhi = herfindahl_hirschman(exposure_per_instrument)
    concentration = sorted(
        (
            {
                "instrument": symbol,
                "notional": _dstr(notional),
                "weight": _dstr(notional / total) if total > 0 else "0",
            }
            for symbol, notional in exposure_per_instrument.items()
        ),
        key=lambda row: Decimal(row["notional"]),
        reverse=True,
    )
    scenarios = []
    for name, shock in shocks:
        pnl = Decimal("0")
        if shock < 0:
            pnl = total * shock
        elif shock > 0:
            pnl = total * shock
        scenarios.append(
            {
                "name": name,
                "spot_shock": _dstr(shock),
                "estimated_pnl": _dstr(pnl),
                "estimated_equity_change_pct": _dstr(shock) if total > 0 else "0",
            }
        )
    return {
        "total_exposure": _dstr(total),
        "hhi": _dstr(hhi),
        "duplicated_bets": "high" if hhi >= Decimal("0.5") else "moderate" if hhi >= Decimal("0.25") else "low",
        "concentration": concentration,
        "scenarios": scenarios,
        "hedge_universe": "spot_only_kraken",
        "options_available": False,
        "note": "Shocks are linear spot proxies. Funding/depeg are not simulated from derivatives data.",
    }
