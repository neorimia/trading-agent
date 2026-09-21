"""PostgreSQL execution stores — design Phases 3+4 (docs/database-design.md §8.4-8.9).

Two writers, mirroring `src/data/postgres_store.py` / `src/research/postgres_store.py`:

- `PostgresIdempotencyStore` — drop-in for `IdempotencyStore` (`src/execution/
  idempotency_store.py`), backed by `orders` / `order_events` / `executions` instead
  of a SQLite reservations table. Same `reserve` → `store_result` window guarantee.
- `PostgresPortfolioStore` — balances/positions snapshot writer (mirrors what
  `PaperTradingLoop._persist_local_state` writes to JSON today) plus `signals` /
  `risk_events` recorders.

Simplification documented here rather than hidden: both classes are constructed with
a fixed `portfolio_id` / `strategy_version_id` / `risk_limits_version_id` context,
because the paper loop runs exactly one portfolio and one strategy version per
process lifetime today (no dual-write, no live yet — docs/database-cutover-
playbook.md). A future multi-portfolio engine would resolve these per-order instead.

Second simplification: `OrderResult.broker_order_id` has no column in the schema
(design DDL never carries it — it is diagnostic only and unused by `OrderGateway`
or `PaperTradingLoop` control flow). `PostgresIdempotencyStore.get_result` therefore
returns it as `None` on idempotent replay, unlike the SQLite `IdempotencyStore`
which round-trips the full `result_json` including that field. First-submission
callers still see the real value returned directly from the broker.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from src.db.pool import get_database_pool
from src.engine.proposal_types import ParsedProposal
from src.execution.idempotency_store import DuplicateClientOrderId
from src.execution.types import OrderRequest, OrderResult
from src.risk.portfolio_state import PortfolioState
from src.risk.risk_engine import RiskDecision

# design §8.5 stores the code's `filled` OrderStatus as `executed` (its terminal
# success name); every other status is stored verbatim (see migrations/versions/
# 0003_execution_risk.py deviations note).
_RESULT_TO_ORDER_STATUS = {
    "filled": "executed",
    "partially_filled": "partially_filled",
    "rejected": "rejected",
    "unknown": "unknown",
    "timeout": "timeout",
}
_ORDER_STATUS_TO_RESULT = {value: key for key, value in _RESULT_TO_ORDER_STATUS.items()}
_TERMINAL_ORDER_STATUSES = frozenset(_ORDER_STATUS_TO_RESULT)
_RESULT_STATUS_TO_EVENT = {
    "filled": "filled",
    "partially_filled": "partial_fill",
    "rejected": "rejected",
    "unknown": "error",
    "timeout": "error",
}


def _payload(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        dumped = model.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if isinstance(model, dict):
        return model
    return {"value": str(model)}


class PostgresIdempotencyStore:
    """`reserve`/`store_result` drop-in for `IdempotencyStore`, backed by Postgres.

    `reserve` requires `order=` and `correlation_id=` (see `OrderGateway.submit`) —
    the SQLite store only ever needed the id, but a full `orders` row needs the
    instrument/side/quantity and the paper-loop decision id (`orders.order_id`,
    distinct from `client_order_id`, see 0003_execution_risk.py deviations note).
    """

    def __init__(
        self,
        database_url: str,
        *,
        portfolio_id: UUID,
        strategy_version_id: UUID | None,
        risk_limits_version_id: UUID | None,
        trading_mode: str = "paper",
    ) -> None:
        self._pool = get_database_pool(database_url)
        self._portfolio_id = portfolio_id
        self._strategy_version_id = strategy_version_id
        self._risk_limits_version_id = risk_limits_version_id
        self._trading_mode = trading_mode

    def close(self) -> None:
        """Pool lifetime belongs to the process, not an individual request."""

    @staticmethod
    def _instrument_id(connection: Any, canonical_symbol: str) -> UUID:
        row = connection.execute(
            "SELECT instrument_id FROM instruments WHERE canonical_symbol = %s",
            (canonical_symbol,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown instrument symbol {canonical_symbol!r}")
        return row["instrument_id"]

    def reserve(
        self,
        client_order_id: UUID,
        *,
        order: OrderRequest | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        if order is None:
            raise ValueError(
                "PostgresIdempotencyStore.reserve requires order= "
                "(OrderGateway.submit always passes it)"
            )
        if correlation_id is None:
            raise ValueError("PostgresIdempotencyStore.reserve requires correlation_id=")
        with self._pool.connection() as connection:
            with connection.transaction():
                existing = connection.execute(
                    "SELECT order_id, status FROM orders WHERE client_order_id = %s",
                    (client_order_id,),
                ).fetchone()
                if existing is not None:
                    stored = (
                        self._load_result(connection, existing["order_id"])
                        if existing["status"] in _TERMINAL_ORDER_STATUSES
                        else None
                    )
                    raise DuplicateClientOrderId(client_order_id, stored)
                instrument_id = self._instrument_id(connection, order.instrument)
                now = datetime.now(timezone.utc)
                try:
                    connection.execute(
                        """
                        INSERT INTO orders (
                            order_id, client_order_id, portfolio_id, instrument_id,
                            strategy_version_id, risk_limits_version_id, side,
                            order_type, requested_quantity, trading_mode, status,
                            requested_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'submitted', %s
                        )
                        """,
                        (
                            correlation_id,
                            client_order_id,
                            self._portfolio_id,
                            instrument_id,
                            self._strategy_version_id,
                            self._risk_limits_version_id,
                            order.side,
                            order.order_type,
                            order.quantity,
                            self._trading_mode,
                            now,
                        ),
                    )
                except psycopg.errors.UniqueViolation as exc:
                    raise DuplicateClientOrderId(client_order_id, None) from exc
                connection.execute(
                    """
                    INSERT INTO order_events (order_id, event_type, payload, correlation_id)
                    VALUES (%s, 'submitted', %s::jsonb, %s)
                    """,
                    (
                        correlation_id,
                        json.dumps({"client_order_id": str(client_order_id)}),
                        correlation_id,
                    ),
                )

    def store_result(self, result: OrderResult) -> None:
        with self._pool.connection() as connection:
            with connection.transaction():
                row = connection.execute(
                    "SELECT order_id, instrument_id FROM orders WHERE client_order_id = %s",
                    (result.client_order_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(
                        f"no reservation for client_order_id {result.client_order_id}"
                    )
                order_id = row["order_id"]
                order_status = _RESULT_TO_ORDER_STATUS[result.status]
                closed_at = (
                    datetime.now(timezone.utc)
                    if order_status in _TERMINAL_ORDER_STATUSES
                    else None
                )
                connection.execute(
                    """
                    UPDATE orders SET status = %s, reason = %s, closed_at = %s
                    WHERE order_id = %s
                    """,
                    (order_status, result.reason, closed_at, order_id),
                )
                connection.execute(
                    """
                    INSERT INTO order_events (order_id, event_type, payload, correlation_id)
                    VALUES (%s, %s, %s::jsonb, %s)
                    """,
                    (
                        order_id,
                        _RESULT_STATUS_TO_EVENT[result.status],
                        result.model_dump_json(),
                        order_id,
                    ),
                )
                if result.filled_quantity > 0 and result.fill_price is not None:
                    connection.execute(
                        """
                        INSERT INTO executions (
                            order_id, instrument_id, trading_mode, fill_price,
                            fill_quantity, fee, executed_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            order_id,
                            row["instrument_id"],
                            self._trading_mode,
                            result.fill_price,
                            result.filled_quantity,
                            result.fee,
                            datetime.now(timezone.utc),
                        ),
                    )

    def get_result(self, client_order_id: UUID) -> OrderResult | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT order_id, status FROM orders WHERE client_order_id = %s",
                (client_order_id,),
            ).fetchone()
            if row is None or row["status"] not in _TERMINAL_ORDER_STATUSES:
                return None
            return self._load_result(connection, row["order_id"])

    @staticmethod
    def _load_result(connection: Any, order_id: UUID) -> OrderResult | None:
        order = connection.execute(
            "SELECT client_order_id, status, reason FROM orders WHERE order_id = %s",
            (order_id,),
        ).fetchone()
        if order is None or order["client_order_id"] is None:
            return None
        executions = connection.execute(
            """
            SELECT fill_price, fill_quantity, fee FROM executions
            WHERE order_id = %s ORDER BY created_at
            """,
            (order_id,),
        ).fetchall()
        filled_qty = sum((row["fill_quantity"] for row in executions), Decimal("0"))
        fee_total = sum((row["fee"] for row in executions), Decimal("0"))
        fill_price = executions[-1]["fill_price"] if executions else None
        return OrderResult(
            client_order_id=order["client_order_id"],
            status=_ORDER_STATUS_TO_RESULT.get(order["status"], "unknown"),
            filled_quantity=filled_qty,
            fill_price=fill_price,
            reason=order["reason"],
            fee=fee_total,
        )


