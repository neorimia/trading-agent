"""Idempotent import of one frozen `runtime/paper*` directory into PostgreSQL.

Reconstructs design Phase 3+4 history (`signals`, `orders`, `order_events`,
`executions`, `risk_events`) from a **frozen copy** of a paper-trading runtime
directory, plus its current balances/positions — modeled on
`scripts/db/import_research.py` / `scripts/db/import_market_data.py` (same
idempotent-rerun, "never guess", JSON-report contract).

Inputs, all under `--runtime-root` (never the live `runtime/paper*` tree — copy
it first, e.g. `cp -r runtime/paper /tmp/paper-frozen`):

- `control/local_positions.json`, `simulated_broker.json`, `paper_tracker.json`
  (all optional — some frozen dirs pre-date tracker-state persistence),
  `reconciliation.json` (informational only, not re-derived).
- `execution/idempotency.sqlite` (optional; cross-checked against audit history).
- `audit/audit.sqlite` — **required**, read-only reconstruction source.

One invocation imports exactly one runtime directory into exactly one
`portfolios` row (`--portfolio-name`, defaults to `runtime_root.name`, must
already exist — run `scripts/db/seed.py` first or let this script seed it via
`--strategies`/`--strategy-versions`/`--risk-limits`/`--paper-config`, same as
`import_research.py` seeding reference data). Loop this command across
`paper`, `paper-kraken`, `paper-csv`, `paper-faza5` frozen copies to import all
four.

Documented gaps (never fabricated):

- `--strategy-id` is a required CLI argument. `ParsedProposal`/`RiskDecision`
  audit payloads carry no strategy identity (it is fixed for a whole paper-
  session process via a CLI flag that itself isn't logged) — the operator
  who ran that frozen directory must say which strategy it was, exactly like
  `import_market_data.py --source` requires vendor attribution instead of
  guessing it from the cache file.
- `risk_events.portfolio_state_snapshot` is NOT NULL, but the audit trail logs
  only `RiskDecision`/halt-reason — never the `PortfolioState` object
  `RiskEngine.evaluate()` saw. Imported rows store a
  `{"reconstructed": false, ...}` marker instead of a fabricated snapshot.
- `strategy_version_id` / `risk_limits_version_id` are always the *current*
  seeded version (no historical version-at-timestamp tracking exists yet) —
  every imported signal/order/risk_event sets `unresolved_history=true` in the
  report per the cutover playbook gate.
- `broker_order_id` on replay has the same gap as `PostgresIdempotencyStore`
  (`src/execution/postgres_store.py`) — not stored anywhere in the schema.

Quarantine (JSONL at `--quarantine`, truncated and rewritten each run so a
rerun on the same frozen copy reproduces the same file, never accumulates):

- `local_vs_broker_mismatch` — `local_positions.json` vs `simulated_broker.json`
  disagree on a position or the pending/open order id sets.
- `idempotency_no_audit_match` — an `idempotency.sqlite` reservation
  (`client_order_id`) with no corresponding audit `order_submitted` event
  (the exact crash-window gap Phase 3+4's single-transaction `reserve` →
  `store_result` closes going forward; historically unprovable, not guessed).
- `order_submitted_without_risk_decision` / `unmapped_symbol` — an order or
  signal whose instrument/side/quantity cannot be resolved without guessing.

Idempotency: `orders` keys off `order_id = correlation_id` (`ON CONFLICT DO
NOTHING`); `signals`/`order_events`/`executions`/`risk_events` have no natural
schema key for a historical import, so each insert is preceded by an
existence check on the tuple that identifies "the same audit event replayed"
(exact original timestamp + correlation/order id). Re-running on the same
frozen copy must not change any table's row count.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import yaml
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.db.seed import seed_execution_reference_data
from src.db.config import require_database_url
from src.db.pool import close_database_pools
from src.engine.proposal_types import ParsedProposal
from src.execution.broker import BrokerState
from src.execution.postgres_store import (
    _RESULT_STATUS_TO_EVENT,
    _RESULT_TO_ORDER_STATUS,
    PostgresPortfolioStore,
    _risk_event_type,
)
from src.execution.reconciliation import LocalPortfolioSnapshot
from src.execution.types import OrderResult
from src.risk.risk_engine import RiskDecision

_TERMINAL_STATUSES = frozenset(_RESULT_TO_ORDER_STATUS)


class QuarantineWriter:
    """JSONL sink, truncated at construction so a rerun on the same frozen
    copy reproduces the same file instead of accumulating duplicates across
    invocations."""

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


def _load_audit_events(
    path: Path,
) -> dict[UUID, dict[str, tuple[datetime, dict[str, Any]]]]:
    """`correlation_id -> {event_type: (timestamp, payload)}` — one event of a
    given type per correlation in the live loop's own recording pattern (never
    double-recorded within one bar-decision cycle)."""
    grouped: dict[UUID, dict[str, tuple[datetime, dict[str, Any]]]] = {}
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        for row in connection.execute(
            "SELECT timestamp, correlation_id, event_type, payload "
            "FROM audit_events ORDER BY id ASC"
        ):
            correlation_id = UUID(row["correlation_id"])
            timestamp = datetime.fromisoformat(row["timestamp"])
            payload = json.loads(row["payload"])
            grouped.setdefault(correlation_id, {})[row["event_type"]] = (timestamp, payload)
    finally:
        connection.close()
    return grouped


def _load_idempotency(path: Path) -> dict[str, tuple[str, dict[str, Any] | None]]:
    """`client_order_id -> (reserved_at, result payload or None if in-flight)`."""
    reservations: dict[str, tuple[str, dict[str, Any] | None]] = {}
    if not path.is_file():
        return reservations
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        for row in connection.execute(
            "SELECT client_order_id, reserved_at, result_json FROM reservations"
        ):
            result = json.loads(row["result_json"]) if row["result_json"] else None
            reservations[row["client_order_id"]] = (row["reserved_at"], result)
    finally:
        connection.close()
    return reservations


def _signal_source_for_strategy(strategy_id: str, strategies_path: Path) -> str:
    """`signals.source` mirrors the strategy's `kind` — the same value the live
    loop passes as `PostgresPortfolioStore(signal_source=...)` (`scripts/
    paper_trading/run_paper_session.py`)."""
    raw = yaml.safe_load(strategies_path.read_text(encoding="utf-8"))
    for item in raw.get("strategies", []):
        if str(item.get("id")) == strategy_id:
            return str(item["kind"])
    raise ValueError(f"unknown strategy_id {strategy_id!r} in {strategies_path}")


def _unavailable_portfolio_state_snapshot(
    *, decision_payload: dict[str, Any] | None = None, halt_reason: str | None = None
) -> dict[str, Any]:
    return {
        "reconstructed": False,
        "note": (
            "audit trail logs RiskDecision/halt reason only, not the "
            "PortfolioState object RiskEngine.evaluate() saw at decision "
            "time; not fabricated by the importer"
        ),
        "risk_decision": decision_payload,
        "halt_reason": halt_reason,
    }


def _resolve_instrument_id(connection: Any, symbol: str) -> UUID | None:
    row = connection.execute(
        "SELECT instrument_id FROM instruments WHERE canonical_symbol = %s",
        (symbol,),
    ).fetchone()
    return row["instrument_id"] if row is not None else None


@dataclass
class _ImportCounts:
    signals: int = 0
    orders: int = 0
    order_events: int = 0
    executions: int = 0
    risk_events: int = 0
    quarantined: dict[str, int] = field(default_factory=dict)

    def bump_quarantine(self, reason: str) -> None:
        self.quarantined[reason] = self.quarantined.get(reason, 0) + 1


def _import_signal(
    connection: Any,
    *,
    instrument_id: UUID,
    strategy_version_id: UUID | None,
    source: str,
    proposal: ParsedProposal,
    timestamp: datetime,
    dry_run: bool,
) -> tuple[UUID, bool]:
    """Returns `(signal_id, created)` — `created=False` on an idempotent rerun
    that found the same signal already imported."""
    existing = connection.execute(
        """
        SELECT signal_id FROM signals
        WHERE instrument_id = %s AND source = %s AND generated_at = %s
          AND rationale IS NOT DISTINCT FROM %s
          AND strategy_version_id IS NOT DISTINCT FROM %s
        """,
        (instrument_id, source, timestamp, proposal.rationale, strategy_version_id),
    ).fetchone()
    if existing is not None:
        return existing["signal_id"], False
    if dry_run:
        return uuid4(), True
    row = connection.execute(
        """
        INSERT INTO signals (
            instrument_id, strategy_version_id, source, direction, confidence,
            rationale, is_proposal, generated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, true, %s)
        RETURNING signal_id
        """,
        (
            instrument_id,
            strategy_version_id,
            source,
            proposal.direction,
            Decimal(str(proposal.confidence)),
            proposal.rationale,
            timestamp,
        ),
    ).fetchone()
    return row["signal_id"], True


def _risk_event_exists(connection: Any, correlation_id: UUID, event_type: str, occurred_at: datetime) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM risk_events
            WHERE correlation_id = %s AND event_type = %s AND occurred_at = %s
            """,
            (correlation_id, event_type, occurred_at),
        ).fetchone()
        is not None
    )


