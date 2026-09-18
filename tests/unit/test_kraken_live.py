"""KrakenLiveBroker — mock HTTP, validare AssetPairs, cl_ord_id, fără rețea live."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest

from src.execution.key_policy import assert_live_key_policy
from src.execution.kraken_live import (
    KrakenLiveBroker,
    build_kraken_live_broker,
    parse_asset_pairs,
    sign_private_request,
    to_cl_ord_id,
)
from src.execution.types import OrderRequest

_ASSET_PAIRS = {
    "error": [],
    "result": {
        "XETHZUSD": {
            "altname": "ETHUSD",
            "lot_decimals": 8,
            "pair_decimals": 2,
            "ordermin": "0.01",
            "costmin": "10",
            "tick_size": "0.01",
        }
    },
}


def _policy():
    return assert_live_key_policy(
        {
            "LIVE_TRADING_ENABLED": "true",
            "KRAKEN_SPOT_API_KEY": "key",
            "KRAKEN_SPOT_API_SECRET": "c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0",
            "KRAKEN_SUBACCOUNT": "true",
            "KRAKEN_IP_WHITELIST_CONFIGURED": "true",
            "KRAKEN_KEY_WITHDRAW_ENABLED": "false",
        }
    )


def _order(**overrides) -> OrderRequest:
    payload = {
        "client_order_id": uuid4(),
        "instrument": "ETHUSD",
        "side": "buy",
        "quantity": Decimal("0.02"),
        "order_type": "market",
    }
    payload.update(overrides)
    return OrderRequest(**payload)


def test_cl_ord_id_is_uuid_hex() -> None:
    order_id = UUID("12345678123456781234567812345678")
    assert to_cl_ord_id(order_id) == "12345678123456781234567812345678"
    assert "-" not in to_cl_ord_id(order_id)


def test_sign_is_deterministic() -> None:
    first = sign_private_request(
        secret="c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0",
        url_path="/0/private/AddOrder",
        nonce="1",
        postdata="nonce=1&pair=ETHUSD",
    )
    second = sign_private_request(
        secret="c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0",
        url_path="/0/private/AddOrder",
        nonce="1",
        postdata="nonce=1&pair=ETHUSD",
    )
    assert first == second
    assert first != ""


def test_parse_asset_pairs_maps_universe_symbol() -> None:
    parsed = parse_asset_pairs(_ASSET_PAIRS)
    assert "ETHUSD" in parsed
    assert parsed["ETHUSD"].min_quantity == Decimal("0.01")
    assert parsed["ETHUSD"].min_notional == Decimal("10")


def test_monitor_mode_rejects_submit() -> None:
    broker = KrakenLiveBroker(api_key="k", api_secret="c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0", mode="monitor")
    result = broker.submit(_order())
    assert result.status == "rejected"
    assert result.reason == "monitor_mode_forbids_orders"


def test_trading_requires_policy() -> None:
    with pytest.raises(RuntimeError, match="LiveKeyPolicy"):
        KrakenLiveBroker(api_key="k", api_secret="c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0", mode="trading")


def test_invalid_lot_rejected_without_http() -> None:
    broker = KrakenLiveBroker(
        api_key="k",
        api_secret="c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0",
        mode="trading",
        policy=_policy(),
        constraints=parse_asset_pairs(_ASSET_PAIRS),
        last_price={"ETHUSD": Decimal("2500")},
    )
    result = broker.submit(_order(quantity=Decimal("0.00000001")))
    assert result.status == "rejected"
    assert result.reason in {"quantity_below_minimum", "quantity_not_aligned_to_lot_size"}


def test_add_order_sends_cl_ord_id() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        assert "API-Key" in request.headers
        assert "API-Sign" in request.headers
        return httpx.Response(
            200,
            json={"error": [], "result": {"txid": ["OXXXXX-YYYYY-ZZZZZ"], "descr": {"order": "buy"}}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    order = _order()
    broker = KrakenLiveBroker(
        api_key="k",
        api_secret="c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0",
        mode="trading",
        policy=_policy(),
        http_client=client,
        constraints=parse_asset_pairs(_ASSET_PAIRS),
        last_price={"ETHUSD": Decimal("2500")},
        nonce_fn=lambda: "1",
    )
    result = broker.submit(order)
    assert result.status == "submitted"
    assert result.broker_order_id == "OXXXXX-YYYYY-ZZZZZ"
    assert f"cl_ord_id={to_cl_ord_id(order.client_order_id)}" in seen["body"]
    assert "pair=ETHUSD" in seen["body"]
    assert seen["path"] == "/0/private/AddOrder"


def test_snapshot_maps_balance_and_open_orders() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("Balance"):
            return httpx.Response(200, json={"error": [], "result": {"XETH": "0.5", "ZUSD": "100"}})
        if request.url.path.endswith("OpenOrders"):
            return httpx.Response(
                200,
                json={
                    "error": [],
                    "result": {
                        "open": {
                            "OID": {"cl_ord_id": "abc123", "descr": {"pair": "ETHUSD"}},
                        }
                    },
                },
            )
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    broker = KrakenLiveBroker(
        api_key="k",
        api_secret="c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0",
        mode="monitor",
        http_client=client,
        nonce_fn=lambda: "1",
    )
    state = broker.snapshot()
    assert state.positions["ETHUSD"] == Decimal("0.5")
    assert state.open_client_order_ids == ["abc123"]


def test_build_monitor_rejects_withdraw_flag() -> None:
    with pytest.raises(RuntimeError, match="withdraw-enabled"):
        build_kraken_live_broker(
            {
                "KRAKEN_SPOT_API_KEY": "k",
                "KRAKEN_SPOT_API_SECRET": "s",
                "KRAKEN_KEY_WITHDRAW_ENABLED": "true",
            },
            mode="monitor",
        )