class PostgresPortfolioStore:
    """Writes the same balances/positions the JSON files carry, plus `signals` and
    `risk_events` (design §8.4, §8.6-8.7). Read-only helper `read_open_positions` is
    also used by the control-plane Postgres read path (`src/control/runtime_state.py`)."""

    def __init__(
        self,
        database_url: str,
        *,
        portfolio_id: UUID,
        signal_source: str,
        risk_limits_version_id: UUID | None,
    ) -> None:
        self._pool = get_database_pool(database_url)
        self._portfolio_id = portfolio_id
        self._signal_source = signal_source
        self._risk_limits_version_id = risk_limits_version_id

    def close(self) -> None:
        """Pool lifetime belongs to the process, not an individual request."""

    @staticmethod
    def _instrument_id(connection: Any, canonical_symbol: str) -> UUID:
        row = connection.execute(
            "SELECT instrument_id FROM instruments WHERE canonical_symbol = %s",
            (canonical_symbol,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown instrument symbol {canonical_symbol!r}")
        return row["instrument_id"]

    @staticmethod
    def _base_asset_id(connection: Any, instrument_id: UUID) -> int:
        row = connection.execute(
            "SELECT base_asset_id FROM instruments WHERE instrument_id = %s",
            (instrument_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown instrument_id {instrument_id!r}")
        return row["base_asset_id"]

    @staticmethod
    def _asset_id(connection: Any, symbol: str) -> int:
        row = connection.execute(
            "SELECT asset_id FROM assets WHERE symbol = %s",
            (symbol,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown asset symbol {symbol!r}")
        return row["asset_id"]

    def persist_snapshot(
        self,
        *,
        instrument: str,
        cash_asset: str,
        cash: Decimal | None,
        open_quantity: Decimal,
        avg_entry_price: Decimal | None,
        last_price: Decimal | None,
        broker_open_quantity: Decimal | None,
    ) -> None:
        """One local_ledger cash row, one local_ledger base-asset row, one open/closed
        `positions` row, and — when the broker snapshot is available — one
        exchange_reported base-asset balance row (design §8.4's local-vs-exchange
        distinction).

        `cash=None` skips the cash row entirely rather than writing a fabricated
        zero — used by `scripts/db/import_execution.py` for frozen runtime
        directories whose `paper_tracker.json` (the only source of cash) never
        got written (pre-dates tracker-state persistence; no guessing per the
        importer's quarantine philosophy)."""
        with self._pool.connection() as connection:
            with connection.transaction():
                instrument_id = self._instrument_id(connection, instrument)
                base_asset_id = self._base_asset_id(connection, instrument_id)
                if cash is not None:
                    cash_asset_id = self._asset_id(connection, cash_asset)
                    self._upsert_balance(connection, cash_asset_id, "local_ledger", cash)
                self._upsert_balance(
                    connection, base_asset_id, "local_ledger", open_quantity
                )
                if broker_open_quantity is not None:
                    self._upsert_balance(
                        connection, base_asset_id, "exchange_reported", broker_open_quantity
                    )
                self._upsert_position(
                    connection,
                    instrument_id,
                    open_quantity=open_quantity,
                    avg_entry_price=avg_entry_price if open_quantity != 0 else None,
                    last_price=last_price,
                )

    def _upsert_balance(
        self, connection: Any, asset_id: int, source: str, quantity: Decimal
    ) -> None:
        connection.execute(
            """
            INSERT INTO balances (portfolio_id, asset_id, source, quantity, updated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (portfolio_id, asset_id, source) DO UPDATE SET
                quantity = EXCLUDED.quantity,
                updated_at = now()
            """,
            (self._portfolio_id, asset_id, source, quantity),
        )

    def _upsert_position(
        self,
        connection: Any,
        instrument_id: UUID,
        *,
        open_quantity: Decimal,
        avg_entry_price: Decimal | None,
        last_price: Decimal | None,
    ) -> None:
        existing = connection.execute(
            """
            SELECT position_id FROM positions
            WHERE portfolio_id = %s AND instrument_id = %s AND closed_at IS NULL
            """,
            (self._portfolio_id, instrument_id),
        ).fetchone()
        if open_quantity != 0:
            if existing is not None:
                connection.execute(
                    """
                    UPDATE positions SET
                        quantity = %s, avg_entry_price = %s, last_price = %s, updated_at = now()
                    WHERE position_id = %s
                    """,
                    (open_quantity, avg_entry_price, last_price, existing["position_id"]),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO positions (
                        portfolio_id, instrument_id, quantity, avg_entry_price, last_price
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (self._portfolio_id, instrument_id, open_quantity, avg_entry_price, last_price),
                )
        elif existing is not None:
            connection.execute(
                """
                UPDATE positions SET
                    quantity = 0, last_price = %s, updated_at = now(), closed_at = now()
                WHERE position_id = %s
                """,
                (last_price, existing["position_id"]),
            )

    def record_signal(
        self,
        proposal: ParsedProposal,
        *,
        strategy_version_id: UUID | None,
    ) -> UUID:
        with self._pool.connection() as connection:
            instrument_id = self._instrument_id(connection, proposal.instrument)
            row = connection.execute(
                """
                INSERT INTO signals (
                    instrument_id, strategy_version_id, source, direction, confidence,
                    rationale, is_proposal
                ) VALUES (%s, %s, %s, %s, %s, %s, true)
                RETURNING signal_id
                """,
                (
                    instrument_id,
                    strategy_version_id,
                    self._signal_source,
                    proposal.direction,
                    Decimal(str(proposal.confidence)),
                    proposal.rationale,
                ),
            ).fetchone()
        return row["signal_id"]

    def record_risk_event(
        self,
        decision: RiskDecision,
        *,
        portfolio_state: PortfolioState,
        correlation_id: UUID,
        order_id: UUID | None = None,
        risk_limits_version_id: UUID | None = None,
    ) -> None:
        version_id = risk_limits_version_id or self._risk_limits_version_id
        if version_id is None:
            raise ValueError("record_risk_event requires a risk_limits_version_id")
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO risk_events (
                    order_id, event_type, reason, portfolio_state_snapshot,
                    risk_limits_version_id, correlation_id
                ) VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    order_id,
                    _risk_event_type(decision),
                    decision.reject_reason,
                    json.dumps(_payload(portfolio_state)),
                    version_id,
                    correlation_id,
                ),
            )

    def record_halt_event(
        self,
        reason: str,
        *,
        portfolio_state: PortfolioState,
        correlation_id: UUID,
        risk_limits_version_id: UUID | None = None,
    ) -> None:
        """`HaltAndFlatten`-triggered halts (design §13) — every halt trips the kill
        switch (`kill_switch`) except `reconciliation_mismatch`, which keeps its own
        event type because it is a data-integrity signal, not a risk-limit trip."""
        version_id = risk_limits_version_id or self._risk_limits_version_id
        if version_id is None:
            raise ValueError("record_halt_event requires a risk_limits_version_id")
        event_type = "reconciliation_mismatch" if reason == "reconciliation_mismatch" else "kill_switch"
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO risk_events (
                    event_type, reason, portfolio_state_snapshot, risk_limits_version_id,
                    correlation_id
                ) VALUES (%s, %s, %s::jsonb, %s, %s)
                """,
                (
                    event_type,
                    reason,
                    json.dumps(_payload(portfolio_state)),
                    version_id,
                    correlation_id,
                ),
            )

    def read_open_positions(self) -> dict[str, Decimal]:
        """Canonical_symbol -> open quantity, for the control-plane read path
        (`src/control/runtime_state.py`) — a Postgres analogue of parsing
        `local_positions.json`."""
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT i.canonical_symbol, p.quantity
                FROM positions p
                JOIN instruments i ON i.instrument_id = p.instrument_id
                WHERE p.portfolio_id = %s AND p.closed_at IS NULL
                """,
                (self._portfolio_id,),
            ).fetchall()
        return {row["canonical_symbol"]: row["quantity"] for row in rows}

    def read_cash(self, cash_asset: str) -> Decimal | None:
        with self._pool.connection() as connection:
            asset_id = self._asset_id(connection, cash_asset)
            row = connection.execute(
                """
                SELECT quantity FROM balances
                WHERE portfolio_id = %s AND asset_id = %s AND source = 'local_ledger'
                """,
                (self._portfolio_id, asset_id),
            ).fetchone()
        return row["quantity"] if row is not None else None


def _risk_event_type(decision: RiskDecision) -> str:
    if decision.approved:
        return "order_accepted"
    mapping = {
        "max_daily_loss": "max_daily_loss_halt",
        "max_drawdown": "max_drawdown_halt",
        "halted": "kill_switch",
    }
    return mapping.get(decision.reject_reason or "", "order_rejected")


def resolve_portfolio_id(database_url: str, portfolio_name: str) -> UUID:
    with get_database_pool(database_url).connection() as connection:
        row = connection.execute(
            "SELECT portfolio_id FROM portfolios WHERE name = %s",
            (portfolio_name,),
        ).fetchone()
    if row is None:
        raise ValueError(
            f"unknown portfolio {portfolio_name!r} — run scripts/db/seed.py first"
        )
    return row["portfolio_id"]


def resolve_active_strategy_version_id(database_url: str, strategy_id: str) -> UUID | None:
    with get_database_pool(database_url).connection() as connection:
        row = connection.execute(
            """
            SELECT strategy_version_id FROM strategy_versions
            WHERE strategy_id = %s AND is_active = true
            ORDER BY version DESC LIMIT 1
            """,
            (strategy_id,),
        ).fetchone()
    return row["strategy_version_id"] if row is not None else None


def resolve_open_risk_limits_version_id(database_url: str) -> UUID | None:
    with get_database_pool(database_url).connection() as connection:
        row = connection.execute(
            "SELECT risk_limits_version_id FROM risk_limits WHERE effective_to IS NULL",
        ).fetchone()
    return row["risk_limits_version_id"] if row is not None else None