def _import_risk_event(
    connection: Any,
    *,
    order_id: UUID | None,
    event_type: str,
    reason: str | None,
    risk_limits_version_id: UUID,
    correlation_id: UUID,
    timestamp: datetime,
    snapshot_payload: dict[str, Any],
    dry_run: bool,
) -> bool:
    if _risk_event_exists(connection, correlation_id, event_type, timestamp):
        return False
    if dry_run:
        return True
    connection.execute(
        """
        INSERT INTO risk_events (
            occurred_at, order_id, event_type, reason, portfolio_state_snapshot,
            risk_limits_version_id, correlation_id
        ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
        """,
        (
            timestamp,
            order_id,
            event_type,
            reason,
            json.dumps(snapshot_payload, default=str),
            risk_limits_version_id,
            correlation_id,
        ),
    )
    return True


def _import_order(
    connection: Any,
    *,
    order_id: UUID,
    client_order_id: UUID,
    portfolio_id: UUID,
    instrument_id: UUID,
    strategy_version_id: UUID | None,
    signal_id: UUID | None,
    risk_limits_version_id: UUID,
    side: str,
    requested_quantity: Decimal,
    status: str,
    reason: str | None,
    requested_at: datetime,
    closed_at: datetime | None,
    dry_run: bool,
) -> bool:
    """`True` if this call created the row (fresh import); `False` if it
    already existed (idempotent rerun) — either way the row is present."""
    existing = connection.execute(
        "SELECT 1 FROM orders WHERE order_id = %s", (order_id,)
    ).fetchone()
    if existing is not None or dry_run:
        return existing is None
    connection.execute(
        """
        INSERT INTO orders (
            order_id, client_order_id, portfolio_id, instrument_id,
            strategy_version_id, signal_id, risk_limits_version_id, side,
            order_type, requested_quantity, trading_mode, status, reason,
            requested_at, closed_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, 'market', %s, 'paper', %s, %s, %s, %s
        )
        ON CONFLICT (order_id) DO NOTHING
        """,
        (
            order_id,
            client_order_id,
            portfolio_id,
            instrument_id,
            strategy_version_id,
            signal_id,
            risk_limits_version_id,
            side,
            requested_quantity,
            status,
            reason,
            requested_at,
            closed_at,
        ),
    )
    return True


