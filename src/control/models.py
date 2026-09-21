"""Contracte JSON ale control plane-ului. extra=forbid. Sumele sunt string decimal."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.monitor.broker_monitor import BrokerMonitorSnapshot

_STRICT = ConfigDict(extra="forbid")

AgentStatus = Literal["running", "stopped", "halted"]
VenueStatus = Literal["connected", "stale", "down"]
ServiceStatus = Literal["up", "down"]
TradingMode = Literal["paper", "live"]
ReconciliationStatus = Literal["ok", "mismatch", "unknown"]
OperatorRole = Literal["operator", "observer"]
MarketDataStatus = Literal["ok", "stale", "research_only", "no_adapter", "data_unavailable"]
StrategyKind = Literal["ema_cross", "llm"]
AlertSeverity = Literal["warning", "error"]
WsChannel = Literal["health", "approvals", "alerts", "events"]


class HealthResponse(BaseModel):
    model_config = _STRICT

    agent: AgentStatus
    venue: VenueStatus
    llm: ServiceStatus
    research: ServiceStatus
    ollama: ServiceStatus
    trading_mode: TradingMode
    heartbeat_age_s: float | None
    last_bar_at: datetime | None
    last_bar_instrument: str | None = None
    reconciliation: ReconciliationStatus
    halt_reason: str | None = None
    live_actions_blocked: bool = True
    broker_monitor: BrokerMonitorSnapshot = Field(
        default_factory=lambda: BrokerMonitorSnapshot(status="not_configured")
    )


class PortfolioResponse(BaseModel):
    model_config = _STRICT

    equity: str
    cash: str
    realized_pnl: str
    unrealized_pnl: str
    drawdown: str
    peak_equity: str
    exposure_per_instrument: dict[str, str]
    exposure_per_asset_class: dict[str, str]
    orders_today: int
    starting_cash: str
    incomplete: bool
    as_of: datetime | None


class MarketInstrument(BaseModel):
    model_config = _STRICT

    symbol: str
    venue: str
    asset_class: str
    price: str | None
    change_pct: str | None
    volume: str | None
    volatility: str | None
    spread: str | None
    as_of: datetime | None
    stale: bool
    in_universe: bool = True
    status: MarketDataStatus = "ok"


class BarPoint(BaseModel):
    model_config = _STRICT

    timestamp: datetime
    open: str
    high: str
    low: str
    close: str
    volume: str
    ema_fast: str | None = None
    ema_slow: str | None = None


class BarsResponse(BaseModel):
    model_config = _STRICT

    symbol: str
    timeframe: str
    bars: list[BarPoint]
    stale: bool


class SignalResponse(BaseModel):
    model_config = _STRICT

    symbol: str
    source: Literal["ema_cross", "llm", "none"]
    direction: str | None
    confidence: float | None
    rationale: str | None
    as_of: datetime | None
    sources: list[str]
    is_proposal: bool = True


class PositionRow(BaseModel):
    model_config = _STRICT

    instrument: str
    quantity: str
    entry_price: str | None
    last_price: str | None
    unrealized_pnl: str | None
    stop_loss: str | None
    take_profit: str | None
    stop_source: str = "engine_default_2pct"


class OrderRow(BaseModel):
    model_config = _STRICT

    correlation_id: UUID
    client_order_id: str | None = None
    instrument: str
    side: str | None
    quantity: str | None
    status: str
    fill_price: str | None = None
    filled_quantity: str | None = None
    fee: str | None = None
    slippage: str | None = None
    timestamp: datetime
    reason: str | None = None
    trading_mode: TradingMode


class PendingApproval(BaseModel):
    model_config = _STRICT

    correlation_id: UUID
    requested_at: datetime
    expires_at: datetime
    remaining_s: float
    instrument: str
    side: str
    quantity: str
    reject_reason: str | None
    requires_human_approval: bool
    estimated_notional: str | None = None
    last_price: str | None = None
    rationale: str | None = None
    stale: bool
    trading_mode: TradingMode
    approve_blocked_reason: str | None = None


class ApprovalDecisionRequest(BaseModel):
    model_config = _STRICT

    approved: bool
    reason: str = Field(min_length=1)
    decided_by: str = Field(min_length=1, default="human")


class CircuitBreakerView(BaseModel):
    model_config = _STRICT

    max_consecutive_errors: int
    max_consecutive_losses: int
    halt_on_unknown_order_result: bool
    state: Literal["RUNNING", "HALTED"]


class CircuitBreakerLimitsWrite(BaseModel):
    model_config = _STRICT

    max_consecutive_errors: int = Field(gt=0)
    max_consecutive_losses: int = Field(gt=0)
    halt_on_unknown_order_result: bool


class RiskLimitsView(BaseModel):
    model_config = _STRICT

    max_notional_per_order: str
    max_exposure_per_instrument: str
    max_exposure_per_asset_class: str
    max_daily_loss: str
    max_drawdown: str
    max_orders_per_day: int
    circuit_breaker: CircuitBreakerView
    consumed_daily_loss: str
    remaining_daily_loss: str
    consumed_drawdown: str
    remaining_drawdown: str
    consumed_orders_today: int
    remaining_orders_today: int
    restart_required_on_write: bool = True


class RiskLimitsWrite(BaseModel):
    model_config = _STRICT

    max_notional_per_order: str
    max_exposure_per_instrument: str
    max_exposure_per_asset_class: str
    max_daily_loss: str
    max_drawdown: str
    max_orders_per_day: int
    circuit_breaker: CircuitBreakerLimitsWrite
    confirmation_token: str = Field(min_length=1)


class HaltRequest(BaseModel):
    model_config = _STRICT

    reason: str = Field(min_length=1)


class AgentEventRow(BaseModel):
    model_config = _STRICT

    id: int
    timestamp: datetime
    correlation_id: UUID
    event_type: str
    payload: dict[str, Any]


class AgentEventsResponse(BaseModel):
    model_config = _STRICT

    events: list[AgentEventRow]
    next_cursor: int | None


class ResearchDocumentView(BaseModel):
    model_config = _STRICT

    doc_id: str
    url: str
    title: str
    source_id: str
    published_at: datetime | None
    fetched_at: datetime
    event_date: datetime | None
    assets_mentioned: list[str]
    category: str
    summary: str | None
    sentiment_score: float | None
    impact_magnitude: str | None
    impact_direction: str | None
    confidence_score: float
    stale: bool
    contradicts: list[str]
    extracted_text: str


class SecuritySettings(BaseModel):
    model_config = _STRICT

    environment: str
    trading_mode: TradingMode
    live_trading_enabled: bool
    broker_paper_mode: bool
    kraken_spot_key_present: bool
    kraken_spot_secret_present: bool
    withdraw_enabled: bool
    ip_whitelist_configured: bool
    subaccount: bool
    operator_role: OperatorRole
    data_retention: str
    webhooks_configured: bool = False
    notifications_configured: bool = False


class StrategyRow(BaseModel):
    model_config = _STRICT

    id: str
    name: str
    kind: StrategyKind
    enabled: bool
    params: dict[str, str]
    last_paper_sessions: int | None = None
    last_paper_halted: bool | None = None
    last_backtest_ref: str | None = None


class StrategyToggleRequest(BaseModel):
    model_config = _STRICT

    enabled: bool
    confirmation_token: str = Field(min_length=1)


class OperatorAnalyzeRequest(BaseModel):
    """Consolă → control. Nu e ordin. Doar tipurile Nivel 1."""

    model_config = _STRICT

    instrument: str = Field(min_length=1)
    analysis_type: Literal["priced_in", "technical", "news_impact", "daily_plan"]
    timeframe: str = Field(default="1d", min_length=1)


class AlertRow(BaseModel):
    model_config = _STRICT

    id: str
    severity: AlertSeverity
    title: str
    detail: str
    persistent: bool = True


class WsEnvelope(BaseModel):
    model_config = _STRICT

    channel: WsChannel
    payload: dict[str, Any]
    sent_at: datetime


class AckResponse(BaseModel):
    model_config = _STRICT

    ok: bool
    detail: str
    restart_required: bool = False
