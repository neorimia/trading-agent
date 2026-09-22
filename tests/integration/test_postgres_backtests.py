"""PostgreSQL backtest/paper-run stores: constraints, role isolation, going-forward
determinism, and the importer (design Phase 6, docs/database-design.md §8.6)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from scripts.db.import_backtests import import_backtests
from scripts.db.seed import seed_execution_reference_data, seed_reference_data
from src.data.cache import canonical_dataset_hash
from src.data.sources import CsvBarDataSource
from src.db.pool import close_database_pools
from src.engine.backtest_runner import run_backtest
from src.engine.backtest_store import PostgresBacktestStore, compute_universe_sha256
from src.engine.cost_models import VenueCostConfig
from src.execution.postgres_store import (
    PostgresPaperRunStore,
    resolve_active_strategy_version_id,
    resolve_portfolio_id,
)

pytestmark = pytest.mark.postgres
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_BARS = REPO_ROOT / "tests" / "fixtures" / "bars_ethusd_1d.csv"
STRATEGY_ID = "baseline_ema_cross"


def _admin_database_url() -> str:
    """The migration-owner role, for schema setup/seeding/role-isolation baselines."""
    value = os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("MIGRATION_DATABASE_URL")
    if not value:
        pytest.skip("ADMIN_DATABASE_URL is not configured")
    return value


def _backtest_database_url() -> str:
    """The backtest_writer application role, as production code paths use it."""
    value = os.environ.get("BACKTEST_DATABASE_URL")
    if not value:
        pytest.skip("BACKTEST_DATABASE_URL is not configured")
    return value


def _control_database_url() -> str:
    value = os.environ.get("CONTROL_DATABASE_URL")
    if not value:
        pytest.skip("CONTROL_DATABASE_URL is not configured")
    return value


@pytest.fixture(autouse=True)
def clean_database() -> None:
    url = _admin_database_url()
    close_database_pools()
    with psycopg.connect(url) as connection:
        # backtest_runs/backtest_trades/paper_trading_runs are listed explicitly
        # (not left to CASCADE from strategy_versions/portfolios) so this cleanup
        # stays correct even if those FK targets ever change — same discipline as
        # tests/integration/test_postgres_execution.py's own TRUNCATE list.
        connection.execute(
            """
            TRUNCATE
                alerts, human_approvals, system_events, audit_log, agent_runs,
                backtest_trades, backtest_runs, paper_trading_runs,
                risk_events, executions, order_events, orders, signals,
                positions, balances, strategy_versions, strategies, risk_limits,
                portfolios
            RESTART IDENTITY CASCADE
            """
        )
        seed_reference_data(
            connection,
            universe_path=REPO_ROOT / "config/universe.yaml",
            sources_path=REPO_ROOT / "config/research_sources.yaml",
        )
        seed_execution_reference_data(
            connection,
            strategies_path=REPO_ROOT / "config/strategies.yaml",
            strategy_versions_dir=REPO_ROOT / "config/strategy_versions",
            risk_limits_path=REPO_ROOT / "config/risk_limits.yaml",
            paper_config_path=REPO_ROOT / "config/paper_trading.yaml",
        )
        connection.commit()
    yield
    close_database_pools()


def _bars() -> list:
    return CsvBarDataSource(FIXTURE_BARS).fetch_bars(
        "ETHUSD",
        datetime(2024, 11, 1, tzinfo=timezone.utc),
        datetime(2024, 12, 16, tzinfo=timezone.utc),
        "1d",
    )


def _instrument_id(connection: psycopg.Connection, symbol: str) -> UUID:
    return connection.execute(
        "SELECT instrument_id FROM instruments WHERE canonical_symbol = %s", (symbol,)
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


def test_backtest_runs_status_check_constraint_rejects_invalid_value() -> None:
    admin_url = _admin_database_url()
    strategy_version_id = resolve_active_strategy_version_id(admin_url, STRATEGY_ID)
    with psycopg.connect(admin_url) as connection:
        instrument_id = _instrument_id(connection, "ETHUSD")
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO backtest_runs (
                    strategy_version_id, instrument_id, timeframe, period_start,
                    period_end, dataset_hash, universe_sha256, status
                ) VALUES (%s, %s, '1d', now(), now(), 'hash', 'sha', 'not_a_real_status')
                """,
                (strategy_version_id, instrument_id),
            )