def _import_order_event(
    connection: Any,
    *,
    order_id: UUID,
    event_type: str,
    occurred_at: datetime,
    payload: dict[str, Any],
    correlation_id: UUID,
    dry_run: bool,
) -> bool:
    existing = connection.execute(
        """
        SELECT 1 FROM order_events
        WHERE order_id = %s AND event_type = %s AND occurred_at = %s
        """,
        (order_id, event_type, occurred_at),
    ).fetchone()
    if existing is not None:
        return False
    if dry_run:
        return True
    connection.execute(
        """
        INSERT INTO order_events (order_id, event_type, occurred_at, payload, correlation_id)
        VALUES (%s, %s, %s, %s::jsonb, %s)
        """,
        (order_id, event_type, occurred_at, json.dumps(payload, default=str), correlation_id),
    )
    return True


def _import_execution_row(
    connection: Any,
    *,
    order_id: UUID,
    instrument_id: UUID,
    fill_price: Decimal,
    fill_quantity: Decimal,
    fee: Decimal,
    executed_at: datetime,
    dry_run: bool,
) -> bool:
    existing = connection.execute(
        """
        SELECT 1 FROM executions
        WHERE order_id = %s AND fill_price = %s AND fill_quantity = %s AND executed_at = %s
        """,
        (order_id, fill_price, fill_quantity, executed_at),
    ).fetchone()
    if existing is not None:
        return False
    if dry_run:
        return True
    connection.execute(
        """
        INSERT INTO executions (
            order_id, instrument_id, trading_mode, fill_price, fill_quantity, fee, executed_at
        ) VALUES (%s, %s, 'paper', %s, %s, %s, %s)
        """,
        (order_id, instrument_id, fill_price, fill_quantity, fee, executed_at),
    )
    return True


