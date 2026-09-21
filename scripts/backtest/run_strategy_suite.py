"""Rulare locală, reproductibilă a suitei de strategii pe StrategySpec.

Nu e folosit în CI (prea lent, poate cere fetch de rețea la primul run — vezi
tests/fixtures/bars_ethusd_1d.csv pentru testele rapide). Scopul: produce numere reale
pentru docs/backtesting-methodology.md §7 și docs/strategies-analysis.md §6, pe date publice
Binance klines cache-uite local (.cache/market_data/, gitignored).

Metodologie per (activ, strategie):
  1. chronological_split(bars) -> train (60%) / validation (20%) / holdout (20%), fără shuffle.
  2. Walk-forward (3 folduri expanding) pe train+validation, cost 1x — verifică robustețea
     parametrilor impliciți înainte de a privi holdout-ul (comparable() e sigur de calculat
     pe o fereastră care include warmup, pentru că nu depinde de equity curve).
  3. Holdout rulat IZOLAT (doar barele de holdout, fără warmup din train/validation) la
     1x/2x/3x cost — asta ține equity curve-ul (deci Sharpe/Sortino/drawdown/baseline) curat:
     nu se amestecă o perioadă de warmup fără tranzacții cu perioada testată. Compromisul
     documentat: indicatorii (EMA/RSI/ADX/Donchian) au nevoie de propriul warmup ÎN interiorul
     ferestrei de holdout, deci primele ~20-30 de bare din holdout pot arăta `hold` din lipsă
     de istoric suficient — vizibil în decisions/n_trades, nu ascuns.

Rulare:
    python -m scripts.backtest.run_strategy_suite
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.engine.backtest_runner import REPO_ROOT, run_backtest
from src.engine.cost_models import VenueCostConfig
from src.engine.splits import chronological_split, walk_forward_folds
from src.data.historical import make_cached_historical

ASSETS = ("ETHUSD", "BTCUSD")
KINDS = ("ema_cross", "donchian_breakout", "rsi_mean_reversion")
START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
TIMEFRAME = "1d"
RUN_ID = "strategy-suite-2024-full-year"


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> None:
    report_dir = REPO_ROOT / "backtests" / "reports" / RUN_ID
    report_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = REPO_ROOT / ".cache" / "market_data"
    # Default 'files' (rollback target); MARKET_DATA_STORE_BACKEND=postgres reads/
    # writes ohlcv_candles instead (docs/database-cutover-playbook.md §Market data).
    market = make_cached_historical(
        cache_dir,
        "binance",
        backend=os.environ.get("MARKET_DATA_STORE_BACKEND", "files"),
        database_url=os.environ.get("MARKET_DATA_DATABASE_URL"),
    )
    now = datetime.now(timezone.utc)

    summary: list[dict[str, Any]] = []
    for asset in ASSETS:
        bars, dataset_hash = market.get_or_fetch(asset, START, END, TIMEFRAME, now=now)
        split = chronological_split(bars)
        train_val = split.train + split.validation
        folds = walk_forward_folds(train_val, n_folds=3)

        for kind in KINDS:
            wf_rows = []
            for fold in folds:
                window = fold.train + fold.out_of_sample
                metrics = run_backtest(
                    window,
                    universe_symbol=asset,
                    timeframe=TIMEFRAME,
                    strategy_kind=kind,  # type: ignore[arg-type]
                    costs=VenueCostConfig.for_multiplier(1),
                    dataset_hash=dataset_hash,
                    halt_flag=report_dir / f"halt-wf-{asset}-{kind}-{fold.index}.flag",
                    trade_start=fold.out_of_sample[0].timestamp,
                )
                wf_rows.append(
                    {
                        "fold": fold.index,
                        "train_bars": len(fold.train),
                        "oos_bars": len(fold.out_of_sample),
                        **metrics.comparable(),
                    }
                )

            holdout_rows: dict[str, Any] = {}
            for multiplier in (1, 2, 3):
                metrics = run_backtest(
                    split.holdout,
                    universe_symbol=asset,
                    timeframe=TIMEFRAME,
                    strategy_kind=kind,  # type: ignore[arg-type]
                    costs=VenueCostConfig.for_multiplier(multiplier),
                    dataset_hash=dataset_hash,
                    halt_flag=report_dir / f"halt-holdout-{asset}-{kind}-{multiplier}x.flag",
                )
                holdout_rows[f"{multiplier}x"] = {
                    "comparable": metrics.comparable(),
                    "extra": metrics.extra,
                }

            payload = {
                "asset": asset,
                "kind": kind,
                "n_bars": len(bars),
                "split": {
                    "train": len(split.train),
                    "validation": len(split.validation),
                    "holdout": len(split.holdout),
                },
                "dataset_hash": dataset_hash,
                "walk_forward_1x": wf_rows,
                "holdout": holdout_rows,
            }
            (report_dir / f"{asset}_{kind}.json").write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8"
            )

            perf_1x = holdout_rows["1x"]["extra"]["performance"]
            perf_3x = holdout_rows["3x"]["extra"]["performance"]
            baselines_1x = holdout_rows["1x"]["extra"]["baselines"]
            summary.append(
                {
                    "asset": asset,
                    "kind": kind,
                    "holdout_bars": len(split.holdout),
                    "n_trades_1x": perf_1x["n_trades"],
                    "total_return_1x_pct": perf_1x["total_return_pct"],
                    "total_return_3x_pct": perf_3x["total_return_pct"],
                    "buy_and_hold_pct": baselines_1x["buy_and_hold_pct"],
                    "max_drawdown_1x_pct": perf_1x["max_drawdown_pct"],
                    "sharpe_1x": perf_1x["sharpe_ratio"],
                    "profit_factor_1x": perf_1x["profit_factor"],
                    "warnings": perf_1x["warnings"],
                }
            )

    manifest = {
        "run_id": RUN_ID,
        "generated_at": now.isoformat(),
        "assets": list(ASSETS),
        "kinds": list(KINDS),
        "start": START.isoformat(),
        "end": END.isoformat(),
        "timeframe": TIMEFRAME,
        "git_commit": _git_commit(),
        "risk_limits_note": "config/risk_limits.yaml as committed at git_commit — RiskEngine sizes every fill.",
        "random_seed": 42,
        "data_source": "binance_public_klines (cached locally, gitignored)",
    }
    (report_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {report_dir}")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
