"""PostgreSQL execution/risk stores: constraints, idempotency window, importer,
and role isolation (design Phase 3+4, docs/database-design.md §8.4-8.9)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from scripts.db.import_execution import import_execution
from scripts.db.seed import seed_execution_reference_data, seed_reference_data
from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent
from src.db.pool import close_database_pools
from src.execution.idempotency_store import DuplicateClientOrderId, IdempotencyStore
from src.execution.postgres_store import (
    PostgresIdempotencyStore,
    PostgresPortfolioStore,
    resolve_active_strategy_version_id,
    resolve_open_risk_limits_version_id,
    resolve_portfolio_id,
)
from src.execution.types import OrderRequest, OrderResult

pytestmark = pytest.mark.postgres
REPO_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_ID = "llm_assisted"


def _admin_database_url() -> str:
    """The migration-owner role, for schema setup/seeding/role-isolation baselines."""
    value = os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("MIGRATION_DATABASE_URL")
    if not value:
        pytest.skip("ADMIN_DATABASE_URL is not configured")
    return value


def _execution_database_url() -> str:
    """The execution_writer application role, as production code paths use it."""
    value = os.environ.get("EXECUTION_DATABASE_URL")
    if not value:
        pytest.skip("EXECUTION_DATABASE_URL is not configured")
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
        # Child-to-parent order respects FKs; CASCADE would also work but being
        # explicit documents the dependency graph for readers.
        connection.execute(
            """
            TRUNCATE
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


def _ids(admin_url: str) -> tuple[UUID, UUID | None, UUID]:
    portfolio_id = resolve_portfolio_id(admin_url, "paper")
    strategy_version_id = resolve_active_strategy_version_id(admin_url, STRATEGY_ID)
    risk_limits_version_id = resolve_open_risk_limits_version_id(admin_url)
    assert risk_limits_version_id is not None
    return portfolio_id, strategy_version_id, risk_limits_version_id


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


def test_orders_status_check_constraint_rejects_invalid_value() -> None:
    admin_url = _admin_database_url()
    portfolio_id, strategy_version_id, risk_limits_version_id = _ids(admin_url)
    with psycopg.connect(admin_url) as connection:
        instrument_id = connection.execute(
            "SELECT instrument_id FROM instruments WHERE canonical_symbol = 'ETHUSD'"
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO orders (
                    order_id, client_order_id, portfolio_id, instrument_id,
                    strategy_version_id, risk_limits_version_id, side, order_type,
                    requested_quantity, trading_mode, status, requested_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 'buy', 'market', 1, 'paper',
                          'not_a_real_status', now())
                """,
                (
                    uuid4(),
                    uuid4(),
                    portfolio_id,
                    instrument_id,
                    strategy_version_id,
                    risk_limits_version_id,
                ),
            )


def test_risk_events_event_type_check_constraint_rejects_invalid_value() -> None:
    admin_url = _admin_database_url()
    _, _, risk_limits_version_id = _ids(admin_url)
    with psycopg.connect(admin_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO risk_events (
                    event_type, reason, portfolio_state_snapshot, risk_limits_version_id,
                    correlation_id
                ) VALUES ('not_a_real_event_type', 'x', '{}'::jsonb, %s, %s)
                """,
                (risk_limits_version_id, uuid4()),
            )


def test_orders_unknown_instrument_is_a_foreign_key_violation() -> None:
    admin_url = _admin_database_url()
    portfolio_id, strategy_version_id, risk_limits_version_id = _ids(admin_url)
    with psycopg.connect(admin_url) as connection:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            connection.execute(
                """
                INSERT INTO orders (
                    order_id, client_order_id, portfolio_id, instrument_id,
                    strategy_version_id, risk_limits_version_id, side, order_type,
                    requested_quantity, trading_mode, status, requested_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 'buy', 'market', 1, 'paper',
                          'submitted', now())
                """,
                (
                    uuid4(),
                    uuid4(),
                    portfolio_id,
                    uuid4(),  # not a real instrument_id
                    strategy_version_id,
                    risk_limits_version_id,
                ),
            )