def test_backtest_trades_side_check_constraint_rejects_invalid_value() -> None:
    admin_url = _admin_database_url()
    strategy_version_id = resolve_active_strategy_version_id(admin_url, STRATEGY_ID)
    with psycopg.connect(admin_url) as connection:
        instrument_id = _instrument_id(connection, "ETHUSD")
        run_id = connection.execute(
            """
            INSERT INTO backtest_runs (
                strategy_version_id, instrument_id, timeframe, period_start,
                period_end, dataset_hash, universe_sha256, status
            ) VALUES (%s, %s, '1d', now(), now(), 'hash', 'sha', 'completed')
            RETURNING backtest_run_id
            """,
            (strategy_version_id, instrument_id),
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO backtest_trades (
                    backtest_run_id, instrument_id, side, entry_time, entry_price, quantity
                ) VALUES (%s, %s, 'hold', now(), 100, 1)
                """,
                (run_id, instrument_id),
            )


def test_paper_trading_runs_unique_portfolio_constraint_rejects_duplicate() -> None:
    admin_url = _admin_database_url()
    portfolio_id = resolve_portfolio_id(admin_url, "paper")
    strategy_version_id = resolve_active_strategy_version_id(admin_url, STRATEGY_ID)
    with psycopg.connect(admin_url) as connection:
        instrument_id = _instrument_id(connection, "ETHUSD")

        def insert() -> None:
            connection.execute(
                """
                INSERT INTO paper_trading_runs (
                    portfolio_id, strategy_version_id, instrument_id, config_snapshot
                ) VALUES (%s, %s, %s, '{}'::jsonb)
                """,
                (portfolio_id, strategy_version_id, instrument_id),
            )

        insert()
        with pytest.raises(psycopg.errors.UniqueViolation):
            insert()


# ---------------------------------------------------------------------------
# Going-forward writer (src/engine/backtest_store.py)
# ---------------------------------------------------------------------------


def test_backtest_writer_can_insert_run_update_status_and_insert_trades() -> None:
    admin_url = _admin_database_url()
    strategy_version_id = resolve_active_strategy_version_id(admin_url, STRATEGY_ID)
    bars = _bars()
    dataset_hash = canonical_dataset_hash(bars)
    store = PostgresBacktestStore(_backtest_database_url())

    run_id = store.insert_run(
        strategy_version_id=strategy_version_id,
        instrument="ETHUSD",
        timeframe="1d",
        period_start=bars[0].timestamp,
        period_end=bars[-1].timestamp,
        dataset_hash=dataset_hash,
        universe_sha256="test-sha",
        status="running",
    )
    store.update_run_status(run_id, status="completed", metrics={"comparable": {"n_bars": len(bars)}})
    inserted = store.insert_trades(
        run_id,
        "ETHUSD",
        [
            {
                "side": "buy",
                "entry_time": bars[0].timestamp.isoformat(),
                "entry_price": "2600",
                "exit_time": bars[1].timestamp.isoformat(),
                "exit_price": "2650",
                "quantity": "1",
                "pnl": "50",
                "fees": "0.5",
                "exit_reason": None,
            }
        ],
    )
    assert inserted == 1

    with psycopg.connect(admin_url) as connection:
        status, finished_at, metrics = connection.execute(
            "SELECT status, finished_at, metrics FROM backtest_runs WHERE backtest_run_id = %s",
            (run_id,),
        ).fetchone()
        assert status == "completed"
        assert finished_at is not None
        assert metrics["comparable"]["n_bars"] == len(bars)
        trades_count = connection.execute(
            "SELECT count(*) FROM backtest_trades WHERE backtest_run_id = %s", (run_id,)
        ).fetchone()[0]
        assert trades_count == 1


def test_same_dataset_hash_seed_strategy_produces_identical_trades_on_rerun(tmp_path: Path) -> None:
    """design §19: two runs with the same dataset_hash/random_seed/strategy_version_id
    must produce byte-identical `backtest_trades` — the backtest itself is
    deterministic (no LLM/randomness in the `baseline` kind)."""
    admin_url = _admin_database_url()
    strategy_version_id = resolve_active_strategy_version_id(admin_url, STRATEGY_ID)
    bars = _bars()
    dataset_hash = canonical_dataset_hash(bars)
    universe_sha256 = compute_universe_sha256(REPO_ROOT / "config" / "universe.yaml")
    store = PostgresBacktestStore(_backtest_database_url())

    def run_and_store(halt_name: str) -> UUID:
        metrics = run_backtest(
            bars,
            universe_symbol="ETHUSD",
            timeframe="1d",
            strategy_kind="baseline",
            costs=VenueCostConfig.for_multiplier(1),
            dataset_hash=dataset_hash,
            halt_flag=tmp_path / halt_name,
        )
        run_id = store.insert_run(
            strategy_version_id=strategy_version_id,
            instrument="ETHUSD",
            timeframe="1d",
            period_start=bars[0].timestamp,
            period_end=bars[-1].timestamp,
            dataset_hash=dataset_hash,
            universe_sha256=universe_sha256,
            random_seed=42,
            status="completed",
            metrics={"comparable": metrics.comparable()},
        )
        store.insert_trades(run_id, "ETHUSD", metrics.extra["closed_trade_records"])
        return run_id

    run_id_a = run_and_store("halt-a.flag")
    run_id_b = run_and_store("halt-b.flag")

    def trade_rows(run_id: UUID) -> list[tuple]:
        with psycopg.connect(admin_url) as connection:
            return connection.execute(
                """
                SELECT side, entry_time, entry_price, exit_time, exit_price,
                       quantity, pnl, fees, exit_reason
                FROM backtest_trades WHERE backtest_run_id = %s ORDER BY id
                """,
                (run_id,),
            ).fetchall()

    trades_a = trade_rows(run_id_a)
    trades_b = trade_rows(run_id_b)
    assert len(trades_a) > 0  # sanity: the fixture actually produces round-trip trades
    assert trades_a == trades_b


# ---------------------------------------------------------------------------
# Role isolation (deploy/postgres/create_roles.sql)
# ---------------------------------------------------------------------------


def test_control_reader_can_read_backtest_tables_but_not_write() -> None:
    admin_url = _admin_database_url()
    strategy_version_id = resolve_active_strategy_version_id(admin_url, STRATEGY_ID)
    with psycopg.connect(admin_url) as connection:
        instrument_id = _instrument_id(connection, "ETHUSD")
        connection.execute(
            """
            INSERT INTO backtest_runs (
                strategy_version_id, instrument_id, timeframe, period_start,
                period_end, dataset_hash, universe_sha256, status
            ) VALUES (%s, %s, '1d', now(), now(), 'hash', 'sha', 'completed')
            """,
            (strategy_version_id, instrument_id),
        )

    with psycopg.connect(_control_database_url()) as connection:
        count = connection.execute("SELECT count(*) FROM backtest_runs").fetchone()[0]
        assert count == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "INSERT INTO backtest_runs (backtest_run_id) VALUES (%s)", (uuid4(),)
            )


def test_backtest_writer_cannot_delete_backtest_trades() -> None:
    admin_url = _admin_database_url()
    strategy_version_id = resolve_active_strategy_version_id(admin_url, STRATEGY_ID)
    bars = _bars()
    store = PostgresBacktestStore(_backtest_database_url())
    run_id = store.insert_run(
        strategy_version_id=strategy_version_id,
        instrument="ETHUSD",
        timeframe="1d",
        period_start=bars[0].timestamp,
        period_end=bars[-1].timestamp,
        dataset_hash=canonical_dataset_hash(bars),
        universe_sha256="test-sha",
        status="completed",
    )
    store.insert_trades(
        run_id,
        "ETHUSD",
        [
            {
                "side": "buy",
                "entry_time": bars[0].timestamp.isoformat(),
                "entry_price": "2600",
                "exit_time": bars[1].timestamp.isoformat(),
                "exit_price": "2650",
                "quantity": "1",
                "pnl": "50",
                "fees": "0.5",
                "exit_reason": None,
            }
        ],
    )

    with psycopg.connect(_backtest_database_url()) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "DELETE FROM backtest_trades WHERE backtest_run_id = %s", (run_id,)
            )


# ---------------------------------------------------------------------------
# Importer (scripts/db/import_backtests.py)
# ---------------------------------------------------------------------------


def _write_fixture_backtests_root(root: Path, *, dataset_hash: str) -> tuple[str, str, str]:
    """A frozen `backtests/` copy exercising every importer branch: one `done` job
    with real going-forward trade records, one `error` job with no metrics
    (quarantined `dataset_hash_missing`), one `done` job for an unmapped symbol
    (quarantined `unmapped_symbol`), and one CLI-suite manifest + metrics file
    (PnL-only history, always `trades_not_reconstructable`, module docstring)."""
    jobs_dir = root / "jobs"
    reports_dir = root / "reports"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    done_run_id = uuid4().hex
    request = {
        "strategy_kind": "ema_cross",
        "strategy_params": {},
        "universe_symbol": "ETHUSD",
        "timeframe": "1d",
        "start": "2024-11-01T00:00:00+00:00",
        "end": "2024-12-16T00:00:00+00:00",
        "cost_multiplier": 1,
    }
    done_record = {
        "run_id": done_run_id,
        "strategy_id": STRATEGY_ID,
        "status": "done",
        "created_at": "2026-01-01T00:00:00+00:00",
        "started_at": "2026-01-01T00:00:01+00:00",
        "finished_at": "2026-01-01T00:00:05+00:00",
        "error": None,
        "request": request,
        "metrics": {
            "comparable": {
                "strategy": "ema_cross",
                "cost_multiplier": 1,
                "dataset_hash": dataset_hash,
                "n_bars": 45,
                "n_fills": 2,
                "n_decisions": 3,
                "ending_usdt": "9950.00",
                "commissions_usdt": "1.00",
                "decisions": [],
            },
            "extra": {
                "closed_trade_records": [
                    {
                        "side": "buy",
                        "entry_time": "2024-11-20T23:59:59+00:00",
                        "entry_price": "2638.006",
                        "exit_time": "2024-11-24T23:59:59+00:00",
                        "exit_price": "2495.00",
                        "quantity": "0.15160",
                        "pnl": "-21.67970960",
                        "fees": "0.98",
                        "exit_reason": None,
                    }
                ]
            },
        },
    }
    (jobs_dir / f"{done_run_id}.json").write_text(json.dumps(done_record), encoding="utf-8")
    (reports_dir / f"{done_run_id}.json").write_text(
        json.dumps({**done_record, "report_kind": "backtest_job"}), encoding="utf-8"
    )

    error_run_id = uuid4().hex
    error_record = {
        "run_id": error_run_id,
        "strategy_id": STRATEGY_ID,
        "status": "error",
        "created_at": "2026-01-01T00:00:00+00:00",
        "started_at": "2026-01-01T00:00:01+00:00",
        "finished_at": "2026-01-01T00:00:02+00:00",
        "error": "no bars returned for requested range — cannot backtest",
        "request": {**request, "start": "2030-01-01T00:00:00+00:00", "end": "2030-02-01T00:00:00+00:00"},
        "metrics": None,
    }
    (jobs_dir / f"{error_run_id}.json").write_text(json.dumps(error_record), encoding="utf-8")

    unmapped_run_id = uuid4().hex
    unmapped_record = {
        **done_record,
        "run_id": unmapped_run_id,
        "request": {**request, "universe_symbol": "ZZZUSD"},
    }
    (jobs_dir / f"{unmapped_run_id}.json").write_text(json.dumps(unmapped_record), encoding="utf-8")

    suite_run_id = "20260101T000000Z"
    suite_dir = reports_dir / suite_run_id
    suite_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": suite_run_id,
        "instrument": "ETHUSD",
        "timeframe": "1d",
        "start": "2024-11-01T00:00:00+00:00",
        "end": "2024-12-31T23:59:59+00:00",
        "dataset_hash": dataset_hash,
        "n_bars": 45,
        "random_seed": 42,
        "universe_sha256": "test-suite-sha",
    }
    (suite_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (suite_dir / "metrics_baseline_1x.json").write_text(
        json.dumps(
            {
                "strategy": "baseline",
                "cost_multiplier": 1,
                "dataset_hash": dataset_hash,
                "n_bars": 45,
                "n_fills": 4,
                "n_decisions": 4,
                "ending_usdt": "9900.00",
                "commissions_usdt": "2.00",
                "decisions": [],
            }
        ),
        encoding="utf-8",
    )
    return done_run_id, error_run_id, unmapped_run_id


def _write_fixture_runtime_paper(root: Path, *, portfolio_name: str = "paper") -> None:
    paper_dir = root / portfolio_name
    paper_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": "20260101T000000Z",
        "path": "B",
        "dry_run": True,
        "venue": "KRAKEN",
        "instrument": "ETHUSD",
        "data_source": "csv:fixture",
        "mode": "batch",
        "n_bars": 45,
        "n_sessions": 3,
        "elapsed_s": 1.2345,
        "latency_per_session_s": 0.4115,
        "halted": False,
        "restart_reconciled": None,
        "node_data_clients": ["KRAKEN"],
        "node_exec_clients": ["KRAKEN"],
        "sessions": [
            {
                "session_index": 0,
                "correlation_id": str(uuid4()),
                "bar_timestamp": "2024-11-01T00:00:00+00:00",
                "instrument": "ETHUSD",
                "proposal_direction": "long",
                "rejected_reason": None,
                "risk_approved": True,
                "human_approved": True,
                "order_status": "filled",
                "halted": False,
                "notes": None,
            }
        ],
    }
    (paper_dir / "paper_run_summary.json").write_text(json.dumps(summary), encoding="utf-8")


def test_importer_populates_runs_trades_and_paper_run_with_quarantine(tmp_path: Path) -> None:
    dataset_hash = canonical_dataset_hash(_bars())
    backtests_root = tmp_path / "backtests"
    runtime_root = tmp_path / "runtime"
    _write_fixture_backtests_root(backtests_root, dataset_hash=dataset_hash)
    _write_fixture_runtime_paper(runtime_root)
    admin_url = _admin_database_url()

    report = import_backtests(
        database_url=admin_url,
        backtests_root=backtests_root,
        runtime_root=runtime_root,
        paper_strategy_id=STRATEGY_ID,
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=False,
    )

    assert report["jobs_imported"] == {
        "created": 1,
        "existing": 0,
        "trades_imported": 1,
        "trades_not_reconstructable": 0,
    }
    assert report["cli_suites_imported"] == {
        "created": 1,
        "existing": 0,
        "trades_not_reconstructable": 1,
    }
    assert report["paper_runs_imported"] == {"upserted": 1, "skipped": 0}
    assert report["destination"]["backtest_runs"] == 2
    assert report["destination"]["backtest_trades"] == 1
    assert report["destination"]["paper_trading_runs"] == 1

    quarantine_text = (tmp_path / "quarantine.jsonl").read_text(encoding="utf-8")
    reasons = {
        json.loads(line)["reason"] for line in quarantine_text.splitlines() if line.strip()
    }
    assert reasons == {"dataset_hash_missing", "unmapped_symbol"}

    portfolio_id = resolve_portfolio_id(admin_url, "paper")
    with psycopg.connect(admin_url) as connection:
        sessions_count, status = connection.execute(
            "SELECT sessions_count, status FROM paper_trading_runs WHERE portfolio_id = %s",
            (portfolio_id,),
        ).fetchone()
        assert sessions_count == 3
        assert status == "running"


def test_importer_dry_run_writes_nothing(tmp_path: Path) -> None:
    dataset_hash = canonical_dataset_hash(_bars())
    backtests_root = tmp_path / "backtests"
    runtime_root = tmp_path / "runtime"
    _write_fixture_backtests_root(backtests_root, dataset_hash=dataset_hash)
    _write_fixture_runtime_paper(runtime_root)
    admin_url = _admin_database_url()

    report = import_backtests(
        database_url=admin_url,
        backtests_root=backtests_root,
        runtime_root=runtime_root,
        paper_strategy_id=STRATEGY_ID,
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=True,
    )

    assert report["jobs_imported"]["created"] == 1
    assert report["cli_suites_imported"]["created"] == 1
    assert report["paper_runs_imported"]["upserted"] == 1
    # Dry-run previews the same numbers a real run would produce but writes none
    # of them.
    with psycopg.connect(admin_url) as connection:
        assert connection.execute("SELECT count(*) FROM backtest_runs").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM backtest_trades").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM paper_trading_runs").fetchone()[0] == 0


def test_importer_rerun_on_same_frozen_copy_is_idempotent(tmp_path: Path) -> None:
    dataset_hash = canonical_dataset_hash(_bars())
    backtests_root = tmp_path / "backtests"
    runtime_root = tmp_path / "runtime"
    _write_fixture_backtests_root(backtests_root, dataset_hash=dataset_hash)
    _write_fixture_runtime_paper(runtime_root)
    admin_url = _admin_database_url()
    kwargs = dict(
        database_url=admin_url,
        backtests_root=backtests_root,
        runtime_root=runtime_root,
        paper_strategy_id=STRATEGY_ID,
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=False,
    )

    first = import_backtests(**kwargs)
    second = import_backtests(**kwargs)

    assert first["destination"] == second["destination"]
    # Nothing new was created the second time — jobs/cli-suite rows are found via
    # ON CONFLICT DO NOTHING existence checks, and the paper run UPSERTs the same
    # sessions_count verbatim (never incremented on a rerun).
    assert second["jobs_imported"]["created"] == 0
    assert second["jobs_imported"]["existing"] == 1
    assert second["cli_suites_imported"]["created"] == 0
    assert second["cli_suites_imported"]["existing"] == 1
    assert second["paper_runs_imported"] == {"upserted": 1, "skipped": 0}
    assert second["quarantine_count"] == first["quarantine_count"]


def test_importer_unmapped_portfolio_is_quarantined_not_guessed(tmp_path: Path) -> None:
    dataset_hash = canonical_dataset_hash(_bars())
    backtests_root = tmp_path / "backtests"
    runtime_root = tmp_path / "runtime"
    _write_fixture_backtests_root(backtests_root, dataset_hash=dataset_hash)
    _write_fixture_runtime_paper(runtime_root, portfolio_name="paper-not-a-real-portfolio")
    admin_url = _admin_database_url()

    report = import_backtests(
        database_url=admin_url,
        backtests_root=backtests_root,
        runtime_root=runtime_root,
        paper_strategy_id=STRATEGY_ID,
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=False,
    )

    assert report["paper_runs_imported"] == {"upserted": 0, "skipped": 1}
    quarantine_text = (tmp_path / "quarantine.jsonl").read_text(encoding="utf-8")
    reasons = {
        json.loads(line)["reason"] for line in quarantine_text.splitlines() if line.strip()
    }
    assert "unmapped_portfolio" in reasons