def _import_history(
    connection: Any,
    *,
    audit_events: dict[UUID, dict[str, tuple[datetime, dict[str, Any]]]],
    idempotency_reservations: dict[str, tuple[str, dict[str, Any] | None]],
    portfolio_id: UUID,
    strategy_version_id: UUID | None,
    risk_limits_version_id: UUID,
    signal_source: str,
    quarantine: QuarantineWriter,
    dry_run: bool,
) -> _ImportCounts:
    counts = _ImportCounts()
    signals_by_correlation: dict[UUID, UUID] = {}
    orders_by_correlation: set[UUID] = set()
    matched_client_order_ids: set[str] = set()

    for correlation_id, events in audit_events.items():
        if "proposal" in events:
            ts, payload = events["proposal"]
            proposal = ParsedProposal.model_validate(payload)
            instrument_id = _resolve_instrument_id(connection, proposal.instrument)
            if instrument_id is None:
                quarantine.add(
                    "unmapped_symbol",
                    stage="signal",
                    correlation_id=str(correlation_id),
                    instrument=proposal.instrument,
                )
                counts.bump_quarantine("unmapped_symbol")
            else:
                signal_id, created = _import_signal(
                    connection,
                    instrument_id=instrument_id,
                    strategy_version_id=strategy_version_id,
                    source=signal_source,
                    proposal=proposal,
                    timestamp=ts,
                    dry_run=dry_run,
                )
                signals_by_correlation[correlation_id] = signal_id
                if created:
                    counts.signals += 1

        # Order first: `risk_events.order_id` is a real FK to `orders`, so we must
        # know whether this correlation's order row actually got created (it may
        # fail — unmapped_symbol — after the risk_decision audit event existed)
        # before attaching a risk_event to it. Reading the raw `risk_decision`
        # payload below does not depend on this ordering.
        if "order_submitted" in events:
            ts_submit, submit_payload = events["order_submitted"]
            result = OrderResult.model_validate(submit_payload)
            client_order_id = str(result.client_order_id)
            matched_client_order_ids.add(client_order_id)
            if "risk_decision" not in events:
                quarantine.add(
                    "order_submitted_without_risk_decision",
                    correlation_id=str(correlation_id),
                    client_order_id=client_order_id,
                )
                counts.bump_quarantine("order_submitted_without_risk_decision")
            else:
                _, decision_payload = events["risk_decision"]
                decision = RiskDecision.model_validate(decision_payload)
                instrument_id = _resolve_instrument_id(connection, decision.instrument)
                if instrument_id is None:
                    quarantine.add(
                        "unmapped_symbol",
                        stage="order",
                        correlation_id=str(correlation_id),
                        instrument=decision.instrument,
                    )
                    counts.bump_quarantine("unmapped_symbol")
                else:
                    status = _RESULT_TO_ORDER_STATUS[result.status]
                    closed_at = ts_submit if status in _TERMINAL_STATUSES else None
                    if _import_order(
                        connection,
                        order_id=correlation_id,
                        client_order_id=result.client_order_id,
                        portfolio_id=portfolio_id,
                        instrument_id=instrument_id,
                        strategy_version_id=strategy_version_id,
                        signal_id=signals_by_correlation.get(correlation_id),
                        risk_limits_version_id=risk_limits_version_id,
                        side=decision.side,
                        requested_quantity=decision.quantity,
                        status=status,
                        reason=result.reason,
                        requested_at=ts_submit,
                        closed_at=closed_at,
                        dry_run=dry_run,
                    ):
                        counts.orders += 1
                    orders_by_correlation.add(correlation_id)

                    if _import_order_event(
                        connection,
                        order_id=correlation_id,
                        event_type="submitted",
                        occurred_at=ts_submit,
                        payload=submit_payload,
                        correlation_id=correlation_id,
                        dry_run=dry_run,
                    ):
                        counts.order_events += 1

                    if "fill" in events:
                        ts_fill, fill_payload = events["fill"]
                        fill_result = OrderResult.model_validate(fill_payload)
                        fill_event_type = _RESULT_STATUS_TO_EVENT[fill_result.status]
                        if _import_order_event(
                            connection,
                            order_id=correlation_id,
                            event_type=fill_event_type,
                            occurred_at=ts_fill,
                            payload=fill_payload,
                            correlation_id=correlation_id,
                            dry_run=dry_run,
                        ):
                            counts.order_events += 1
                        if fill_result.filled_quantity > 0 and fill_result.fill_price is not None:
                            if _import_execution_row(
                                connection,
                                order_id=correlation_id,
                                instrument_id=instrument_id,
                                fill_price=fill_result.fill_price,
                                fill_quantity=fill_result.filled_quantity,
                                fee=fill_result.fee,
                                executed_at=ts_fill,
                                dry_run=dry_run,
                            ):
                                counts.executions += 1
                    elif result.status in {"rejected", "unknown", "timeout"}:
                        # No separate `fill` audit event for these terminal-without-
                        # fill outcomes; the live loop never records one either.
                        terminal_event_type = _RESULT_STATUS_TO_EVENT[result.status]
                        if _import_order_event(
                            connection,
                            order_id=correlation_id,
                            event_type=terminal_event_type,
                            occurred_at=ts_submit,
                            payload=submit_payload,
                            correlation_id=correlation_id,
                            dry_run=dry_run,
                        ):
                            counts.order_events += 1

        if "risk_decision" in events:
            ts, payload = events["risk_decision"]
            decision = RiskDecision.model_validate(payload)
            event_type = _risk_event_type(decision)
            # `orders_by_correlation` reflects whether the order block above (which
            # ran first, in this same iteration) actually created/found an `orders`
            # row for this correlation — never a dangling FK, even when the order
            # was quarantined (unmapped_symbol) after the risk_decision existed.
            order_id = correlation_id if correlation_id in orders_by_correlation else None
            if _import_risk_event(
                connection,
                order_id=order_id,
                event_type=event_type,
                reason=decision.reject_reason,
                risk_limits_version_id=risk_limits_version_id,
                correlation_id=correlation_id,
                timestamp=ts,
                snapshot_payload=_unavailable_portfolio_state_snapshot(decision_payload=payload),
                dry_run=dry_run,
            ):
                counts.risk_events += 1

        if "halt" in events:
            ts, payload = events["halt"]
            reason = payload.get("reason") if isinstance(payload, dict) else None
            event_type = "reconciliation_mismatch" if reason == "reconciliation_mismatch" else "kill_switch"
            order_id = correlation_id if correlation_id in orders_by_correlation else None
            if _import_risk_event(
                connection,
                order_id=order_id,
                event_type=event_type,
                reason=reason,
                risk_limits_version_id=risk_limits_version_id,
                correlation_id=correlation_id,
                timestamp=ts,
                snapshot_payload=_unavailable_portfolio_state_snapshot(halt_reason=reason),
                dry_run=dry_run,
            ):
                counts.risk_events += 1

    for client_order_id, (reserved_at, result) in idempotency_reservations.items():
        if client_order_id not in matched_client_order_ids:
            quarantine.add(
                "idempotency_no_audit_match",
                client_order_id=client_order_id,
                reserved_at=reserved_at,
                has_result=result is not None,
            )
            counts.bump_quarantine("idempotency_no_audit_match")

    return counts


