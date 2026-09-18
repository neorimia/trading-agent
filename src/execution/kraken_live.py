"""KrakenLiveBroker — BrokerClient REST Spot. Zero Nautilus live exec.

Mod implicit: monitor (Balance/OpenOrders). AddOrder e permis doar după
`assert_live_key_policy` și `trading_enabled=True`.

Nu loghează chei sau semnături. Testele injectează httpx.MockTransport.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from decimal import Decimal
from typing import Any, Callable, Literal
from urllib.parse import urlencode
from uuid import UUID

import httpx

from src.data.venue_registry import (
    InstrumentConstraints,
    UNIVERSE_TO_KRAKEN,
    constraints_for,
    execution_pair,
)
from src.execution.broker import BrokerState
from src.execution.key_policy import LiveKeyPolicy, assert_live_key_policy, redact_secrets
from src.execution.order_validation import validate_order_constraints
from src.execution.types import OrderRequest, OrderResult

KRAKEN_API_BASE = "https://api.kraken.com"
ASSETPAIRS_PATH = "/0/public/AssetPairs"
ADD_ORDER_PATH = "/0/private/AddOrder"
CANCEL_ALL_PATH = "/0/private/CancelAll"
BALANCE_PATH = "/0/private/Balance"
OPEN_ORDERS_PATH = "/0/private/OpenOrders"

BrokerMode = Literal["monitor", "trading"]

# Kraken cl_ord_id: identificator client; UUID fără cratime e 32 hex (în limita 36).
def to_cl_ord_id(client_order_id: UUID) -> str:
    return client_order_id.hex


def sign_private_request(*, secret: str, url_path: str, nonce: str, postdata: str) -> str:
    message = (nonce + postdata).encode()
    sha256 = hashlib.sha256(message).digest()
    mac = hmac.new(base64.b64decode(secret), url_path.encode() + sha256, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()


def _kraken_errors(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["unexpected_payload"]
    errors = payload.get("error") or []
    if isinstance(errors, list):
        return [str(item) for item in errors]
    return [str(errors)]


def parse_asset_pairs(
    payload: object,
    universe_to_pair: dict[str, str] | None = None,
) -> dict[str, InstrumentConstraints]:
    """Mapează AssetPairs Kraken → constraints pe simbolul din universe."""
    mapping = universe_to_pair if universe_to_pair is not None else UNIVERSE_TO_KRAKEN
    errors = _kraken_errors(payload)
    if errors:
        raise ValueError("Kraken AssetPairs error: " + ", ".join(errors))
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        raise ValueError("Kraken AssetPairs result missing")
    by_altname: dict[str, dict[str, Any]] = {}
    for raw in payload["result"].values():
        if not isinstance(raw, dict):
            continue
        altname = str(raw.get("altname") or "")
        if altname:
            by_altname[altname] = raw
    parsed: dict[str, InstrumentConstraints] = {}
    for universe, pair in mapping.items():
        raw = by_altname.get(pair)
        if raw is None:
            continue
        lot_decimals = int(raw.get("lot_decimals", 8))
        pair_decimals = int(raw.get("pair_decimals", 2))
        lot_size = Decimal("1").scaleb(-lot_decimals)
        tick = Decimal(str(raw.get("tick_size") or Decimal("1").scaleb(-pair_decimals)))
        ordermin = Decimal(str(raw.get("ordermin") or lot_size))
        costmin = Decimal(str(raw.get("costmin") or "0"))
        parsed[universe] = InstrumentConstraints(
            min_notional=costmin if costmin > 0 else constraints_for(universe).min_notional,
            lot_size=lot_size,
            tick_size=tick,
            min_quantity=ordermin,
            price_precision=pair_decimals,
            size_precision=lot_decimals,
            price_increment=tick,
            size_increment=lot_size,
        )
    return parsed


def _balance_to_positions(result: dict[str, Any]) -> dict[str, Decimal]:
    """Spot long-only: ETH/XETH → ETHUSD, XBT/XXBT → BTCUSD."""
    aliases = {
        "ETHUSD": ("ETH", "XETH", "ETH.F"),
        "BTCUSD": ("XXBT", "XBT", "BTC", "BTC.F"),
    }
    positions: dict[str, Decimal] = {}
    for universe, names in aliases.items():
        total = Decimal("0")
        for name in names:
            raw = result.get(name)
            if raw is not None:
                total += Decimal(str(raw))
        if total > 0:
            positions[universe] = total
    return positions


class KrakenLiveBroker:
    """Client REST Kraken Spot. Implementează BrokerClient."""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        mode: BrokerMode = "monitor",
        http_client: httpx.Client | None = None,
        base_url: str = KRAKEN_API_BASE,
        constraints: dict[str, InstrumentConstraints] | None = None,
        last_price: dict[str, Decimal] | None = None,
        nonce_fn: Callable[[], str] | None = None,
        policy: LiveKeyPolicy | None = None,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("KrakenLiveBroker requires api_key and api_secret")
        if mode == "trading" and policy is None:
            raise RuntimeError("trading mode requires a verified LiveKeyPolicy")
        self._api_key = api_key
        self._api_secret = api_secret
        self._mode = mode
        self._http_client = http_client
        self._owns_client = http_client is None
        self._base_url = base_url.rstrip("/")
        self._constraints = constraints if constraints is not None else {}
        self._last_price: dict[str, Decimal] = dict(last_price or {})
        self._nonce_fn = nonce_fn if nonce_fn is not None else lambda: str(int(time.time() * 1000))
        self._policy = policy
        self._open_cl_ord_ids: list[str] = []
        self._positions: dict[str, Decimal] = {}

    def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def set_last_price(self, instrument: str, price: Decimal) -> None:
        if price <= 0:
            raise ValueError("price must be positive")
        self._last_price[instrument] = price

    def load_asset_pairs(self) -> dict[str, InstrumentConstraints]:
        response = self._client().get(self._base_url + ASSETPAIRS_PATH)
        response.raise_for_status()
        parsed = parse_asset_pairs(response.json())
        self._constraints.update(parsed)
        return parsed

    def submit(self, order: OrderRequest) -> OrderResult:
        if self._mode != "trading":
            return OrderResult(
                client_order_id=order.client_order_id,
                status="rejected",
                reason="monitor_mode_forbids_orders",
            )
        try:
            pair = execution_pair(order.instrument)
        except ValueError:
            return OrderResult(
                client_order_id=order.client_order_id,
                status="rejected",
                reason="instrument_not_mapped",
            )
        constraints = self._constraints.get(order.instrument)
        if constraints is None:
            try:
                constraints = constraints_for(order.instrument)
            except ValueError:
                return OrderResult(
                    client_order_id=order.client_order_id,
                    status="rejected",
                    reason="missing_constraints",
                )
        reason = validate_order_constraints(
            order,
            constraints,
            last_price=self._last_price.get(order.instrument),
        )
        if reason is not None:
            return OrderResult(
                client_order_id=order.client_order_id,
                status="rejected",
                reason=reason,
            )
        cl_ord_id = to_cl_ord_id(order.client_order_id)
        payload = {
            "pair": pair,
            "type": order.side,
            "ordertype": order.order_type,
            "volume": format(order.quantity, "f"),
            "cl_ord_id": cl_ord_id,
        }
        try:
            body = self._private_post(ADD_ORDER_PATH, payload)
        except httpx.TimeoutException:
            self._remember_open(cl_ord_id)
            return OrderResult(
                client_order_id=order.client_order_id,
                status="timeout",
                reason="http_timeout",
            )
        except httpx.HTTPError as exc:
            return OrderResult(
                client_order_id=order.client_order_id,
                status="unknown",
                reason=redact_secrets(f"http_error:{exc}"),
            )
        errors = _kraken_errors(body)
        if errors:
            return OrderResult(
                client_order_id=order.client_order_id,
                status="rejected",
                reason="kraken:" + ",".join(errors),
            )
        result = body.get("result") if isinstance(body, dict) else None
        txid = None
        if isinstance(result, dict):
            ids = result.get("txid")
            if isinstance(ids, list) and ids:
                txid = str(ids[0])
            elif ids:
                txid = str(ids)
        status: Literal["submitted", "filled"] = "submitted"
        filled = Decimal("0")
        fill_price = None
        descr = result.get("descr") if isinstance(result, dict) else None
        if isinstance(descr, dict) and descr.get("order"):
            status = "submitted"
        return OrderResult(
            client_order_id=order.client_order_id,
            status=status,
            broker_order_id=txid,
            filled_quantity=filled,
            fill_price=fill_price,
        )

    def cancel_all(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("cancel_all reason must be a non-empty string")
        if self._mode != "trading":
            self._open_cl_ord_ids.clear()
            return
        try:
            self._private_post(CANCEL_ALL_PATH, {})
        except httpx.HTTPError:
            pass
        self._open_cl_ord_ids.clear()

    def snapshot(self) -> BrokerState:
        try:
            balances = self._private_post(BALANCE_PATH, {})
            orders = self._private_post(OPEN_ORDERS_PATH, {})
        except httpx.HTTPError:
            return BrokerState(
                positions=dict(self._positions),
                open_client_order_ids=list(self._open_cl_ord_ids),
                last_price=dict(self._last_price),
            )
        bal_errors = _kraken_errors(balances)
        if not bal_errors and isinstance(balances, dict) and isinstance(balances.get("result"), dict):
            self._positions = _balance_to_positions(balances["result"])
        open_ids: list[str] = []
        order_errors = _kraken_errors(orders)
        if not order_errors and isinstance(orders, dict) and isinstance(orders.get("result"), dict):
            open_block = orders["result"].get("open")
            if isinstance(open_block, dict):
                for entry in open_block.values():
                    if not isinstance(entry, dict):
                        continue
                    cl_id = entry.get("cl_ord_id") or entry.get("userref")
                    if cl_id:
                        open_ids.append(str(cl_id))
        self._open_cl_ord_ids = sorted(open_ids)
        return BrokerState(
            positions=dict(self._positions),
            open_client_order_ids=list(self._open_cl_ord_ids),
            last_price=dict(self._last_price),
        )

    def _client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=15.0)
        return self._http_client

    def _private_post(self, path: str, fields: dict[str, str]) -> dict[str, Any]:
        nonce = self._nonce_fn()
        data = {"nonce": nonce, **fields}
        postdata = urlencode(data)
        signature = sign_private_request(
            secret=self._api_secret,
            url_path=path,
            nonce=nonce,
            postdata=postdata,
        )
        response = self._client().post(
            self._base_url + path,
            content=postdata,
            headers={
                "API-Key": self._api_key,
                "API-Sign": signature,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("unexpected Kraken private payload")
        return payload


def build_kraken_live_broker(
    environ: dict[str, str],
    *,
    mode: BrokerMode,
    http_client: httpx.Client | None = None,
) -> KrakenLiveBroker:
    policy = assert_live_key_policy(environ) if mode == "trading" else None
    if mode == "monitor":
        if not environ.get("KRAKEN_SPOT_API_KEY") or not environ.get("KRAKEN_SPOT_API_SECRET"):
            raise RuntimeError("monitor mode still requires spot API keys")
        if environ.get("KRAKEN_KEY_WITHDRAW_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            raise RuntimeError("withdraw-enabled keys are forbidden even in monitor mode")
    return KrakenLiveBroker(
        api_key=environ["KRAKEN_SPOT_API_KEY"],
        api_secret=environ["KRAKEN_SPOT_API_SECRET"],
        mode=mode,
        http_client=http_client,
        policy=policy,
    )
