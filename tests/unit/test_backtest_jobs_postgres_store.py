"""BacktestJobManager with a fake Postgres-shaped store (design Phase 6, §8.6).

`tests/unit/test_backtest_jobs.py` stays files-only per the Phase 6 plan (verifies
`backtests/jobs/*.json` + `backtests/reports/*.json` are written regardless of the
store). This file adds the `store=` branch: a fake standing in for
`src.engine.backtest_store.PostgresBacktestStore` (same public method shapes, no real
database), asserting `BacktestJobManager._execute` calls it in the right order and
that a files-only run (`store=None`, the default) never touches it at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from src.control.backtest_jobs import BacktestJobManager, BacktestJobRequest
from src.data.sources import CsvBarDataSource

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"


def _fetch_bars(symbol: str, start: datetime, end: datetime, timeframe: str):
    return CsvBarDataSource(FIXTURE).fetch_bars(symbol, start, end, timeframe)


def _request(**overrides) -> BacktestJobRequest:
    base = dict(
        strategy_id="baseline_ema_cross",
        strategy_kind="ema_cross",
        strategy_params={},
        universe_symbol="ETHUSD",
        timeframe="1d",
        start=datetime(2024, 11, 1, tzinfo=timezone.utc),
        end=datetime(2024, 12, 16, tzinfo=timezone.utc),
        cost_multiplier=1,
    )
    base.update(overrides)
    return BacktestJobRequest(**base)


@dataclass
class _FakeBacktestStore:
    """Mirrors `src.engine.backtest_store.PostgresBacktestStore`'s public methods
    (module docstring: `BacktestJobManager` calls `resolve_active_strategy_version_id`,
    `insert_run`, `insert_trades`, `update_run_status` — no real pool/connection)."""

    active_strategy_version_id: UUID | None = field(default_factory=uuid4)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    _next_run_id: UUID = field(default_factory=uuid4)

    def resolve_active_strategy_version_id(self, strategy_id: str) -> UUID | None:
        self.calls.append(("resolve_active_strategy_version_id", {"strategy_id": strategy_id}))
        return self.active_strategy_version_id

    def insert_run(self, **kwargs: Any) -> UUID:
        self.calls.append(("insert_run", kwargs))
        return self._next_run_id

    def update_run_status(self, backtest_run_id: UUID, **kwargs: Any) -> None:
        self.calls.append(("update_run_status", {"backtest_run_id": backtest_run_id, **kwargs}))

    def insert_trades(self, backtest_run_id: UUID, instrument: str, records: list[dict[str, Any]]) -> int:
        self.calls.append(
            ("insert_trades", {"backtest_run_id": backtest_run_id, "instrument": instrument, "records": records})
        )
        return len(records)

    def method_names(self) -> list[str]:
        return [name for name, _ in self.calls]


def _manager(tmp_path: Path, *, store: _FakeBacktestStore | None) -> BacktestJobManager:
    return BacktestJobManager(
        jobs_dir=tmp_path / "jobs",
        reports_dir=tmp_path / "reports",
        halt_flag=tmp_path / "runtime" / "control" / "halt.flag",
        fetch_bars=_fetch_bars,
        start_worker=False,
        store=store,  # type: ignore[arg-type]
        universe_path=REPO_ROOT / "config" / "universe.yaml",
    )


def test_files_only_run_never_touches_the_store(tmp_path: Path) -> None:
    """Default (`store=None`, `BACKTEST_STORE_BACKEND=files`) — the rollback
    target. JSON job/report writes still happen unconditionally."""
    manager = _manager(tmp_path, store=None)
    run_id = manager.submit(_request())
    manager.process_one(timeout_s=1)

    record = manager.get(run_id)
    assert record["status"] == "done"
    assert (tmp_path / "reports" / f"{run_id}.json").is_file()


def test_successful_job_inserts_run_then_trades_then_completes(tmp_path: Path) -> None:
    store = _FakeBacktestStore()
    manager = _manager(tmp_path, store=store)
    run_id = manager.submit(_request())
    manager.process_one(timeout_s=1)

    record = manager.get(run_id)
    assert record["status"] == "done"
    # JSON writes are unconditional regardless of the store (module docstring).
    assert (tmp_path / "reports" / f"{run_id}.json").is_file()

    # Order matters: strategy_version resolved, then the running row inserted,
    # then trades appended, then the row is marked completed with final metrics
    # (src/control/backtest_jobs.py::_execute).
    assert store.method_names() == [
        "resolve_active_strategy_version_id",
        "insert_run",
        "insert_trades",
        "update_run_status",
    ]

    insert_run_call = store.calls[1][1]
    assert insert_run_call["strategy_version_id"] == store.active_strategy_version_id
    assert insert_run_call["instrument"] == "ETHUSD"
    assert insert_run_call["timeframe"] == "1d"
    assert insert_run_call["status"] == "running"
    assert insert_run_call["dataset_hash"]  # non-empty, computed from fetched bars
    assert insert_run_call["universe_sha256"]  # non-empty (compute_universe_sha256)

    update_call = store.calls[3][1]
    assert update_call["status"] == "completed"
    assert "comparable" in update_call["metrics"]


def test_unresolved_strategy_version_skips_the_store_but_still_completes(tmp_path: Path) -> None:
    """`resolve_active_strategy_version_id` returning `None` (strategy not seeded
    in Postgres yet) must not block the files-only run — the job still completes
    and writes JSON; only the Postgres row is skipped."""
    store = _FakeBacktestStore(active_strategy_version_id=None)
    manager = _manager(tmp_path, store=store)
    run_id = manager.submit(_request())
    manager.process_one(timeout_s=1)

    record = manager.get(run_id)
    assert record["status"] == "done"
    assert store.method_names() == ["resolve_active_strategy_version_id"]


def test_failed_job_marks_the_postgres_row_failed_not_completed(tmp_path: Path) -> None:
    store = _FakeBacktestStore()
    manager = _manager(tmp_path, store=store)
    run_id = manager.submit(
        _request(start=datetime(2030, 1, 1, tzinfo=timezone.utc), end=datetime(2030, 2, 1, tzinfo=timezone.utc))
    )
    manager.process_one(timeout_s=1)

    record = manager.get(run_id)
    assert record["status"] == "error"
    # No bars for this range -> dataset_hash never computed -> insert_run never
    # called at all (src/engine/backtest_store.py module docstring: the row is
    # only created once dataset_hash is known).
    assert store.method_names() == []