def _import_current_state(
    portfolio_store: PostgresPortfolioStore,
    *,
    control_dir: Path,
    cash_asset: str,
    quarantine: QuarantineWriter,
    dry_run: bool,
) -> dict[str, Any]:
    local_raw = _read_json(control_dir / "local_positions.json")
    broker_raw = _read_json(control_dir / "simulated_broker.json")
    tracker_raw = _read_json(control_dir / "paper_tracker.json")
    result: dict[str, Any] = {
        "local_positions_present": local_raw is not None,
        "simulated_broker_present": broker_raw is not None,
        "paper_tracker_present": tracker_raw is not None,
        "instruments_written": [],
        "instruments_skipped_unmapped": [],
    }
    if local_raw is None:
        return result

    local = LocalPortfolioSnapshot.model_validate(local_raw)
    broker = BrokerState.model_validate(broker_raw) if broker_raw is not None else None
    tracker_instrument = tracker_raw.get("instrument") if tracker_raw else None
    tracker_cash = Decimal(str(tracker_raw["cash"])) if tracker_raw else None
    tracker_avg_price = Decimal(str(tracker_raw["avg_price"])) if tracker_raw else None

    instruments = sorted(set(local.positions) | set(broker.positions if broker else {}))
    for instrument in instruments:
        local_qty = local.positions.get(instrument, Decimal("0"))
        broker_qty = broker.positions.get(instrument) if broker is not None else None
        if broker is not None and broker_qty is not None and local_qty != broker_qty:
            quarantine.add(
                "local_vs_broker_mismatch",
                field="position",
                instrument=instrument,
                local=str(local_qty),
                broker=str(broker_qty),
            )
        is_tracker_instrument = instrument == tracker_instrument
        if dry_run:
            result["instruments_written"].append(instrument)
            continue
        try:
            portfolio_store.persist_snapshot(
                instrument=instrument,
                cash_asset=cash_asset,
                cash=tracker_cash if is_tracker_instrument else None,
                open_quantity=local_qty,
                avg_entry_price=tracker_avg_price if is_tracker_instrument else None,
                last_price=(broker.last_price.get(instrument) if broker is not None else None),
                broker_open_quantity=broker_qty,
            )
            result["instruments_written"].append(instrument)
        except ValueError:
            quarantine.add("unmapped_symbol", stage="current_state", instrument=instrument)
            result["instruments_skipped_unmapped"].append(instrument)

    if broker is not None:
        local_pending = sorted(local.pending_client_order_ids)
        broker_open = sorted(broker.open_client_order_ids)
        if local_pending != broker_open:
            quarantine.add(
                "local_vs_broker_mismatch",
                field="open_orders",
                local=",".join(local_pending),
                broker=",".join(broker_open),
            )
    return result


