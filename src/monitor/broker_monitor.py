"""Sidecar Kraken monitor — Balance/OpenOrders only. Never submit. Never paper recon."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.execution.broker import BrokerState
from src.execution.key_policy import redact_secrets
from src.runtime_io import write_text_atomic

_STRICT = ConfigDict(extra="forbid")

BrokerMonitorStatus = Literal["not_configured", "polling", "error"]


class BrokerMonitorSnapshot(BaseModel):
    model_config = _STRICT

    status: BrokerMonitorStatus
    polled_at: datetime | None = None
    positions: dict[str, str] = Field(default_factory=dict)
    open_client_order_ids: list[str] = Field(default_factory=list)
    last_price: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    mode: Literal["monitor"] = "monitor"


def snapshot_from_broker_state(
    state: BrokerState,
    *,
    polled_at: datetime,
) -> BrokerMonitorSnapshot:
    return BrokerMonitorSnapshot(
        status="polling",
        polled_at=polled_at,
        positions={key: format(value, "f") for key, value in state.positions.items()},
        open_client_order_ids=list(state.open_client_order_ids),
        last_price={key: format(value, "f") for key, value in state.last_price.items()},
        error=None,
    )


def write_broker_monitor(path, snapshot: BrokerMonitorSnapshot) -> None:
    write_text_atomic(path, snapshot.model_dump_json())


def load_broker_monitor(path) -> BrokerMonitorSnapshot:
    from pathlib import Path

    target = Path(path)
    if not target.is_file():
        return BrokerMonitorSnapshot(status="not_configured")
    try:
        return BrokerMonitorSnapshot.model_validate_json(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return BrokerMonitorSnapshot(status="error", error="unreadable_snapshot")


def poll_once(broker, path, *, now: datetime | None = None, environ=None) -> BrokerMonitorSnapshot:
    moment = now if now is not None else datetime.now(timezone.utc)
    try:
        state = broker.snapshot()
        snap = snapshot_from_broker_state(state, polled_at=moment)
    except Exception as exc:
        snap = BrokerMonitorSnapshot(
            status="error",
            polled_at=moment,
            error=redact_secrets(str(exc), environ),
        )
    write_broker_monitor(path, snap)
    return snap


def run_monitor_loop(
    broker,
    path,
    *,
    poll_interval_s: float = 30.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    should_stop: Callable[[], bool] | None = None,
    max_polls: int | None = None,
    environ=None,
) -> None:
    polls = 0
    while True:
        if should_stop is not None and should_stop():
            break
        poll_once(broker, path, environ=environ)
        polls += 1
        if max_polls is not None and polls >= max_polls:
            break
        if should_stop is not None and should_stop():
            break
        sleep_fn(poll_interval_s)
