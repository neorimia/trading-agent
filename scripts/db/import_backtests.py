"""Idempotent import of on-disk backtest/paper-run history into PostgreSQL.

Reconstructs design Phase 6 (`backtest_runs`, `backtest_trades`, `paper_trading_runs`,
docs/database-design.md §8.6) from three on-disk sources, modeled on
`scripts/db/import_execution.py` / `scripts/db/import_market_data.py` (same
idempotent-rerun, "never guess", JSON-report contract):

1. `--backtests-root/jobs/*.json` — `src/control/backtest_jobs.py::BacktestJobManager`
   async job records (any status). Natural key: `run_id` (a `uuid4().hex` string)
   becomes the row's `backtest_run_id` PK directly (`ON CONFLICT DO NOTHING`).
2. `--backtests-root/reports/<run_id>/manifest.json` — CLI suite runs
   (`scripts/backtest/run_backtest.py`). One row per sibling
   `metrics_{kind}_{multiplier}x.json` in that directory. Natural key:
   `uuid5(_SUITE_NAMESPACE, f"{suite_run_id}|{kind}|{multiplier}")`.
3. `--runtime-root/paper*/paper_run_summary.json` — one `paper_trading_runs` row per
   matched directory, keyed by the already-seeded `portfolios.name` (`UNIQUE
   (portfolio_id)`, so re-importing the same frozen file always upserts the same row
   instead of accumulating).

`--runtime-root` must be a **frozen copy** (e.g. `cp -r runtime /tmp/runtime-frozen`),
never the live `runtime/` tree, exactly like `import_execution.py`'s `--runtime-root`
discipline. `backtests/reports/` is gitignored (`.gitignore` `backtests/reports/*`) —
tests use a frozen fixture copy, not the live directory.

Documented gaps (never fabricated):

- Job JSON never records `universe_sha256` (the field predates this import; going-
  forward writes via `src/engine/backtest_store.py` set it directly, bypassing JSON).
  The importer hashes the *current* `config/universe.yaml` and counts the row under
  `universe_sha256_reconstructed_count` instead of inventing a historical value.
- `metrics_{kind}_{multiplier}x.json` (CLI suite) only ever contains
  `BacktestMetrics.comparable()` — never `.extra.closed_trade_records` — so CLI-suite
  trades are always `trades_not_reconstructable`, never guessed from `decisions`/PnL.
  Job JSON *does* carry `metrics.extra.closed_trade_records` for jobs run after this
  Phase 6 change (`src/engine/backtest_runner.py::_build_extra_metrics`); those are
  real recorded trades, not reconstructed, and are imported as such.
- A job whose `metrics.comparable.dataset_hash` is missing (errored before running)
  is quarantined `dataset_hash_missing`, not synthesized — `backtest_runs.dataset_hash`
  is NOT NULL and this codebase's importers never write a guessed placeholder for a
  NOT NULL column.
- `paper_trading_runs.config_snapshot` for an imported (historical) run is built from
  the *current* `paper_trading.yaml`/`risk_limits.yaml`, not the config in effect when
  that frozen directory last ran (not persisted anywhere) — the snapshot dict marks
  `"reconstructed_from_current_config": true` so this is never mistaken for the
  historical config.
- `paper_trading_runs.sessions_count` is set to the frozen summary's `n_sessions`
  verbatim (not incremented) so reruns on the same frozen file are idempotent —
  see `src/execution/postgres_store.py::PostgresPaperRunStore.upsert_run`.

Idempotency: rerunning on the same frozen inputs must not change any destination
count. Job/CLI-suite runs use `ON CONFLICT (backtest_run_id) DO NOTHING`; trades are
only inserted the first time their parent run row is created (never re-inserted on a
rerun, so a partial dataset never gets duplicate trades either); paper runs UPSERT on
`portfolio_id`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import yaml
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.db.seed import seed_execution_reference_data
from src.db.config import require_database_url
from src.db.pool import close_database_pools
from src.execution.postgres_store import (
    PostgresPaperRunStore,
    resolve_active_strategy_version_id,
    resolve_portfolio_id,
)

# Fixed namespace for deriving CLI-suite child backtest_run_ids
# (uuid5(_SUITE_NAMESPACE, f"{suite_run_id}|{kind}|{multiplier}")) — stable across
# reruns and across machines, unlike uuid4.
_SUITE_NAMESPACE = uuid.UUID("6e9b6f2e-8e1a-4a7b-9c3d-2f1a5b7c9d0e")
_METRICS_FILENAME_RE = re.compile(r"^metrics_(?P<kind>[a-z_]+)_(?P<multiplier>\d+)x\.json$")
_JOB_STATUS_TO_RUN_STATUS = {
    "queued": "queued",
    "running": "running",
    "done": "completed",
    "error": "failed",
}


class QuarantineWriter:
    """JSONL sink, truncated at construction so a rerun on the same frozen copy
    reproduces the same file instead of accumulating duplicates across
    invocations (same discipline as `scripts/db/import_execution.py`)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: list[dict[str, Any]] = []

    def add(self, reason: str, **detail: Any) -> None:
        self._entries.append({"reason": reason, **detail})

    def flush(self) -> int:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            for entry in self._entries:
                handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
        return len(self._entries)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else None


