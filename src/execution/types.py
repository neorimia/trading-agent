"""OrderRequest / OrderResult — design §4.4."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal[
    "submitted",
    "filled",
    "partially_filled",
    "rejected",
    "unknown",
    "timeout",
]


class OrderRequest(BaseModel):
    model_config = _STRICT

    client_order_id: UUID
    instrument: str = Field(min_length=1)
    side: OrderSide
    quantity: Decimal = Field(gt=0)
    order_type: OrderType = "market"


class OrderResult(BaseModel):
    model_config = _STRICT

    client_order_id: UUID
    status: OrderStatus
    broker_order_id: str | None = None
    filled_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    fill_price: Decimal | None = None
    reason: str | None = None
    # Comision estimat al fill-ului (aceeași unitate ca fill_price * filled_quantity).
    # Implicit 0 pentru brokerii care nu modelează costuri (ex. kraken_live.py, unde
    # comisionul real vine din exchange, nu e simulat aici).
    fee: Decimal = Field(default=Decimal("0"), ge=0)