def _destination_counts(connection: Any, portfolio_id: UUID) -> dict[str, int]:
    def count(query: str, *params: Any) -> int:
        return connection.execute(query, params).fetchone()["count"]

    return {
        "orders": count(
            "SELECT count(*) AS count FROM orders WHERE portfolio_id = %s", portfolio_id
        ),
        "order_events": count(
            """
            SELECT count(*) AS count FROM order_events oe
            JOIN orders o ON o.order_id = oe.order_id WHERE o.portfolio_id = %s
            """,
            portfolio_id,
        ),
        "executions": count(
            """
            SELECT count(*) AS count FROM executions e
            JOIN orders o ON o.order_id = e.order_id WHERE o.portfolio_id = %s
            """,
            portfolio_id,
        ),
        # `risk_events` has no `portfolio_id` column (design §8.7 — it links via
        # `order_id`, nullable for standalone halts/reconciliation). Order-linked
        # rows are scoped to this portfolio precisely; standalone rows are not
        # attributable to any single portfolio, so they get their own system-wide
        # count rather than being folded into (or excluded from) this portfolio's
        # total.
        "risk_events_for_portfolio_orders": count(
            """
            SELECT count(*) AS count FROM risk_events re
            JOIN orders o ON o.order_id = re.order_id WHERE o.portfolio_id = %s
            """,
            portfolio_id,
        ),
        "risk_events_standalone_system_wide": count(
            "SELECT count(*) AS count FROM risk_events WHERE order_id IS NULL"
        ),
        "positions": count(
            "SELECT count(*) AS count FROM positions WHERE portfolio_id = %s", portfolio_id
        ),
        "balances": count(
            "SELECT count(*) AS count FROM balances WHERE portfolio_id = %s", portfolio_id
        ),
    }


