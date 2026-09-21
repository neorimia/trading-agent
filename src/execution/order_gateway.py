"""OrderGateway — submit idempotent + cancel_all. Nu importă src.llm."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from src.execution.broker import BrokerClient
from src.execution.idempotency_store import DuplicateClientOrderId
from src.execution.types import OrderRequest, OrderResult


class IdempotencyStoreProtocol(Protocol):
    """Shared shape of `IdempotencyStore` (SQLite) and `PostgresIdempotencyStore`."""

    def reserve(
        self,
        client_order_id: UUID,
        *,
        order: OrderRequest | None = None,
        correlation_id: UUID | None = None,
    ) -> None: ...

    def store_result(self, result: OrderResult) -> None: ...


class OrderGateway:
    def __init__(self, store: IdempotencyStoreProtocol, broker: BrokerClient) -> None:
        self._store = store
        self._broker = broker

    def submit(self, order: OrderRequest, *, correlation_id: UUID | None = None) -> OrderResult:
        """`correlation_id` is the paper-loop decision id (design §8.5 `orders.order_id`),
        distinct from `order.client_order_id` (the idempotency key). Only the Postgres
        backend uses it; SQLite ignores it (interface parity, see
        `IdempotencyStore.reserve`)."""
        try:
            self._store.reserve(order.client_order_id, order=order, correlation_id=correlation_id)
        except DuplicateClientOrderId as exc:
            if exc.stored is not None:
                return exc.stored
            return OrderResult(
                client_order_id=order.client_order_id,
                status="submitted",
                reason="duplicate_in_flight",
            )
        result = self._broker.submit(order)
        self._store.store_result(result)
        return result

    def cancel_all(self, reason: str) -> None:
        self._broker.cancel_all(reason)