def test_orders_client_order_id_unique_constraint_rejects_duplicate() -> None:
    admin_url = _admin_database_url()
    portfolio_id, strategy_version_id, risk_limits_version_id = _ids(admin_url)
    client_order_id = uuid4()
    with psycopg.connect(admin_url) as connection:
        instrument_id = connection.execute(
            "SELECT instrument_id FROM instruments WHERE canonical_symbol = 'ETHUSD'"
        ).fetchone()[0]

        def insert(order_id: UUID) -> None:
            connection.execute(
                """
                INSERT INTO orders (
                    order_id, client_order_id, portfolio_id, instrument_id,
                    strategy_version_id, risk_limits_version_id, side, order_type,
                    requested_quantity, trading_mode, status, requested_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 'buy', 'market', 1, 'paper',
                          'submitted', now())
                """,
                (
                    order_id,
                    client_order_id,
                    portfolio_id,
                    instrument_id,
                    strategy_version_id,
                    risk_limits_version_id,
                ),
            )

        insert(uuid4())
        with pytest.raises(psycopg.errors.UniqueViolation):
            insert(uuid4())


# ---------------------------------------------------------------------------
# Idempotency window (PostgresIdempotencyStore mirrors the SQLite IdempotencyStore
# reserve -> store_result -> get_result contract used by OrderGateway)
# ---------------------------------------------------------------------------


def test_postgres_idempotency_reserve_store_result_get_result_roundtrip() -> None:
    admin_url = _admin_database_url()
    portfolio_id, strategy_version_id, risk_limits_version_id = _ids(admin_url)
    store = PostgresIdempotencyStore(
        _execution_database_url(),
        portfolio_id=portfolio_id,
        strategy_version_id=strategy_version_id,
        risk_limits_version_id=risk_limits_version_id,
    )
    client_order_id = uuid4()
    order = OrderRequest(client_order_id=client_order_id, instrument="ETHUSD", side="buy", quantity=Decimal("1"))
    correlation_id = uuid4()

    assert store.get_result(client_order_id) is None
    store.reserve(client_order_id, order=order, correlation_id=correlation_id)

    result = OrderResult(
        client_order_id=client_order_id,
        status="filled",
        filled_quantity=Decimal("1"),
        fill_price=Decimal("2700.5"),
        fee=Decimal("0.5"),
    )
    store.store_result(result)

    loaded = store.get_result(client_order_id)
    assert loaded is not None
    assert loaded.status == "filled"
    assert loaded.filled_quantity == Decimal("1")
    assert loaded.fill_price == Decimal("2700.5")
    # Documented gap (module docstring): broker_order_id has no column, so replay
    # never round-trips it, unlike the SQLite store.
    assert loaded.broker_order_id is None


def test_postgres_idempotency_duplicate_reserve_raises_with_stored_result() -> None:
    admin_url = _admin_database_url()
    portfolio_id, strategy_version_id, risk_limits_version_id = _ids(admin_url)
    store = PostgresIdempotencyStore(
        _execution_database_url(),
        portfolio_id=portfolio_id,
        strategy_version_id=strategy_version_id,
        risk_limits_version_id=risk_limits_version_id,
    )
    client_order_id = uuid4()
    order = OrderRequest(client_order_id=client_order_id, instrument="ETHUSD", side="sell", quantity=Decimal("2"))
    store.reserve(client_order_id, order=order, correlation_id=uuid4())

    # Reserving again before a result exists -> duplicate with stored=None (in-flight).
    with pytest.raises(DuplicateClientOrderId) as exc_info:
        store.reserve(client_order_id, order=order, correlation_id=uuid4())
    assert exc_info.value.stored is None

    store.store_result(
        OrderResult(client_order_id=client_order_id, status="rejected", reason="test")
    )

    # Reserving after a terminal result exists -> duplicate with the stored result
    # attached, exactly like OrderGateway.submit's replay path expects.
    with pytest.raises(DuplicateClientOrderId) as exc_info:
        store.reserve(client_order_id, order=order, correlation_id=uuid4())
    assert exc_info.value.stored is not None
    assert exc_info.value.stored.status == "rejected"


