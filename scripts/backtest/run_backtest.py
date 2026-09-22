"""Orchestrator CLI — backtest realist Task 4.

Umple cache-ul de propuneri (HTTP către llm/server sau Ollama direct din script),
apoi rulează walk-forward (baseline) și holdout LLM vs baseline la 1×/2×/3× costuri.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.data.historical import make_cached_historical
from src.engine.backtest_repository import open_backtest_store
from src.engine.backtest_runner import write_json, run_backtest, REPO_ROOT
from src.engine.backtest_store import compute_universe_sha256
from src.engine.cost_models import VenueCostConfig
from src.engine.proposal_cache import CachingLLMProposalClient
from src.engine.llm_client import LLMProposalClient
from src.engine.signals import iter_prefixes, proposal_context_at
from src.engine.splits import chronological_split, walk_forward_folds
from src.engine.proposal_types import ProposalContext, RejectedProposal


DEFAULT_START = datetime(2024, 11, 1, tzinfo=timezone.utc)
DEFAULT_END = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


class DirectOllamaClient:
    """Umple cache-ul din script (nu din engine/). Același generate_proposal ca llm/service."""

    def request_proposal(
        self,
        context: ProposalContext,
        timeout_s: float | None = None,
    ) -> ParsedProposal | RejectedProposal:
        from src.engine.proposal_types import ParsedProposal as EngineProposal
        from src.llm.schema import LLMProposal
        from src.llm.service import (
            ModelConfig,
            ProposalInput,
            generate_proposal,
            load_llm_settings,
            load_universe,
            validate_against_universe,
        )

        config, universe_path = load_llm_settings()
        if timeout_s is not None:
            config = ModelConfig(
                ollama_host=config.ollama_host,
                model_name=config.model_name,
                timeout_s=timeout_s,
            )
        universe = load_universe(universe_path)
        inner = generate_proposal(
            ProposalInput(
                instrument=context.instrument,
                as_of=context.as_of,
                market_summary=context.market_summary,
                external_context=context.external_context,
            ),
            config,
        )
        if isinstance(inner, LLMProposal):
            inner = validate_against_universe(inner, universe)
        if isinstance(inner, LLMProposal):
            return EngineProposal.model_validate(inner.model_dump())
        return RejectedProposal(reason=inner.reason, raw_output=inner.raw_output)


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


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Faza 4 realistic backtest")
    parser.add_argument("--instrument", default="ETHUSD")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--end", default=DEFAULT_END.isoformat())
    parser.add_argument("--csv", default="", help="Optional local CSV instead of network history")
    parser.add_argument(
        "--history-source",
        choices=("binance", "kraken"),
        default="binance",
        help="Public OHLC vendor. Execution venue remains KRAKEN; binance is long-window backfill.",
    )
    parser.add_argument("--llm-url", default="http://127.0.0.1:8765")
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--direct-ollama", action="store_true")
    parser.add_argument("--lookback", type=int, default=20)
    parser.add_argument("--run-id", default="")
    return parser.parse_args()


def _dt(raw: str) -> datetime:
    moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def fill_proposal_cache(
    bars,
    cache_dir: Path,
    lookback: int,
    inner,
    *,
    since: datetime | None = None,
) -> int:
    client = CachingLLMProposalClient(cache_dir, inner)
    filled = 0
    for prefix in iter_prefixes(bars):
        if len(prefix) < lookback:
            continue
        if since is not None and prefix[-1].timestamp < since:
            continue
        context = proposal_context_at(
            prefix, fast_period=10, slow_period=20, lookback=lookback
        )
        client.request_proposal(context)
        filled += 1
    return filled


def main() -> None:
    args = _parse_args()
    start = _dt(args.start)
    end = _dt(args.end)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = REPO_ROOT / "backtests" / "reports" / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = REPO_ROOT / ".cache" / "market_data"
    now = datetime.now(timezone.utc)

    # Default 'files' (rollback target); MARKET_DATA_STORE_BACKEND=postgres reads/
    # writes ohlcv_candles instead (docs/database-cutover-playbook.md §Market data).
    market_data_backend = os.environ.get("MARKET_DATA_STORE_BACKEND", "files")
    market_data_database_url = os.environ.get("MARKET_DATA_DATABASE_URL")
    if args.csv:
        market = make_cached_historical(
            cache_dir,
            csv_path=Path(args.csv),
            backend=market_data_backend,
            database_url=market_data_database_url,
        )
    else:
        market = make_cached_historical(
            cache_dir,
            args.history_source,
            backend=market_data_backend,
            database_url=market_data_database_url,
        )
    bars, dataset_hash = market.get_or_fetch(
        args.instrument, start, end, args.timeframe, now=now
    )
    split = chronological_split(bars)
    train_val = split.train + split.validation
    folds = walk_forward_folds(train_val, n_folds=3)

    wf_metrics = []
    for fold in folds:
        window = fold.train + fold.out_of_sample
        metrics = run_backtest(
            window,
            universe_symbol=args.instrument,
            timeframe=args.timeframe,
            strategy_kind="baseline",
            costs=VenueCostConfig.for_multiplier(1),
            dataset_hash=dataset_hash,
            halt_flag=report_dir / f"halt-wf-{fold.index}.flag",
            trade_start=fold.out_of_sample[0].timestamp,
        )
        wf_metrics.append(
            {
                "fold": fold.index,
                "train_bars": len(fold.train),
                "oos_bars": len(fold.out_of_sample),
                "metrics": metrics.comparable(),
            }
        )

    proposal_dir = report_dir / "proposal_cache"
    llm_ready = False
    if not args.skip_llm:
        inner: object
        if args.direct_ollama:
            inner = DirectOllamaClient()
        else:
            inner = LLMProposalClient(base_url=args.llm_url, timeout_s=120.0)
        try:
            fill_proposal_cache(
                bars,
                proposal_dir,
                args.lookback,
                inner,
                since=split.holdout[0].timestamp,
            )
            llm_ready = True
        except Exception as exc:  # noqa: BLE001 — documentat în manifest; holdout LLM e sărit
            write_json(report_dir / "llm_cache_error.json", {"error": str(exc)})
            if args.direct_ollama:
                raise

    holdout_window = train_val + split.holdout
    holdout_start = split.holdout[0].timestamp
    comparison = []
    kinds = ["baseline"] + (["llm"] if llm_ready else [])
    frozen = CachingLLMProposalClient(proposal_dir, inner=None, read_only=True)

    # Faza 6 (docs/database-design.md §8.6): default 'files' (rollback target, the
    # manifest.json/metrics_*.json writes below are unconditional). postgres inserts
    # one backtest_runs row per metrics_{kind}_{Nx}.json — one suite run has no
    # single strategy_version_id/instrument row of its own in the design, so
    # metrics.suite_run_id links siblings instead of a dedicated suite table.
    backtest_store_backend = os.environ.get("BACKTEST_STORE_BACKEND", "files")
    backtest_database_url = os.environ.get("BACKTEST_DATABASE_URL")
    backtest_store = open_backtest_store(
        backend=backtest_store_backend, database_url=backtest_database_url
    )
    universe_sha256 = compute_universe_sha256(REPO_ROOT / "config" / "universe.yaml")
    strategy_ids = {"baseline": "baseline_ema_cross", "llm": "llm_assisted"}

    for multiplier in (1, 2, 3):
        costs = VenueCostConfig.for_multiplier(multiplier)
        row: dict = {"cost_multiplier": multiplier}
        for kind in kinds:
            metrics = run_backtest(
                holdout_window,
                universe_symbol=args.instrument,
                timeframe=args.timeframe,
                strategy_kind=kind,  # type: ignore[arg-type]
                costs=costs,
                dataset_hash=dataset_hash,
                halt_flag=report_dir / f"halt-holdout-{kind}-{multiplier}x.flag",
                trade_start=holdout_start,
                proposal_client=frozen if kind == "llm" else None,
            )
            write_json(
                report_dir / f"metrics_{kind}_{multiplier}x.json",
                metrics.comparable(),
            )
            row[kind] = metrics.comparable()
            if backtest_store is not None:
                strategy_version_id = backtest_store.resolve_active_strategy_version_id(
                    strategy_ids[kind]
                )
                if strategy_version_id is not None:
                    backtest_run_id = backtest_store.insert_run(
                        strategy_version_id=strategy_version_id,
                        instrument=args.instrument,
                        timeframe=args.timeframe,
                        period_start=holdout_start,
                        period_end=end,
                        dataset_hash=dataset_hash,
                        universe_sha256=universe_sha256,
                        random_seed=42,
                        status="completed",
                        metrics={"suite_run_id": run_id, **metrics.comparable()},
                        report_path=str(report_dir / f"metrics_{kind}_{multiplier}x.json"),
                    )
                    backtest_store.insert_trades(
                        backtest_run_id,
                        args.instrument,
                        metrics.extra.get("closed_trade_records", []),
                    )
        comparison.append(row)
    if backtest_store is not None:
        backtest_store.close()

    manifest = {
        "run_id": run_id,
        "instrument": args.instrument,
        "timeframe": args.timeframe,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "dataset_hash": dataset_hash,
        "n_bars": len(bars),
        "split": {
            "train": len(split.train),
            "validation": len(split.validation),
            "holdout": len(split.holdout),
        },
        "fast_ema_period": 10,
        "slow_ema_period": 20,
        "lookback": args.lookback,
        "random_seed": 42,
        "git_commit": _git_commit(),
        "risk_limits_sha256": _file_hash(REPO_ROOT / "config" / "risk_limits.yaml"),
        "universe_sha256": universe_sha256,
        "llm_cache_ready": llm_ready,
        "data_source": "csv" if args.csv else "binance_public_klines",
        "data_source_note": (
            "Historical klines from Binance public API. universe.yaml venue=KRAKEN "
            "is execution routing for later phases, not the backtest data vendor."
        ),
    }
    write_json(report_dir / "manifest.json", manifest)
    write_json(report_dir / "walk_forward.json", wf_metrics)
    write_json(report_dir / "holdout_comparison.json", comparison)
    print(f"Wrote {report_dir}")
    print(json_dumps_brief(manifest, comparison))


def json_dumps_brief(manifest: dict, comparison: list) -> str:
    import json

    return json.dumps({"manifest": manifest, "holdout": comparison}, indent=2, default=str)


if __name__ == "__main__":
    main()
