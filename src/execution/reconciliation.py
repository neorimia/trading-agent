"""Reconciliere local vs broker — la pornire și periodic. Design §8.4."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from src.execution.broker import BrokerState
from src.runtime_io import write_text_atomic

_STRICT = ConfigDict(extra="forbid")


class LocalPortfolioSnapshot(BaseModel):
    model_config = _STRICT

    positions: dict[str, Decimal] = Field(default_factory=dict)
    pending_client_order_ids: list[str] = Field(default_factory=list)


class ReconciliationMismatch(BaseModel):
    model_config = _STRICT

    field: str = Field(min_length=1)
    instrument: str | None = None
    local: str
    broker: str


class ReconciliationReport(BaseModel):
    model_config = _STRICT

    matched: bool
    checked_at: datetime
    mismatches: list[ReconciliationMismatch] = Field(default_factory=list)


class Reconciliation:
    def __init__(self, report_path: str | Path) -> None:
        self._report_path = Path(report_path)
        self._report_path.parent.mkdir(parents=True, exist_ok=True)

    def reconcile(
        self,
        local_state: LocalPortfolioSnapshot,
        broker_state: BrokerState,
    ) -> ReconciliationReport:
        mismatches: list[ReconciliationMismatch] = []
        instruments = sorted(set(local_state.positions) | set(broker_state.positions))
        for instrument in instruments:
            local_qty = local_state.positions.get(instrument, Decimal("0"))
            broker_qty = broker_state.positions.get(instrument, Decimal("0"))
            if local_qty != broker_qty:
                mismatches.append(
                    ReconciliationMismatch(
                        field="position",
                        instrument=instrument,
                        local=str(local_qty),
                        broker=str(broker_qty),
                    )
                )
        local_pending = sorted(local_state.pending_client_order_ids)
        broker_open = sorted(broker_state.open_client_order_ids)
        if local_pending != broker_open:
            mismatches.append(
                ReconciliationMismatch(
                    field="open_orders",
                    instrument=None,
                    local=",".join(local_pending),
                    broker=",".join(broker_open),
                )
            )
        report = ReconciliationReport(
            matched=len(mismatches) == 0,
            checked_at=datetime.now(timezone.utc),
            mismatches=mismatches,
        )
        write_text_atomic(self._report_path, report.model_dump_json())
        return report

    def last_report(self) -> ReconciliationReport | None:
        if not self._report_path.is_file():
            return None
        return ReconciliationReport.model_validate_json(
            self._report_path.read_text(encoding="utf-8")
        )