def import_execution(
    *,
    runtime_root: Path,
    database_url: str,
    strategy_id: str,
    portfolio_name: str | None = None,
    cash_asset: str = "USD",
    strategies_path: Path = REPO_ROOT / "config/strategies.yaml",
    strategy_versions_dir: Path = REPO_ROOT / "config/strategy_versions",
    risk_limits_path: Path = REPO_ROOT / "config/risk_limits.yaml",
    paper_config_path: Path = REPO_ROOT / "config/paper_trading.yaml",
    quarantine_path: Path,
    dry_run: bool,
) -> dict[str, Any]:
    portfolio_name = portfolio_name or runtime_root.name
    quarantine = QuarantineWriter(quarantine_path)

    control_dir = runtime_root / "control"
    audit_path = runtime_root / "audit" / "audit.sqlite"
    idempotency_path = runtime_root / "execution" / "idempotency.sqlite"
    if not audit_path.is_file():
        raise ValueError(f"required audit.sqlite not found: {audit_path}")

    signal_source = _signal_source_for_strategy(strategy_id, strategies_path)
    audit_events = _load_audit_events(audit_path)
    idempotency_reservations = _load_idempotency(idempotency_path)
    source_event_type_counts: dict[str, int] = {}
    for events in audit_events.values():
        for event_type in events:
            source_event_type_counts[event_type] = source_event_type_counts.get(event_type, 0) + 1

    if not dry_run:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            seed_execution_reference_data(
                connection,
                strategies_path=strategies_path,
                strategy_versions_dir=strategy_versions_dir,
                risk_limits_path=risk_limits_path,
                paper_config_path=paper_config_path,
            )

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        portfolio_row = connection.execute(
            "SELECT portfolio_id FROM portfolios WHERE name = %s", (portfolio_name,)
        ).fetchone()
        if portfolio_row is None:
            raise ValueError(f"unknown portfolio {portfolio_name!r} — run scripts/db/seed.py first")
        portfolio_id = portfolio_row["portfolio_id"]

        strategy_version_row = connection.execute(
            """
            SELECT strategy_version_id FROM strategy_versions
            WHERE strategy_id = %s AND is_active = true
            ORDER BY version DESC LIMIT 1
            """,
            (strategy_id,),
        ).fetchone()
        if strategy_version_row is None:
            raise ValueError(f"no active strategy_version for strategy_id={strategy_id!r}")
        strategy_version_id = strategy_version_row["strategy_version_id"]

        risk_limits_row = connection.execute(
            "SELECT risk_limits_version_id FROM risk_limits WHERE effective_to IS NULL"
        ).fetchone()
        if risk_limits_row is None:
            raise ValueError("no open risk_limits version — run scripts/db/seed.py first")
        risk_limits_version_id = risk_limits_row["risk_limits_version_id"]

        history_counts = _import_history(
            connection,
            audit_events=audit_events,
            idempotency_reservations=idempotency_reservations,
            portfolio_id=portfolio_id,
            strategy_version_id=strategy_version_id,
            risk_limits_version_id=risk_limits_version_id,
            signal_source=signal_source,
            quarantine=quarantine,
            dry_run=dry_run,
        )

    portfolio_store = PostgresPortfolioStore(
        database_url,
        portfolio_id=portfolio_id,
        signal_source=signal_source,
        risk_limits_version_id=risk_limits_version_id,
    )
    try:
        current_state = _import_current_state(
            portfolio_store,
            control_dir=control_dir,
            cash_asset=cash_asset,
            quarantine=quarantine,
            dry_run=dry_run,
        )
    finally:
        portfolio_store.close()
        close_database_pools()

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        destination_counts = _destination_counts(connection, portfolio_id)

    quarantine_count = quarantine.flush()

    return {
        "dry_run": dry_run,
        "runtime_root": str(runtime_root),
        "portfolio_name": portfolio_name,
        "portfolio_id": portfolio_id,
        "strategy_id": strategy_id,
        "strategy_version_id": strategy_version_id,
        "risk_limits_version_id": risk_limits_version_id,
        "source": {
            "audit_correlations": len(audit_events),
            "audit_event_type_counts": source_event_type_counts,
            "idempotency_reservations": len(idempotency_reservations),
        },
        "history_imported": {
            "signals": history_counts.signals,
            "orders": history_counts.orders,
            "order_events": history_counts.order_events,
            "executions": history_counts.executions,
            "risk_events": history_counts.risk_events,
        },
        "current_state": current_state,
        "destination": destination_counts,
        "quarantine_path": str(quarantine_path),
        "quarantine_count": quarantine_count,
        "quarantine_reason_counts": history_counts.quarantined,
        "unresolved_history": bool(audit_events),
        "portfolio_state_unavailable": bool(audit_events),
        "idempotent_key": (
            "orders.order_id=correlation_id; signals/order_events/risk_events/"
            "executions deduped on (natural id, event_type, exact original timestamp)"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        required=True,
        help="Frozen copy of one runtime/paper* directory — never the live tree",
    )
    parser.add_argument("--database-url", default=os.environ.get("MIGRATION_DATABASE_URL"))
    parser.add_argument(
        "--portfolio-name",
        default=None,
        help="Defaults to --runtime-root's directory name (e.g. paper-kraken)",
    )
    parser.add_argument(
        "--strategy-id",
        required=True,
        help=(
            "Required — audit payloads carry no strategy identity, only the "
            "operator running this import knows which strategy produced "
            "this frozen directory (config/strategies.yaml id)"
        ),
    )
    parser.add_argument("--cash-asset", default="USD")
    parser.add_argument("--strategies", type=Path, default=REPO_ROOT / "config/strategies.yaml")
    parser.add_argument(
        "--strategy-versions", type=Path, default=REPO_ROOT / "config/strategy_versions"
    )
    parser.add_argument("--risk-limits", type=Path, default=REPO_ROOT / "config/risk_limits.yaml")
    parser.add_argument(
        "--paper-config", type=Path, default=REPO_ROOT / "config/paper_trading.yaml"
    )
    parser.add_argument(
        "--quarantine",
        type=Path,
        default=None,
        help="Defaults to <runtime-root-name>-quarantine.jsonl next to --report",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    if not args.runtime_root.is_dir():
        raise SystemExit(f"--runtime-root not found: {args.runtime_root}")
    url = require_database_url(args.database_url, variable="MIGRATION_DATABASE_URL")
    quarantine_path = args.quarantine or (
        (args.report.parent if args.report else Path.cwd())
        / f"{args.runtime_root.name}-quarantine.jsonl"
    )

    report = import_execution(
        runtime_root=args.runtime_root,
        database_url=url,
        strategy_id=args.strategy_id,
        portfolio_name=args.portfolio_name,
        cash_asset=args.cash_asset,
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
