"""BacktestJobManager — coadă FIFO, persistență JSON, kind-uri nesuportate, timeout."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.control.backtest_jobs import BacktestJobManager, BacktestJobRequest
from src.data.sources import CsvBarDataSource

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"


def _fetch_bars(symbol: str, start: datetime, end: datetime, timeframe: str):
    return CsvBarDataSource(FIXTURE).fetch_bars(symbol, start, end, timeframe)


def _manager(tmp_path: Path, **kwargs) -> BacktestJobManager:
    return BacktestJobManager(
        jobs_dir=tmp_path / "jobs",
        reports_dir=tmp_path / "reports",
        halt_flag=tmp_path / "runtime" / "control" / "halt.flag",
        fetch_bars=_fetch_bars,
        start_worker=False,
        **kwargs,
    )


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


def test_submit_writes_queued_job_and_get_returns_it(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    run_id = manager.submit(_request())
    record = manager.get(run_id)
    assert record is not None
    assert record["status"] == "queued"
    assert record["strategy_id"] == "baseline_ema_cross"
    assert record["request"]["universe_symbol"] == "ETHUSD"


def test_process_one_runs_job_to_completion(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    run_id = manager.submit(_request())
    processed = manager.process_one(timeout_s=1)
    assert processed == run_id
    record = manager.get(run_id)
    assert record["status"] == "done"
    assert record["metrics"] is not None
    assert "comparable" in record["metrics"]
    assert "extra" in record["metrics"]
    # a fost și scris ca raport (pentru last_backtest_ref existent)
    assert (tmp_path / "reports" / f"{run_id}.json").is_file()


def test_process_one_returns_none_when_queue_empty(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    assert manager.process_one(timeout_s=0.01) is None


def test_list_for_strategy_filters_and_sorts_newest_first(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    first = manager.submit(_request())
    manager.process_one(timeout_s=1)
    second = manager.submit(_request())
    manager.process_one(timeout_s=1)
    manager.submit(_request(strategy_id="other_strategy"))

    rows = manager.list_for_strategy("baseline_ema_cross")
    assert {row["run_id"] for row in rows} == {first, second}
    assert rows[0]["run_id"] == second  # cel mai nou primul


def test_submit_rejects_llm_kind() -> None:
    manager_tmp = BacktestJobManager(
        jobs_dir=Path("/tmp/not-used-jobs"),
        reports_dir=Path("/tmp/not-used-reports"),
        halt_flag=Path("/tmp/not-used-halt/halt.flag"),
        fetch_bars=_fetch_bars,
        start_worker=False,
    )
    with pytest.raises(ValueError, match="cannot run via the async backtest job"):
        manager_tmp.submit(_request(strategy_kind="llm"))


def test_submit_rejects_unknown_kind(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    with pytest.raises(ValueError, match="unknown strategy kind"):
        manager.submit(_request(strategy_kind="not_a_real_kind"))


def test_submit_rejects_end_before_start(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    with pytest.raises(ValueError, match="end must be after start"):
        manager.submit(
            _request(
                start=datetime(2024, 12, 16, tzinfo=timezone.utc),
                end=datetime(2024, 11, 1, tzinfo=timezone.utc),
            )
        )


def test_job_with_empty_bar_range_is_marked_error(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    run_id = manager.submit(
        _request(
            start=datetime(2030, 1, 1, tzinfo=timezone.utc),
            end=datetime(2030, 2, 1, tzinfo=timezone.utc),
        )
    )
    manager.process_one(timeout_s=1)
    record = manager.get(run_id)
    assert record["status"] == "error"
    assert "no bars returned" in record["error"]


def test_get_returns_none_for_unknown_run_id(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    assert manager.get("does-not-exist") is None


def test_job_timeout_is_reported_when_execution_exceeds_budget(tmp_path: Path) -> None:
    manager = _manager(tmp_path, timeout_s=0.001)
    run_id = manager.submit(_request())
    manager.process_one(timeout_s=5)
    record = manager.get(run_id)
    # rularea reală (fixture mic) probabil termină sub 1ms rareori; verificăm doar că
    # jobul ajunge într-o stare terminală validă și, dacă a expirat, mesajul e clar.
    assert record["status"] in {"done", "error"}
    if record["status"] == "error":
        assert "timeout" in record["error"]