def test_postgres_idempotency_store_result_without_reservation_raises() -> None:
    admin_url = _admin_database_url()
    portfolio_id, strategy_version_id, risk_limits_version_id = _ids(admin_url)
    store = PostgresIdempotencyStore(
        _execution_database_url(),
        portfolio_id=portfolio_id,
        strategy_version_id=strategy_version_id,
        risk_limits_version_id=risk_limits_version_id,
    )
    with pytest.raises(ValueError):
        store.store_result(OrderResult(client_order_id=uuid4(), status="filled"))


# ---------------------------------------------------------------------------
# Importer (scripts/db/import_execution.py)
# ---------------------------------------------------------------------------


def _write_fixture_runtime(root: Path) -> None:
    """A small frozen runtime directory exercising every importer branch:
    an approved+filled order, a rejected proposal, an unmapped-symbol proposal
    (quarantined, not guessed), and one idempotency reservation with no audit
    match (quarantined as unprovable, docs/database-cutover-playbook.md)."""
    audit = AuditLog(root / "audit" / "audit.sqlite")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # Correlation A: approved proposal -> submitted -> filled.
    corr_a = uuid4()
    client_order_id = uuid4()
    audit.record(
        AuditEvent(
            timestamp=base,
            correlation_id=corr_a,
            event_type="proposal",
            payload={
                "instrument": "ETHUSD",
                "direction": "long",
                "confidence": 0.7,
                "rationale": "test rationale A",
            },
        )
    )
    audit.record(
        AuditEvent(
            timestamp=base + timedelta(seconds=1),
            correlation_id=corr_a,
            event_type="risk_decision",
            payload={
                "approved": True,
                "instrument": "ETHUSD",
                "side": "buy",
                "quantity": "0.5",
                "reject_reason": None,
                "requires_human_approval": False,
            },
        )
    )
    audit.record(
        AuditEvent(
            timestamp=base + timedelta(seconds=2),
            correlation_id=corr_a,
            event_type="order_submitted",
            payload={
                "client_order_id": str(client_order_id),
                "status": "filled",
                "filled_quantity": "0.5",
                "fill_price": "2700.0",
                "fee": "0.1",
            },
        )
    )
    audit.record(
        AuditEvent(
            timestamp=base + timedelta(seconds=2, milliseconds=200),
            correlation_id=corr_a,
            event_type="fill",
            payload={
                "client_order_id": str(client_order_id),
                "status": "filled",
                "filled_quantity": "0.5",
                "fill_price": "2700.0",
                "fee": "0.1",
            },
        )
    )

    # Correlation B: rejected proposal (avoid), no order.
    corr_b = uuid4()
    audit.record(
        AuditEvent(
            timestamp=base + timedelta(seconds=3),
            correlation_id=corr_b,
            event_type="proposal",
            payload={
                "instrument": "ETHUSD",
                "direction": "avoid",
                "confidence": 0.2,
                "rationale": "test rationale B",
            },
        )
    )
    audit.record(
        AuditEvent(
            timestamp=base + timedelta(seconds=4),
            correlation_id=corr_b,
            event_type="risk_decision",
            payload={
                "approved": False,
                "instrument": "ETHUSD",
                "side": "buy",
                "quantity": "0",
                "reject_reason": "no_action_proposed",
                "requires_human_approval": False,
            },
        )
    )

    # Correlation C: proposal for a symbol that is not in `instruments` — must be
    # quarantined, never guessed/dropped silently.
    corr_c = uuid4()
    audit.record(
        AuditEvent(
            timestamp=base + timedelta(seconds=5),
            correlation_id=corr_c,
            event_type="proposal",
            payload={
                "instrument": "ZZZUSD",
                "direction": "long",
                "confidence": 0.9,
                "rationale": "unmapped symbol",
            },
        )
    )

    # An idempotency reservation with a result but no matching audit order_submitted
    # event — simulates the crash-window gap the Phase 3+4 single-transaction
    # reserve->store_result design closes going forward.
    idempotency = IdempotencyStore(root / "execution" / "idempotency.sqlite")
    orphan_client_order_id = uuid4()
    idempotency.reserve(
        orphan_client_order_id,
        order=OrderRequest(
            client_order_id=orphan_client_order_id,
            instrument="ETHUSD",
            side="buy",
            quantity=Decimal("1"),
        ),
        correlation_id=uuid4(),
    )
    idempotency.store_result(
        OrderResult(client_order_id=orphan_client_order_id, status="filled", filled_quantity=Decimal("1"))
    )

    control_dir = root / "control"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "local_positions.json").write_text(
        '{"positions": {"ETHUSD": "0.5"}, "pending_client_order_ids": []}',
        encoding="utf-8",
    )
    (control_dir / "simulated_broker.json").write_text(
        '{"positions": {"ETHUSD": "0.5"}, "open_client_order_ids": [], '
        '"last_price": {"ETHUSD": "2700.0"}}',
        encoding="utf-8",
    )
    (control_dir / "paper_tracker.json").write_text(
        '{"instrument": "ETHUSD", "cash": "8650.0", "avg_price": "2700.0"}',
        encoding="utf-8",
    )


