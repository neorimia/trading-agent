"""OrderGateway — submit idempotent + cancel_all. Nu importă src.llm."""

from __future__ import annotations

from src.execution.broker import BrokerClient
from src.execution.idempotency_store import DuplicateClientOrderId, IdempotencyStore
from src.execution.types import OrderRequest, OrderResult


class OrderGateway:
    def __init__(self, store: IdempotencyStore, broker: BrokerClient) -> None:
        self._store = store
        self._broker = broker

    def submit(self, order: OrderRequest) -> OrderResult:
        try:
            self._store.reserve(order.client_order_id)
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