def _universe_sha256(universe_path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(universe_path.read_bytes())
    return digest.hexdigest()


def _resolve_instrument_id(connection: Any, symbol: str) -> Any:
    row = connection.execute(
        "SELECT instrument_id FROM instruments WHERE canonical_symbol = %s", (symbol,)
    ).fetchone()
    return row["instrument_id"] if row is not None else None


def _resolve_active_strategy_version_id(connection: Any, strategy_id: str) -> Any:
    row = connection.execute(
        """
        SELECT strategy_version_id FROM strategy_versions
        WHERE strategy_id = %s AND is_active = true
        ORDER BY version DESC LIMIT 1
        """,
        (strategy_id,),
    ).fetchone()
    return row["strategy_version_id"] if row is not None else None


def _insert_run_row(
    connection: Any,
    *,
    backtest_run_id: uuid.UUID,
    strategy_version_id: Any,
    instrument_id: Any,
    timeframe: str,
    period_start: datetime,
    period_end: datetime,
    dataset_hash: str,
    universe_sha256: str,
    random_seed: int | None,
    status: str,
    metrics: dict[str, Any] | None,
    report_path: str | None,
    dry_run: bool,
) -> bool:
    """Returns `True` if this call created the row (fresh import); `False` if it
    already existed (idempotent rerun) — either way the row is present unless
    `dry_run`."""
    existing = connection.execute(
        "SELECT 1 FROM backtest_runs WHERE backtest_run_id = %s", (backtest_run_id,)
    ).fetchone()
    if existing is not None or dry_run:
        return existing is None
    connection.execute(
        """
        INSERT INTO backtest_runs (
            backtest_run_id, strategy_version_id, instrument_id, timeframe,
            period_start, period_end, dataset_hash, universe_sha256, random_seed,
            status, metrics, report_path,
            finished_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
            CASE WHEN %s IN ('completed', 'failed') THEN now() ELSE NULL END
        )
        ON CONFLICT (backtest_run_id) DO NOTHING
        """,
        (
            backtest_run_id,
            strategy_version_id,
            instrument_id,
            timeframe,
            period_start,
            period_end,
            dataset_hash,
            universe_sha256,
            random_seed,
            status,
            json.dumps(metrics, default=str) if metrics is not None else None,
            report_path,
            status,
        ),
    )
    return True


def _insert_trade_rows(
    connection: Any,
    *,
    backtest_run_id: uuid.UUID,
    instrument_id: Any,
    records: list[dict[str, Any]],
    dry_run: bool,
) -> int:
    if not records or dry_run:
        return 0
    for record in records:
        connection.execute(
            """
            INSERT INTO backtest_trades (
                backtest_run_id, instrument_id, side, entry_time, entry_price,
                exit_time, exit_price, quantity, pnl, fees, exit_reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                backtest_run_id,
                instrument_id,
                record["side"],
                record["entry_time"],
                Decimal(str(record["entry_price"])),
                record.get("exit_time"),
                Decimal(str(record["exit_price"])) if record.get("exit_price") is not None else None,
                Decimal(str(record["quantity"])),
                Decimal(str(record["pnl"])) if record.get("pnl") is not None else None,
                Decimal(str(record.get("fees", "0"))),
                record.get("exit_reason"),
            ),
        )
    return len(records)


def _import_jobs(
    connection: Any,
    *,
    jobs_dir: Path,
    reports_dir: Path,
    universe_sha256_current: str,
    quarantine: QuarantineWriter,
    dry_run: bool,
) -> dict[str, int]:
    counts = {"created": 0, "existing": 0, "trades_imported": 0, "trades_not_reconstructable": 0}
    if not jobs_dir.is_dir():
        return counts
    for path in sorted(jobs_dir.glob("*.json")):
        if path.suffix == ".tmp":
            continue
        record = _read_json(path)
        if record is None or not isinstance(record.get("request"), dict):
            continue
        run_id_raw = str(record.get("run_id") or "")
        try:
            backtest_run_id = uuid.UUID(hex=run_id_raw)
        except ValueError:
            quarantine.add("invalid_run_id", path=str(path), run_id=run_id_raw)
            continue
        request = record["request"]
        universe_symbol = str(request.get("universe_symbol") or "")
        instrument_id = _resolve_instrument_id(connection, universe_symbol)
        if instrument_id is None:
            quarantine.add("unmapped_symbol", stage="job", run_id=run_id_raw, instrument=universe_symbol)
            continue
        strategy_version_id = _resolve_active_strategy_version_id(
            connection, str(record.get("strategy_id") or "")
        )
        if strategy_version_id is None:
            quarantine.add(
                "unmapped_strategy_version",
                stage="job",
                run_id=run_id_raw,
                strategy_id=record.get("strategy_id"),
            )
            continue
        job_status = str(record.get("status") or "")
        status = _JOB_STATUS_TO_RUN_STATUS.get(job_status)
        if status is None:
            quarantine.add("unknown_job_status", run_id=run_id_raw, status=job_status)
            continue
        metrics_payload = record.get("metrics") if isinstance(record.get("metrics"), dict) else None
        comparable = (metrics_payload or {}).get("comparable") if metrics_payload else None
        dataset_hash = (comparable or {}).get("dataset_hash")
        # `backtest_runs.dataset_hash` is NOT NULL. The job JSON only ever carries it
        # inside `metrics.comparable` (set on the `done` success path in
        # `BacktestJobManager._process`); `queued`/`running`/`error` records never
        # populate `metrics`, so they are always quarantined here rather than
        # inserted with a guessed/blank hash — never guess into a NOT NULL column.
        if not dataset_hash:
            quarantine.add("dataset_hash_missing", run_id=run_id_raw, job_status=job_status)
            continue
        report_path = reports_dir / f"{run_id_raw}.json"
        created = _insert_run_row(
            connection,
            backtest_run_id=backtest_run_id,
            strategy_version_id=strategy_version_id,
            instrument_id=instrument_id,
            timeframe=str(request.get("timeframe") or ""),
            period_start=datetime.fromisoformat(request["start"]),
            period_end=datetime.fromisoformat(request["end"]),
            dataset_hash=dataset_hash,
            universe_sha256=universe_sha256_current,
            random_seed=None,
            status=status,
            metrics=metrics_payload,
            report_path=str(report_path) if report_path.is_file() else str(path),
            dry_run=dry_run,
        )
        counts["created" if created else "existing"] += 1
        if not created:
            continue
        extra = (metrics_payload or {}).get("extra") if metrics_payload else None
        records = (extra or {}).get("closed_trade_records")
        if records:
            counts["trades_imported"] += _insert_trade_rows(
                connection,
                backtest_run_id=backtest_run_id,
                instrument_id=instrument_id,
                records=records,
                dry_run=dry_run,
            )
        else:
            counts["trades_not_reconstructable"] += 1
    return counts


def _import_cli_suites(
    connection: Any,
    *,
    reports_dir: Path,
    quarantine: QuarantineWriter,
    dry_run: bool,
) -> dict[str, int]:
    counts = {"created": 0, "existing": 0, "trades_not_reconstructable": 0}
    strategy_ids = {"baseline": "baseline_ema_cross", "llm": "llm_assisted"}
    if not reports_dir.is_dir():
        return counts
    for manifest_path in sorted(reports_dir.glob("*/manifest.json")):
        manifest = _read_json(manifest_path)
        if manifest is None:
            continue
        suite_run_id = str(manifest.get("run_id") or manifest_path.parent.name)
        instrument = str(manifest.get("instrument") or "")
        instrument_id = _resolve_instrument_id(connection, instrument)
        if instrument_id is None:
            quarantine.add("unmapped_symbol", stage="cli_suite", suite_run_id=suite_run_id, instrument=instrument)
            continue
        dataset_hash = manifest.get("dataset_hash")
        universe_sha256 = manifest.get("universe_sha256")
        if not dataset_hash or not universe_sha256:
            quarantine.add("manifest_missing_hash", suite_run_id=suite_run_id)
            continue
        period_start = datetime.fromisoformat(str(manifest["start"]))
        period_end = datetime.fromisoformat(str(manifest["end"]))
        timeframe = str(manifest.get("timeframe") or "")
        random_seed = manifest.get("random_seed")
        for metrics_path in sorted(manifest_path.parent.glob("metrics_*.json")):
            match = _METRICS_FILENAME_RE.match(metrics_path.name)
            if match is None:
                continue
            kind = match.group("kind")
            multiplier = int(match.group("multiplier"))
            strategy_id = strategy_ids.get(kind)
            if strategy_id is None:
                quarantine.add("unknown_strategy_kind", suite_run_id=suite_run_id, kind=kind)
                continue
            strategy_version_id = _resolve_active_strategy_version_id(connection, strategy_id)
            if strategy_version_id is None:
                quarantine.add(
                    "unmapped_strategy_version",
                    stage="cli_suite",
                    suite_run_id=suite_run_id,
                    strategy_id=strategy_id,
                )
                continue
            backtest_run_id = uuid.uuid5(
                _SUITE_NAMESPACE, f"{suite_run_id}|{kind}|{multiplier}"
            )
            metrics_content = _read_json(metrics_path) or {}
            created = _insert_run_row(
                connection,
                backtest_run_id=backtest_run_id,
                strategy_version_id=strategy_version_id,
                instrument_id=instrument_id,
                timeframe=timeframe,
                period_start=period_start,
                period_end=period_end,
                dataset_hash=str(dataset_hash),
                universe_sha256=str(universe_sha256),
                random_seed=int(random_seed) if random_seed is not None else None,
                status="completed",
                metrics={
                    "suite_run_id": suite_run_id,
                    "period_bounds_note": (
                        "period_start/period_end are the full manifest window, "
                        "not the exact holdout sub-window (not persisted on disk)"
                    ),
                    **metrics_content,
                },
                report_path=str(metrics_path),
                dry_run=dry_run,
            )
            counts["created" if created else "existing"] += 1
            if created:
                # metrics_{kind}_{Nx}.json never carries closed_trade_records
                # (module docstring) — always not-reconstructable for this source.
                counts["trades_not_reconstructable"] += 1
    return counts


def _import_paper_runs(
    database_url: str,
    *,
    runtime_root: Path,
    strategy_id: str,
    paper_config_path: Path,
    risk_limits_path: Path,
    quarantine: QuarantineWriter,
    dry_run: bool,
) -> dict[str, int]:
    counts = {"upserted": 0, "skipped": 0}
    if not runtime_root.is_dir():
        return counts
    strategy_version_id = resolve_active_strategy_version_id(database_url, strategy_id)
    if strategy_version_id is None:
        quarantine.add("unmapped_strategy_version", stage="paper", strategy_id=strategy_id)
        return counts

    paper_raw: dict[str, Any] = {}
    if paper_config_path.is_file():
        paper_raw = yaml.safe_load(paper_config_path.read_text(encoding="utf-8")) or {}
    risk_raw: dict[str, Any] = {}
    if risk_limits_path.is_file():
        risk_raw = yaml.safe_load(risk_limits_path.read_text(encoding="utf-8")) or {}

    for candidate in sorted(runtime_root.glob("paper*")):
        summary_path = candidate / "paper_run_summary.json"
        summary = _read_json(summary_path)
        if summary is None:
            continue
        portfolio_name = candidate.name
        try:
            portfolio_id = resolve_portfolio_id(database_url, portfolio_name)
        except ValueError:
            quarantine.add("unmapped_portfolio", portfolio_name=portfolio_name)
            counts["skipped"] += 1
            continue
        instrument = str(summary.get("instrument") or "")
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            instrument_id = _resolve_instrument_id(connection, instrument)
        if instrument_id is None:
            quarantine.add(
                "unmapped_symbol", stage="paper", portfolio_name=portfolio_name, instrument=instrument
            )
            counts["skipped"] += 1
            continue
        if dry_run:
            counts["upserted"] += 1
            continue
        halted = bool(summary.get("halted"))
        halt_reason = None
        if halted:
            halt_reason = next(
                (s.get("notes") for s in summary.get("sessions", []) if s.get("halted")),
                None,
            )
        store = PostgresPaperRunStore(database_url)
        try:
            store.upsert_run(
                portfolio_id=portfolio_id,
                strategy_version_id=strategy_version_id,
                instrument=instrument,
                config_snapshot={
                    "paper_trading": paper_raw,
                    "risk_limits": risk_raw,
                    "reconstructed_from_current_config": True,
                },
                status="halted" if halted else "running",
                halt_reason=halt_reason,
                summary=summary,
                sessions_count=int(summary.get("n_sessions") or 0),
            )
        finally:
            store.close()
        counts["upserted"] += 1
    return counts


def _destination_counts(database_url: str) -> dict[str, int]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return {
            "backtest_runs": connection.execute(
                "SELECT count(*) AS count FROM backtest_runs"
            ).fetchone()["count"],
            "backtest_trades": connection.execute(
                "SELECT count(*) AS count FROM backtest_trades"
            ).fetchone()["count"],
            "paper_trading_runs": connection.execute(
                "SELECT count(*) AS count FROM paper_trading_runs"
            ).fetchone()["count"],
        }


def import_backtests(
    *,
    database_url: str,
    backtests_root: Path,
    runtime_root: Path | None,
    paper_strategy_id: str | None,
    universe_path: Path = REPO_ROOT / "config" / "universe.yaml",
    strategies_path: Path = REPO_ROOT / "config" / "strategies.yaml",
    strategy_versions_dir: Path = REPO_ROOT / "config" / "strategy_versions",
    risk_limits_path: Path = REPO_ROOT / "config" / "risk_limits.yaml",
    paper_config_path: Path = REPO_ROOT / "config" / "paper_trading.yaml",
    quarantine_path: Path,
    dry_run: bool,
) -> dict[str, Any]:
    if runtime_root is not None and not paper_strategy_id:
        raise ValueError("paper_strategy_id is required when runtime_root is given")
    quarantine = QuarantineWriter(quarantine_path)
    universe_sha256_current = _universe_sha256(universe_path)

    if not dry_run:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            seed_execution_reference_data(
                connection,
                strategies_path=strategies_path,
                strategy_versions_dir=strategy_versions_dir,
                risk_limits_path=risk_limits_path,
                paper_config_path=paper_config_path,
            )

    jobs_dir = backtests_root / "jobs"
    reports_dir = backtests_root / "reports"
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.transaction():
            job_counts = _import_jobs(
                connection,
                jobs_dir=jobs_dir,
                reports_dir=reports_dir,
                universe_sha256_current=universe_sha256_current,
                quarantine=quarantine,
                dry_run=dry_run,
            )
            suite_counts = _import_cli_suites(
                connection,
                reports_dir=reports_dir,
                quarantine=quarantine,
                dry_run=dry_run,
            )

    paper_counts = {"upserted": 0, "skipped": 0}
    if runtime_root is not None:
        assert paper_strategy_id is not None
        paper_counts = _import_paper_runs(
            database_url,
            runtime_root=runtime_root,
            strategy_id=paper_strategy_id,
            paper_config_path=paper_config_path,
            risk_limits_path=risk_limits_path,
            quarantine=quarantine,
            dry_run=dry_run,
        )

    quarantine_count = quarantine.flush()
    destination = {"backtest_runs": None, "backtest_trades": None, "paper_trading_runs": None}
    if not dry_run:
        destination = _destination_counts(database_url)

    return {
        "dry_run": dry_run,
        "backtests_root": str(backtests_root),
        "runtime_root": str(runtime_root) if runtime_root else None,
        "jobs_imported": job_counts,
        "cli_suites_imported": suite_counts,
        "paper_runs_imported": paper_counts,
        "universe_sha256_reconstructed_count": job_counts.get("created", 0),
        "destination": destination,
        "quarantine_path": str(quarantine_path),
        "quarantine_count": quarantine_count,
        "idempotent_key": (
            "backtest_runs.backtest_run_id = job run_id (jobs) or "
            "uuid5(suite_run_id, kind, multiplier) (cli suites); "
            "paper_trading_runs UNIQUE(portfolio_id)"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("MIGRATION_DATABASE_URL"))
    parser.add_argument(
        "--backtests-root",
        type=Path,
        default=REPO_ROOT / "backtests",
        help="Frozen copy containing jobs/ and reports/ (or the live tree in dev)",
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=None,
        help="Frozen copy of the runtime/ tree containing paper*/ subdirs (optional)",
    )
    parser.add_argument(
        "--paper-strategy-id",
        default=None,
        help="Required with --runtime-root — paper_run_summary.json carries no strategy identity",
    )
    parser.add_argument("--universe", type=Path, default=REPO_ROOT / "config/universe.yaml")
    parser.add_argument("--strategies", type=Path, default=REPO_ROOT / "config/strategies.yaml")
    parser.add_argument(
        "--strategy-versions", type=Path, default=REPO_ROOT / "config/strategy_versions"
    )
    parser.add_argument("--risk-limits", type=Path, default=REPO_ROOT / "config/risk_limits.yaml")
    parser.add_argument(
        "--paper-config", type=Path, default=REPO_ROOT / "config/paper_trading.yaml"
    )
    parser.add_argument("--quarantine", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    url = require_database_url(args.database_url, variable="MIGRATION_DATABASE_URL")
    quarantine_path = args.quarantine or (
        (args.report.parent if args.report else Path.cwd()) / "backtests-quarantine.jsonl"
    )
    report = import_backtests(
        database_url=url,
        backtests_root=args.backtests_root,
        runtime_root=args.runtime_root,
        paper_strategy_id=args.paper_strategy_id,
        universe_path=args.universe,
        strategies_path=args.strategies,
        strategy_versions_dir=args.strategy_versions,
        risk_limits_path=args.risk_limits,
        paper_config_path=args.paper_config,
        quarantine_path=quarantine_path,
        dry_run=args.dry_run,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    close_database_pools()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