def test_importer_populates_history_and_current_state(tmp_path: Path) -> None:
    runtime_root = tmp_path / "frozen"
    _write_fixture_runtime(runtime_root)
    admin_url = _admin_database_url()

    report = import_execution(
        runtime_root=runtime_root,
        database_url=admin_url,
        strategy_id=STRATEGY_ID,
        portfolio_name="paper",
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=False,
    )

    assert report["history_imported"] == {
        "signals": 2,
        "orders": 1,
        "order_events": 2,
        "executions": 1,
        "risk_events": 2,
    }
    assert report["destination"]["orders"] == 1
    assert report["destination"]["executions"] == 1
    assert report["destination"]["positions"] == 1
    # local_ledger cash + local_ledger base asset + exchange_reported base asset
    # (simulated_broker.json is present in this fixture, unlike the degraded-dir
    # test below).
    assert report["destination"]["balances"] == 3
    assert report["current_state"]["instruments_written"] == ["ETHUSD"]

    quarantine_text = (tmp_path / "quarantine.jsonl").read_text(encoding="utf-8")
    reasons = {
        json.loads(line)["reason"] for line in quarantine_text.splitlines() if line.strip()
    }
    assert reasons == {"unmapped_symbol", "idempotency_no_audit_match"}

    with psycopg.connect(admin_url) as connection:
        order = connection.execute(
            "SELECT status, side, requested_quantity FROM orders"
        ).fetchone()
        assert order == ("executed", "buy", Decimal("0.5"))


def test_importer_dry_run_writes_nothing(tmp_path: Path) -> None:
    runtime_root = tmp_path / "frozen"
    _write_fixture_runtime(runtime_root)
    admin_url = _admin_database_url()

    report = import_execution(
        runtime_root=runtime_root,
        database_url=admin_url,
        strategy_id=STRATEGY_ID,
        portfolio_name="paper",
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=True,
    )

    assert report["history_imported"] == {
        "signals": 2,
        "orders": 1,
        "order_events": 2,
        "executions": 1,
        "risk_events": 2,
    }
    # Dry-run previews the same numbers a real run would produce but writes none
    # of them — destination reflects the (empty) pre-existing state.
    assert report["destination"]["orders"] == 0
    assert report["destination"]["executions"] == 0
    assert report["destination"]["positions"] == 0
    assert report["destination"]["balances"] == 0


def test_importer_rerun_on_same_frozen_copy_is_idempotent(tmp_path: Path) -> None:
    runtime_root = tmp_path / "frozen"
    _write_fixture_runtime(runtime_root)
    admin_url = _admin_database_url()
    kwargs = dict(
        runtime_root=runtime_root,
        database_url=admin_url,
        strategy_id=STRATEGY_ID,
        portfolio_name="paper",
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=False,
    )

    first = import_execution(**kwargs)
    second = import_execution(**kwargs)

    assert first["destination"] == second["destination"]
    # Nothing new was created the second time around — every row from the first
    # run was found via the dedup/ON CONFLICT checks, not re-inserted.
    assert second["history_imported"] == {
        "signals": 0,
        "orders": 0,
        "order_events": 0,
        "executions": 0,
        "risk_events": 0,
    }
    assert second["quarantine_count"] == first["quarantine_count"]


