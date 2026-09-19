"""Broker monitor sidecar — snapshot only, never submit."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from src.execution.kraken_live import KrakenLiveBroker, build_kraken_live_broker
from src.execution.types import OrderRequest
from src.monitor.broker_monitor import (
    BrokerMonitorSnapshot,
    load_broker_monitor,
    poll_once,
    run_monitor_loop,
)


def _order() -> OrderRequest:
    return OrderRequest(
        client_order_id=uuid4(),
        instrument="ETHUSD",
        side="buy",
        quantity=Decimal("0.02"),
        order_type="market",
    )


def _monitor_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("Balance"):
            return httpx.Response(200, json={"error": [], "result": {"XETH": "0.5"}})
        if request.url.path.endswith("OpenOrders"):
            return httpx.Response(200, json={"error": [], "result": {"open": {}}})
        return httpx.Response(500)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_poll_once_writes_snapshot_without_submit(tmp_path: Path) -> None:
    broker = KrakenLiveBroker(
        api_key="k",
        api_secret="c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0",
        mode="monitor",
        http_client=_monitor_client(),
        nonce_fn=lambda: "1",
    )
    path = tmp_path / "broker_monitor.json"
    now = datetime(2026, 9, 19, tzinfo=timezone.utc)
    snap = poll_once(broker, path, now=now)
    assert snap.status == "polling"
    assert snap.positions["ETHUSD"] == "0.5"
    loaded = load_broker_monitor(path)
    assert loaded.mode == "monitor"
    assert broker.submit(_order()).reason == "monitor_mode_forbids_orders"


def test_withdraw_enabled_refuses_monitor_builder() -> None:
    with pytest.raises(RuntimeError, match="withdraw-enabled"):
        build_kraken_live_broker(
            {
                "KRAKEN_SPOT_API_KEY": "k",
                "KRAKEN_SPOT_API_SECRET": "c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0",
                "KRAKEN_KEY_WITHDRAW_ENABLED": "true",
            },
            mode="monitor",
        )


def test_missing_file_is_not_configured(tmp_path: Path) -> None:
    snap = load_broker_monitor(tmp_path / "missing.json")
    assert snap == BrokerMonitorSnapshot(status="not_configured")


def test_run_loop_respects_max_polls(tmp_path: Path) -> None:
    broker = KrakenLiveBroker(
        api_key="k",
        api_secret="c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0",
        mode="monitor",
    )
    sleeps: list[float] = []
    run_monitor_loop(
        broker,
        tmp_path / "broker_monitor.json",
        poll_interval_s=7,
        sleep_fn=sleeps.append,
        max_polls=1,
    )
    assert sleeps == []
    assert load_broker_monitor(tmp_path / "broker_monitor.json").status in {
        "polling",
        "error",
    }