def test_importer_missing_current_state_files_are_skipped_not_guessed(tmp_path: Path) -> None:
    """Mirrors runtime/paper-kraken and runtime/paper-csv (pre-date tracker-state
    persistence): local_positions.json exists but paper_tracker.json /
    simulated_broker.json do not, so cash/avg_entry_price must stay unwritten
    rather than fabricated as zero."""
    runtime_root = tmp_path / "frozen"
    _write_fixture_runtime(runtime_root)
    (runtime_root / "control" / "paper_tracker.json").unlink()
    (runtime_root / "control" / "simulated_broker.json").unlink()
    admin_url = _admin_database_url()

    report = import_execution(
        runtime_root=runtime_root,
        database_url=admin_url,
        strategy_id=STRATEGY_ID,
        portfolio_name="paper",
        quarantine_path=tmp_path / "quarantine.jsonl",
        dry_run=False,
    )

    assert report["current_state"]["paper_tracker_present"] is False
    assert report["current_state"]["simulated_broker_present"] is False
    assert report["current_state"]["instruments_written"] == ["ETHUSD"]
    # Only the base-asset local_ledger balance is known without a tracker file —
    # no cash row (unknown, not guessed) and no exchange_reported row (no broker
    # file).
    assert report["destination"]["balances"] == 1

    portfolio_id, _, _ = _ids(admin_url)
    store = PostgresPortfolioStore(
        admin_url, portfolio_id=portfolio_id, signal_source="llm_assisted", risk_limits_version_id=None
    )
    assert store.read_cash("USD") is None


# ---------------------------------------------------------------------------
# Role isolation (deploy/postgres/create_roles.sql)
# ---------------------------------------------------------------------------


def test_execution_writer_can_write_journals_but_not_update_or_delete_them() -> None:
    admin_url = _admin_database_url()
    portfolio_id, strategy_version_id, risk_limits_version_id = _ids(admin_url)
    execution_url = _execution_database_url()
    correlation_id = uuid4()

    with psycopg.connect(execution_url) as connection:
        instrument_id = connection.execute(
            "SELECT instrument_id FROM instruments WHERE canonical_symbol = 'ETHUSD'"
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO orders (
                order_id, client_order_id, portfolio_id, instrument_id,
                strategy_version_id, risk_limits_version_id, side, order_type,
                requested_quantity, trading_mode, status, requested_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'buy', 'market', 1, 'paper',
                      'submitted', now())
            """,
            (
                correlation_id,
                uuid4(),
                portfolio_id,
                instrument_id,
                strategy_version_id,
                risk_limits_version_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO order_events (order_id, event_type, payload, correlation_id)
            VALUES (%s, 'submitted', '{}'::jsonb, %s)
            """,
            (correlation_id, correlation_id),
        )
        connection.commit()
        # Append-only journal (docs/database-design.md §13/§15): INSERT is granted,
        # UPDATE/DELETE are not — enforced at the role level, not just convention.
        # Each check gets its own transaction: a rejected statement poisons the
        # rest of the transaction block in psycopg3's autocommit=False default.
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "UPDATE order_events SET event_type = 'filled' WHERE order_id = %s",
                (correlation_id,),
            )
        connection.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("DELETE FROM order_events WHERE order_id = %s", (correlation_id,))
        connection.rollback()

        # `orders` itself IS mutable (status transitions as fills arrive).
        connection.execute(
            "UPDATE orders SET status = 'executed' WHERE order_id = %s", (correlation_id,)
        )


def test_control_reader_can_read_execution_tables_but_not_write() -> None:
    admin_url = _admin_database_url()
    portfolio_id, strategy_version_id, risk_limits_version_id = _ids(admin_url)
    with psycopg.connect(admin_url) as connection:
        instrument_id = connection.execute(
            "SELECT instrument_id FROM instruments WHERE canonical_symbol = 'ETHUSD'"
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO orders (
                order_id, client_order_id, portfolio_id, instrument_id,
                strategy_version_id, risk_limits_version_id, side, order_type,
                requested_quantity, trading_mode, status, requested_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'buy', 'market', 1, 'paper',
                      'submitted', now())
            """,
            (
                uuid4(),
                uuid4(),
                portfolio_id,
                instrument_id,
                strategy_version_id,
                risk_limits_version_id,
            ),
        )

    with psycopg.connect(_control_database_url()) as connection:
        count = connection.execute("SELECT count(*) FROM orders").fetchone()[0]
        assert count == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("INSERT INTO orders (order_id) VALUES (%s)", (uuid4(),))
