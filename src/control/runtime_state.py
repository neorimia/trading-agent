"""Citire stare deterministă din runtime/, config/ și audit. Fără src.llm."""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4

import yaml

from src.audit.audit_log import AuditLog
from src.audit.events import AuditEvent
from src.control.models import (
    AgentEventRow,
    AgentEventsResponse,
    AlertRow,
    BarPoint,
    BarsResponse,
    CircuitBreakerView,
    HealthResponse,
    MarketInstrument,
    OrderRow,
    PendingApproval,
    PortfolioResponse,
    PositionRow,
    ResearchDocumentView,
    RiskLimitsView,
    SecuritySettings,
    SignalResponse,
    StrategyRow,
)
from src.control.settings import (
    ControlSettings,
    RISK_CONFIRMATION_TOKEN,
    STRATEGY_DISABLE_TOKEN,
    STRATEGY_ENABLE_TOKEN,
)
from src.data.sources import Bar
from src.engine.analysis_types import (
    AnalysisContext,
    AnalysisRunResponse,
    ParsedAnalysis,
    RejectedAnalysis,
)
from src.engine.daily_plan import build_daily_plan
from src.engine.indicators import bars_upto, indicator_snapshot, technical_facts_bundle
from src.engine.paper_config import load_paper_trading_config
from src.engine.signals import ema, ema_cross_direction
from src.engine.stress import stress_portfolio
from src.execution.key_policy import load_live_key_policy
from src.execution.reconciliation import LocalPortfolioSnapshot, ReconciliationReport
from src.research.context_builder import build_external_context
from src.research.models import ResearchDocument
from src.research.store import MetadataStore
from src.risk.config_schema import RiskLimits, load_risk_limits
from src.risk.kill_switch import KillSwitch
from src.risk.portfolio_state import load_instrument_rules

STOP_FRACTION = Decimal("0.02")
PingFn = Callable[[str], bool]
FetchBarsFn = Callable[[str, datetime, datetime, str], list[Bar]]
PidAliveFn = Callable[[int], bool]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dstr(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _dec(raw: object, default: Decimal = Decimal("0")) -> Decimal:
    if raw is None:
        return default
    try:
        return Decimal(str(raw))
    except Exception:
        return default


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else None


def _parse_dt(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def trading_mode(settings: ControlSettings) -> str:
    if settings.live_trading_enabled:
        return "live"
    return "paper"


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import os

        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(pid_path: Path) -> int | None:
    if not pid_path.is_file():
        return None
    raw = pid_path.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return None
    return int(raw)


def process_running(pid_path: Path, alive: PidAliveFn = pid_is_alive) -> bool:
    pid = read_pid(pid_path)
    return pid is not None and alive(pid)


def _heartbeat_age(path: Path, now: datetime) -> float | None:
    payload = _read_json(path)
    if payload is None:
        return None
    recorded = _parse_dt(payload.get("timestamp"))
    if recorded is None:
        return None
    return (now - recorded.astimezone(timezone.utc)).total_seconds()


def _last_bar(path: Path) -> tuple[datetime | None, str | None, Decimal | None]:
    payload = _read_json(path)
    if payload is None:
        return None, None, None
    recorded = _parse_dt(payload.get("bar_timestamp")) or _parse_dt(payload.get("timestamp"))
    instrument = payload.get("instrument")
    close = _dec(payload.get("close")) if payload.get("close") is not None else None
    return recorded, str(instrument) if instrument else None, close


def ping_http(url: str, timeout_s: float = 1.5) -> bool:
    import httpx

    try:
        response = httpx.get(url, timeout=timeout_s)
    except httpx.HTTPError:
        return False
    return response.status_code < 500


def build_health(
    settings: ControlSettings,
    *,
    now: datetime | None = None,
    ping: PingFn = ping_http,
    alive: PidAliveFn = pid_is_alive,
) -> HealthResponse:
    moment = now if now is not None else _now()
    paths = settings.paths
    kill = KillSwitch(paths.halt_flag)
    halted = kill.is_active()
    halt_reason = None
    if halted:
        payload = _read_json(paths.halt_flag)
        halt_reason = str(payload.get("reason")) if payload and payload.get("reason") else "halted"
    running = process_running(paths.agent_pid, alive=alive)
    if halted:
        agent = "halted"
    elif running:
        agent = "running"
    else:
        agent = "stopped"
    last_bar_at, last_instrument, _ = _last_bar(paths.last_bar)
    heartbeat_age = _heartbeat_age(paths.heartbeat, moment)
    venue: str
    if last_bar_at is None:
        venue = "down" if running else "down"
    else:
        age = (moment - last_bar_at.astimezone(timezone.utc)).total_seconds()
        venue = "stale" if age > settings.stale_data_threshold_s else "connected"
    recon = "unknown"
    if paths.reconciliation.is_file():
        report = ReconciliationReport.model_validate_json(
            paths.reconciliation.read_text(encoding="utf-8")
        )
        recon = "ok" if report.matched else "mismatch"
    mode = trading_mode(settings)
    return HealthResponse(
        agent=agent,  # type: ignore[arg-type]
        venue=venue,  # type: ignore[arg-type]
        llm="up" if ping(settings.llm_health_url) else "down",
        research="up" if ping(settings.research_health_url) else "down",
        trading_mode=mode,  # type: ignore[arg-type]
        heartbeat_age_s=heartbeat_age,
        last_bar_at=last_bar_at,
        last_bar_instrument=last_instrument,
        reconciliation=recon,  # type: ignore[arg-type]
        halt_reason=halt_reason,
        live_actions_blocked=mode == "live" or halted or venue != "connected",
    )


def _audit(paths) -> AuditLog:
    return AuditLog(paths.audit_db)


def build_portfolio(settings: ControlSettings, *, now: datetime | None = None) -> PortfolioResponse:
    moment = now if now is not None else _now()
    paper = load_paper_trading_config(settings.paths.paper_config)
    starting = paper.starting_cash
    cash = starting
    realized = Decimal("0")
    qty_from_fills: dict[str, Decimal] = {}
    avg_price: dict[str, Decimal] = {}
    orders_today = 0
    today = moment.date().isoformat()
    incomplete = True
    if settings.paths.audit_db.is_file():
        incomplete = False
        log = _audit(settings.paths)
        for event in log.list_events():
            if event.timestamp.date().isoformat() == today and event.event_type in {
                "order_submitted",
                "fill",
            }:
                orders_today += 1 if event.event_type == "order_submitted" else 0
            if event.event_type != "fill":
                continue
            payload = event.payload
            instrument = str(payload.get("instrument") or paper.instrument)
            side = str(payload.get("side") or "buy")
            qty = _dec(payload.get("filled_quantity") or payload.get("quantity"))
            price = _dec(payload.get("fill_price") or payload.get("price"))
            if qty <= 0 or price <= 0:
                continue
            open_qty = qty_from_fills.get(instrument, Decimal("0"))
            if side == "buy":
                cash -= qty * price
                new_qty = open_qty + qty
                if new_qty > 0:
                    prev_avg = avg_price.get(instrument, Decimal("0"))
                    avg_price[instrument] = ((prev_avg * open_qty) + qty * price) / new_qty
                qty_from_fills[instrument] = new_qty
            else:
                cash += qty * price
                closed = min(open_qty, qty)
                if closed > 0 and avg_price.get(instrument, Decimal("0")) > 0:
                    realized += (price - avg_price[instrument]) * closed
                qty_from_fills[instrument] = open_qty - closed
                if qty_from_fills[instrument] == 0:
                    avg_price.pop(instrument, None)
    local = _read_json(settings.paths.local_positions)
    positions: dict[str, Decimal] = dict(qty_from_fills)
    if local:
        snapshot = LocalPortfolioSnapshot.model_validate(local)
        positions = dict(snapshot.positions)
        incomplete = False
    last_bar_at, last_instrument, last_close = _last_bar(settings.paths.last_bar)
    last_price = last_close if last_close is not None else Decimal("0")
    instrument = last_instrument or paper.instrument
    if instrument not in positions:
        positions.setdefault(instrument, Decimal("0"))
    _, asset_classes = load_instrument_rules(settings.paths.universe)
    exposure: dict[str, Decimal] = {}
    class_exposure: dict[str, Decimal] = {}
    unrealized = Decimal("0")
    for symbol, qty in positions.items():
        price = last_price if symbol == instrument else last_price
        notional = abs(qty * price)
        exposure[symbol] = notional
        asset_class = asset_classes.get(symbol, "crypto")
        class_exposure[asset_class] = class_exposure.get(asset_class, Decimal("0")) + notional
        entry = avg_price.get(symbol)
        if qty > 0 and entry is not None and price > 0:
            unrealized += (price - entry) * qty
    equity = cash + sum(qty * last_price for qty in positions.values())
    peak = max(starting, equity)
    drawdown = peak - equity if peak > equity else Decimal("0")
    return PortfolioResponse(
        equity=_dstr(equity) or "0",
        cash=_dstr(cash) or "0",
        realized_pnl=_dstr(realized) or "0",
        unrealized_pnl=_dstr(unrealized) or "0",
        drawdown=_dstr(drawdown) or "0",
        peak_equity=_dstr(peak) or "0",
        exposure_per_instrument={k: _dstr(v) or "0" for k, v in exposure.items()},
        exposure_per_asset_class={k: _dstr(v) or "0" for k, v in class_exposure.items()},
        orders_today=orders_today,
        starting_cash=_dstr(starting) or "0",
        incomplete=incomplete,
        as_of=last_bar_at,
    )


def _universe_rows(path: Path) -> list[dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    instruments = raw.get("instruments") if isinstance(raw, dict) else None
    if not isinstance(instruments, list):
        return []
    return [item for item in instruments if isinstance(item, dict)]


def _change_and_vol(bars: list[Bar]) -> tuple[Decimal | None, Decimal | None]:
    if len(bars) < 2:
        return None, None
    prev = bars[-2].close
    last = bars[-1].close
    change = None
    if prev != 0:
        change = (last - prev) / prev * Decimal("100")
    closes = [float(bar.close) for bar in bars[-20:]]
    vol = None
    if len(closes) >= 3 and all(x > 0 for x in closes):
        rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        vol = Decimal(str(statistics.pstdev(rets)))
    return change, vol


def build_market(
    settings: ControlSettings,
    *,
    symbols: list[str] | None,
    fetch_bars: FetchBarsFn,
    now: datetime | None = None,
) -> list[MarketInstrument]:
    moment = now if now is not None else _now()
    rows = []
    health = build_health(settings, now=moment, ping=lambda _url: True)
    stale = health.venue != "connected"
    wanted = set(symbols) if symbols else None
    for item in _universe_rows(settings.paths.universe):
        symbol = str(item.get("symbol") or "")
        if not symbol or (wanted is not None and symbol not in wanted):
            continue
        end = moment
        start = end - timedelta(days=40)
        bars: list[Bar] = []
        try:
            paper = load_paper_trading_config(settings.paths.paper_config)
            bars = fetch_bars(symbol, start, end, paper.timeframe)
        except Exception:
            bars = []
        change, vol = _change_and_vol(bars)
        last = bars[-1] if bars else None
        rows.append(
            MarketInstrument(
                symbol=symbol,
                venue=str(item.get("venue") or ""),
                asset_class=str(item.get("asset_class") or ""),
                price=_dstr(last.close) if last else None,
                change_pct=_dstr(change) if change is not None else None,
                volume=_dstr(last.volume) if last else None,
                volatility=_dstr(vol) if vol is not None else None,
                spread=None,
                as_of=last.timestamp if last else None,
                stale=stale or last is None,
            )
        )
    return rows


def build_bars(
    settings: ControlSettings,
    symbol: str,
    *,
    timeframe: str,
    start: datetime,
    end: datetime,
    fetch_bars: FetchBarsFn,
    now: datetime | None = None,
) -> BarsResponse:
    paper = load_paper_trading_config(settings.paths.paper_config)
    bars = fetch_bars(symbol, start, end, timeframe)
    closes = [bar.close for bar in bars]
    points: list[BarPoint] = []
    for index, bar in enumerate(bars):
        window = closes[: index + 1]
        fast = ema(window, paper.fast_ema_period)
        slow = ema(window, paper.slow_ema_period)
        points.append(
            BarPoint(
                timestamp=bar.timestamp,
                open=_dstr(bar.open) or "0",
                high=_dstr(bar.high) or "0",
                low=_dstr(bar.low) or "0",
                close=_dstr(bar.close) or "0",
                volume=_dstr(bar.volume) or "0",
                ema_fast=_dstr(fast),
                ema_slow=_dstr(slow),
            )
        )
    health = build_health(settings, now=now, ping=lambda _url: True)
    return BarsResponse(
        symbol=symbol,
        timeframe=timeframe,
        bars=points,
        stale=health.venue != "connected",
    )


def build_signal(
    settings: ControlSettings,
    symbol: str,
    *,
    fetch_bars: FetchBarsFn,
    now: datetime | None = None,
) -> SignalResponse:
    paper = load_paper_trading_config(settings.paths.paper_config)
    moment = now if now is not None else _now()
    bars = fetch_bars(symbol, moment - timedelta(days=80), moment, paper.timeframe)
    direction = None
    rationale = None
    as_of = bars[-1].timestamp if bars else None
    if bars:
        direction = ema_cross_direction(
            [bar.close for bar in bars],
            paper.fast_ema_period,
            paper.slow_ema_period,
        )
        rationale = (
            f"ema_cross fast={paper.fast_ema_period} slow={paper.slow_ema_period}"
            if direction
            else "indicators_not_ready"
        )
    latest_llm = None
    if settings.paths.audit_db.is_file():
        for event in reversed(_audit(settings.paths).list_events()):
            payload = event.payload
            if event.event_type == "proposal" and payload.get("instrument") == symbol:
                latest_llm = event
                break
    if latest_llm is not None:
        payload = latest_llm.payload
        return SignalResponse(
            symbol=symbol,
            source="llm",
            direction=str(payload.get("direction")) if payload.get("direction") else None,
            confidence=float(payload["confidence"]) if payload.get("confidence") is not None else None,
            rationale=str(payload.get("rationale") or "propunere, nu ordin"),
            as_of=latest_llm.timestamp,
            sources=["llm_proposal"],
            is_proposal=True,
        )
    return SignalResponse(
        symbol=symbol,
        source="ema_cross" if direction else "none",
        direction=direction,
        confidence=1.0 if direction else None,
        rationale=rationale,
        as_of=as_of,
        sources=["ema_cross"] if direction else [],
        is_proposal=True,
    )


def list_pending(settings: ControlSettings, *, now: datetime | None = None) -> list[PendingApproval]:
    moment = now if now is not None else _now()
    health = build_health(settings, now=moment, ping=lambda _url: True)
    directory = settings.paths.approvals_dir
    if not directory.is_dir():
        return []
    last_bar_at, _, last_close = _last_bar(settings.paths.last_bar)
    pending: list[PendingApproval] = []
    for request_path in sorted(directory.glob("*.request.json")):
        cid = request_path.name.replace(".request.json", "")
        decision_path = directory / f"{cid}.decision.json"
        if decision_path.is_file():
            continue
        raw = json.loads(request_path.read_text(encoding="utf-8"))
        decision = raw.get("risk_decision") if isinstance(raw, dict) else None
        if not isinstance(decision, dict):
            continue
        requested_at = _parse_dt(raw.get("requested_at")) or moment
        expires_at = requested_at + timedelta(seconds=settings.approval_timeout_s)
        remaining = (expires_at - moment).total_seconds()
        qty = _dec(decision.get("quantity"))
        price = last_close
        notional = qty * price if price is not None else None
        blocked = None
        if health.trading_mode == "live":
            blocked = "live_actions_blocked"
        elif health.agent == "halted":
            blocked = "agent_halted"
        elif health.venue != "connected":
            blocked = "stale_or_disconnected"
        elif remaining <= 0:
            blocked = "approval_timeout"
        rationale = None
        if settings.paths.audit_db.is_file():
            for event in reversed(_audit(settings.paths).list_events()):
                if str(event.correlation_id) == cid and event.event_type == "proposal":
                    rationale = str(event.payload.get("rationale") or "")
                    break
        pending.append(
            PendingApproval(
                correlation_id=UUID(str(raw.get("correlation_id") or cid)),
                requested_at=requested_at,
                expires_at=expires_at,
                remaining_s=max(remaining, 0.0),
                instrument=str(decision.get("instrument") or ""),
                side=str(decision.get("side") or ""),
                quantity=_dstr(qty) or "0",
                reject_reason=str(decision["reject_reason"])
                if decision.get("reject_reason") is not None
                else None,
                requires_human_approval=bool(decision.get("requires_human_approval", True)),
                estimated_notional=_dstr(notional),
                last_price=_dstr(price),
                rationale=rationale,
                stale=health.venue != "connected",
                trading_mode=health.trading_mode,
                approve_blocked_reason=blocked,
            )
        )
    return pending


def write_approval(
    settings: ControlSettings,
    correlation_id: UUID,
    *,
    approved: bool,
    reason: str,
    decided_by: str,
    now: datetime | None = None,
) -> None:
    moment = now if now is not None else _now()
    directory = settings.paths.approvals_dir
    directory.mkdir(parents=True, exist_ok=True)
    request_path = directory / f"{correlation_id}.request.json"
    if not request_path.is_file():
        raise FileNotFoundError(f"no pending approval {correlation_id}")
    decision_path = directory / f"{correlation_id}.decision.json"
    if decision_path.is_file():
        raise FileExistsError(f"approval already decided {correlation_id}")
    payload = {
        "approved": approved,
        "decided_by": decided_by,
        "reason": reason,
        "decided_at": moment.isoformat(),
    }
    decision_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _audit(settings.paths).record(
        AuditEvent.now(
            correlation_id=correlation_id,
            event_type="operator_action",
            payload={"action": "approval", **payload},
        )
    )


def list_orders(settings: ControlSettings) -> list[OrderRow]:
    if not settings.paths.audit_db.is_file():
        return []
    mode = trading_mode(settings)
    rows: list[OrderRow] = []
    for event in _audit(settings.paths).list_events():
        if event.event_type not in {"order_submitted", "fill", "risk_decision"}:
            continue
        payload = event.payload
        if event.event_type == "risk_decision" and payload.get("approved") is True:
            continue
        status = str(payload.get("status") or event.event_type)
        if event.event_type == "risk_decision" and payload.get("approved") is False:
            status = "rejected"
        rows.append(
            OrderRow(
                correlation_id=event.correlation_id,
                client_order_id=str(payload["client_order_id"])
                if payload.get("client_order_id")
                else None,
                instrument=str(payload.get("instrument") or ""),
                side=str(payload["side"]) if payload.get("side") else None,
                quantity=_dstr(_dec(payload.get("quantity") or payload.get("filled_quantity")))
                if payload.get("quantity") is not None or payload.get("filled_quantity") is not None
                else None,
                status=status,
                fill_price=_dstr(_dec(payload["fill_price"])) if payload.get("fill_price") else None,
                filled_quantity=_dstr(_dec(payload["filled_quantity"]))
                if payload.get("filled_quantity") is not None
                else None,
                fee=_dstr(_dec(payload["fee"])) if payload.get("fee") is not None else None,
                slippage=_dstr(_dec(payload["slippage"]))
                if payload.get("slippage") is not None
                else None,
                timestamp=event.timestamp,
                reason=str(payload["reason"] or payload.get("reject_reason") or "")
                if payload.get("reason") or payload.get("reject_reason")
                else None,
                trading_mode=mode,  # type: ignore[arg-type]
            )
        )
    return rows


def list_positions(settings: ControlSettings) -> list[PositionRow]:
    portfolio = build_portfolio(settings)
    last_bar_at, instrument, last_close = _last_bar(settings.paths.last_bar)
    paper = load_paper_trading_config(settings.paths.paper_config)
    symbol = instrument or paper.instrument
    qty = _dec(portfolio.exposure_per_instrument.get(symbol), Decimal("0"))
    local = _read_json(settings.paths.local_positions)
    open_qty = Decimal("0")
    if local:
        open_qty = LocalPortfolioSnapshot.model_validate(local).positions.get(symbol, Decimal("0"))
    stop = None
    if last_close is not None and last_close > 0:
        stop = last_close * (Decimal("1") - STOP_FRACTION)
    return [
        PositionRow(
            instrument=symbol,
            quantity=_dstr(open_qty) or "0",
            entry_price=None,
            last_price=_dstr(last_close),
            unrealized_pnl=portfolio.unrealized_pnl,
            stop_loss=_dstr(stop),
            take_profit=None,
            stop_source="engine_default_2pct",
        )
    ]


def build_risk(settings: ControlSettings) -> RiskLimitsView:
    limits = load_risk_limits(settings.paths.risk_limits)
    portfolio = build_portfolio(settings)
    consumed_loss = _dec(portfolio.realized_pnl)
    if consumed_loss > 0:
        consumed_loss = Decimal("0")
    else:
        consumed_loss = -consumed_loss
    drawdown = _dec(portfolio.drawdown)
    kill = KillSwitch(settings.paths.halt_flag)
    return RiskLimitsView(
        max_notional_per_order=_dstr(limits.max_notional_per_order) or "0",
        max_exposure_per_instrument=_dstr(limits.max_exposure_per_instrument) or "0",
        max_exposure_per_asset_class=_dstr(limits.max_exposure_per_asset_class) or "0",
        max_daily_loss=_dstr(limits.max_daily_loss) or "0",
        max_drawdown=_dstr(limits.max_drawdown) or "0",
        max_orders_per_day=limits.max_orders_per_day,
        circuit_breaker=CircuitBreakerView(
            max_consecutive_errors=limits.circuit_breaker.max_consecutive_errors,
            max_consecutive_losses=limits.circuit_breaker.max_consecutive_losses,
            halt_on_unknown_order_result=limits.circuit_breaker.halt_on_unknown_order_result,
            state="HALTED" if kill.is_active() else "RUNNING",
        ),
        consumed_daily_loss=_dstr(consumed_loss) or "0",
        remaining_daily_loss=_dstr(max(limits.max_daily_loss - consumed_loss, Decimal("0"))) or "0",
        consumed_drawdown=_dstr(drawdown) or "0",
        remaining_drawdown=_dstr(max(limits.max_drawdown - drawdown, Decimal("0"))) or "0",
        consumed_orders_today=portfolio.orders_today,
        remaining_orders_today=max(limits.max_orders_per_day - portfolio.orders_today, 0),
    )


def write_risk_limits(settings: ControlSettings, body, *, correlation_id: UUID) -> None:
    if body.confirmation_token != RISK_CONFIRMATION_TOKEN:
        raise ValueError("confirmation_token must be MAX_DAILY_LOSS")
    parsed = RiskLimits.model_validate(
        {
            "max_notional_per_order": body.max_notional_per_order,
            "max_exposure_per_instrument": body.max_exposure_per_instrument,
            "max_exposure_per_asset_class": body.max_exposure_per_asset_class,
            "max_daily_loss": body.max_daily_loss,
            "max_drawdown": body.max_drawdown,
            "max_orders_per_day": body.max_orders_per_day,
            "circuit_breaker": body.circuit_breaker.model_dump(),
        }
    )
    dumped = {
        "max_notional_per_order": int(parsed.max_notional_per_order)
        if parsed.max_notional_per_order == parsed.max_notional_per_order.to_integral_value()
        else float(parsed.max_notional_per_order),
        "max_exposure_per_instrument": int(parsed.max_exposure_per_instrument)
        if parsed.max_exposure_per_instrument == parsed.max_exposure_per_instrument.to_integral_value()
        else float(parsed.max_exposure_per_instrument),
        "max_exposure_per_asset_class": int(parsed.max_exposure_per_asset_class)
        if parsed.max_exposure_per_asset_class == parsed.max_exposure_per_asset_class.to_integral_value()
        else float(parsed.max_exposure_per_asset_class),
        "max_daily_loss": int(parsed.max_daily_loss)
        if parsed.max_daily_loss == parsed.max_daily_loss.to_integral_value()
        else float(parsed.max_daily_loss),
        "max_drawdown": int(parsed.max_drawdown)
        if parsed.max_drawdown == parsed.max_drawdown.to_integral_value()
        else float(parsed.max_drawdown),
        "max_orders_per_day": parsed.max_orders_per_day,
        "circuit_breaker": {
            "max_consecutive_errors": parsed.circuit_breaker.max_consecutive_errors,
            "max_consecutive_losses": parsed.circuit_breaker.max_consecutive_losses,
            "halt_on_unknown_order_result": parsed.circuit_breaker.halt_on_unknown_order_result,
        },
    }
    path = settings.paths.risk_limits
    path.write_text(yaml.safe_dump(dumped, sort_keys=False), encoding="utf-8")
    _audit(settings.paths).record(
        AuditEvent.now(
            correlation_id=correlation_id,
            event_type="operator_action",
            payload={"action": "risk_limits_updated", "limits": dumped},
        )
    )


def trigger_halt(settings: ControlSettings, reason: str) -> None:
    KillSwitch(settings.paths.halt_flag).trigger(reason)
    _audit(settings.paths).record(
        AuditEvent.now(
            correlation_id=uuid4(),
            event_type="operator_action",
            payload={"action": "halt", "reason": reason},
        )
    )


def reset_halt(settings: ControlSettings) -> None:
    KillSwitch(settings.paths.halt_flag).reset()
    _audit(settings.paths).record(
        AuditEvent.now(
            correlation_id=uuid4(),
            event_type="operator_action",
            payload={"action": "halt_reset"},
        )
    )


def list_agent_events(
    settings: ControlSettings, *, cursor: int = 0, limit: int = 200
) -> AgentEventsResponse:
    if not settings.paths.audit_db.is_file():
        return AgentEventsResponse(events=[], next_cursor=None)
    rows = _audit(settings.paths).list_event_rows(after_id=cursor, limit=limit)
    events = [
        AgentEventRow(
            id=row_id,
            timestamp=event.timestamp,
            correlation_id=event.correlation_id,
            event_type=event.event_type,
            payload=event.payload,
        )
        for row_id, event in rows
    ]
    next_cursor = events[-1].id if events and len(events) == limit else None
    return AgentEventsResponse(events=events, next_cursor=next_cursor)


def list_research(
    settings: ControlSettings, *, instrument: str | None, now: datetime | None = None
) -> list[ResearchDocumentView]:
    moment = now if now is not None else _now()
    if not settings.paths.research_db.is_file():
        return []
    store = MetadataStore(settings.paths.research_db)
    try:
        documents = store.list_documents(instrument=instrument, limit=50)
        views: list[ResearchDocumentView] = []
        for doc in documents:
            contradicts = [
                related_id
                for related_id, relation in store.related_documents(doc.doc_id)
                if relation == "contradicts"
            ]
            views.append(_research_view(doc, contradicts, moment))
        return views
    finally:
        store.close()


def _research_view(
    doc: ResearchDocument, contradicts: list[str], now: datetime
) -> ResearchDocumentView:
    age = now - doc.fetched_at.astimezone(timezone.utc)
    return ResearchDocumentView(
        doc_id=doc.doc_id,
        url=doc.url,
        title=doc.title,
        source_id=doc.source_id,
        published_at=doc.published_at,
        fetched_at=doc.fetched_at,
        event_date=doc.event_date,
        assets_mentioned=doc.assets_mentioned,
        category=doc.category,
        summary=doc.summary,
        sentiment_score=doc.sentiment_score,
        impact_magnitude=doc.impact_magnitude,
        impact_direction=doc.impact_direction,
        confidence_score=doc.confidence_score,
        stale=age > timedelta(hours=24),
        contradicts=contradicts,
        extracted_text=doc.extracted_text,
    )


def build_security(settings: ControlSettings, environ: dict[str, str]) -> SecuritySettings:
    try:
        policy = load_live_key_policy(environ)
        spot_key = policy.has_spot_key
        spot_secret = policy.has_spot_secret
        withdraw = policy.withdraw_enabled
        whitelist = policy.ip_whitelist_configured
        subaccount = policy.subaccount
    except ValueError:
        spot_key = bool(environ.get("KRAKEN_SPOT_API_KEY"))
        spot_secret = bool(environ.get("KRAKEN_SPOT_API_SECRET"))
        withdraw = False
        whitelist = False
        subaccount = False
    role = settings.operator_role if settings.operator_role in {"operator", "observer"} else "observer"
    return SecuritySettings(
        environment=settings.environment,
        trading_mode=trading_mode(settings),  # type: ignore[arg-type]
        live_trading_enabled=settings.live_trading_enabled,
        broker_paper_mode=settings.broker_paper_mode,
        kraken_spot_key_present=spot_key,
        kraken_spot_secret_present=spot_secret,
        withdraw_enabled=withdraw,
        ip_whitelist_configured=whitelist,
        subaccount=subaccount,
        operator_role=role,  # type: ignore[arg-type]
        data_retention="audit_append_only",
    )


def default_strategies(settings: ControlSettings) -> list[dict]:
    paper = load_paper_trading_config(settings.paths.paper_config)
    return [
        {
            "id": "baseline_ema_cross",
            "name": "Baseline EMA cross",
            "kind": "ema_cross",
            "enabled": True,
            "params": {
                "fast_ema_period": paper.fast_ema_period,
                "slow_ema_period": paper.slow_ema_period,
            },
        },
        {
            "id": "llm_assisted",
            "name": "LLM-assisted (proposal only)",
            "kind": "llm",
            "enabled": False,
            "params": {},
        },
    ]


def load_strategy_docs(settings: ControlSettings) -> list[dict]:
    path = settings.paths.strategies
    if not path.is_file():
        return default_strategies(settings)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = raw.get("strategies") if isinstance(raw, dict) else None
    if not isinstance(items, list) or not items:
        return default_strategies(settings)
    return [item for item in items if isinstance(item, dict)]


def list_strategies(settings: ControlSettings) -> list[StrategyRow]:
    summary = _read_json(settings.paths.runtime_dir / "paper_run_summary.json")
    sessions = summary.get("n_sessions") if summary else None
    halted = summary.get("halted") if summary else None
    backtest_ref = None
    reports = settings.paths.backtest_reports
    if reports.is_dir():
        files = sorted(reports.glob("*.md")) + sorted(reports.glob("*.json"))
        if files:
            backtest_ref = files[-1].name
    rows = []
    for item in load_strategy_docs(settings):
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        rows.append(
            StrategyRow(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or item.get("id") or ""),
                kind=str(item.get("kind") or "ema_cross"),  # type: ignore[arg-type]
                enabled=bool(item.get("enabled", False)),
                params={str(k): str(v) for k, v in params.items()},
                last_paper_sessions=int(sessions) if isinstance(sessions, int) else None,
                last_paper_halted=bool(halted) if halted is not None else None,
                last_backtest_ref=backtest_ref,
            )
        )
    return rows


def set_strategy_enabled(
    settings: ControlSettings, strategy_id: str, *, enabled: bool, confirmation_token: str
) -> None:
    expected = STRATEGY_ENABLE_TOKEN if enabled else STRATEGY_DISABLE_TOKEN
    if confirmation_token != expected:
        raise ValueError(f"confirmation_token must be {expected}")
    items = load_strategy_docs(settings)
    found = False
    for item in items:
        if item.get("id") == strategy_id:
            item["enabled"] = enabled
            found = True
    if not found:
        raise FileNotFoundError(strategy_id)
    settings.paths.strategies.parent.mkdir(parents=True, exist_ok=True)
    settings.paths.strategies.write_text(
        yaml.safe_dump({"strategies": items}, sort_keys=False),
        encoding="utf-8",
    )
    _audit(settings.paths).record(
        AuditEvent.now(
            correlation_id=uuid4(),
            event_type="operator_action",
            payload={"action": "strategy_toggle", "id": strategy_id, "enabled": enabled},
        )
    )


def llm_strategy_enabled(settings: ControlSettings) -> bool:
    for item in load_strategy_docs(settings):
        if item.get("id") == "llm_assisted":
            return bool(item.get("enabled"))
    return False


def build_alerts(settings: ControlSettings, *, now: datetime | None = None) -> list[AlertRow]:
    health = build_health(settings, now=now, ping=lambda _url: True)
    risk = build_risk(settings)
    alerts: list[AlertRow] = []
    if health.agent == "halted":
        alerts.append(
            AlertRow(
                id="halt",
                severity="error",
                title="Agent HALTED",
                detail=health.halt_reason or "Kill switch is active. Resume is manual.",
            )
        )
    if health.venue != "connected":
        alerts.append(
            AlertRow(
                id="venue",
                severity="error" if health.venue == "down" else "warning",
                title="Venue connection",
                detail=f"Exchange data is {health.venue}. Orders are blocked.",
            )
        )
    if health.reconciliation == "mismatch":
        alerts.append(
            AlertRow(
                id="recon",
                severity="error",
                title="Reconciliation mismatch",
                detail="Local state does not match broker snapshot. Reset halt only after review.",
            )
        )
    if _dec(risk.remaining_daily_loss) <= 0:
        alerts.append(
            AlertRow(
                id="daily_loss",
                severity="error",
                title="Maximum daily loss reached",
                detail="RiskEngine will reject new entries. This is not a suggestion to increase limits.",
            )
        )
    if health.llm == "down":
        alerts.append(
            AlertRow(
                id="llm",
                severity="warning",
                title="LLM service unreachable",
                detail="Proposal layer is down. Baseline may still run if enabled.",
            )
        )
    return alerts


LEVEL1_ANALYSIS_TYPES = frozenset({"priced_in", "technical", "news_impact", "daily_plan"})
AnalyzeFn = Callable[[AnalysisContext], ParsedAnalysis | RejectedAnalysis]


def _universe_symbols(path: Path) -> set[str]:
    return {
        str(item["symbol"]).strip()
        for item in _universe_rows(path)
        if isinstance(item.get("symbol"), str) and item["symbol"].strip()
    }


def _fetch_window(
    fetch_bars: FetchBarsFn,
    instrument: str,
    timeframe: str,
    now: datetime,
) -> list[Bar]:
    start = now - timedelta(days=90)
    return fetch_bars(instrument, start, now, timeframe)


def _research_external(settings: ControlSettings, instrument: str, as_of: datetime) -> str | None:
    if not settings.paths.research_db.is_file():
        return None
    store = MetadataStore(settings.paths.research_db)
    try:
        documents = store.query_for_context(instrument, as_of, limit=5)
        if not documents:
            return None
        pairs: list[tuple[str, str]] = []
        for doc in documents:
            for related_id, relation in store.related_documents(doc.doc_id):
                if relation == "contradicts":
                    pairs.append((doc.doc_id, related_id))
        return build_external_context(
            instrument, as_of, documents, contradicting_pairs=pairs
        )
    finally:
        store.close()


def _document_titles(settings: ControlSettings, instrument: str, as_of: datetime) -> list[str]:
    if not settings.paths.research_db.is_file():
        return []
    store = MetadataStore(settings.paths.research_db)
    try:
        return [doc.title for doc in store.query_for_context(instrument, as_of, limit=5)]
    finally:
        store.close()


def build_indicator_snapshot(
    settings: ControlSettings,
    symbol: str,
    *,
    timeframe: str,
    fetch_bars: FetchBarsFn,
    now: datetime | None = None,
) -> dict:
    moment = now if now is not None else _now()
    if symbol not in _universe_symbols(settings.paths.universe):
        raise ValueError("instrument_not_in_universe")
    bars = bars_upto(_fetch_window(fetch_bars, symbol, timeframe, moment), moment)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "snapshot": indicator_snapshot(bars, timeframe=timeframe),
        "is_order": False,
    }


def build_stress_view(settings: ControlSettings, *, now: datetime | None = None) -> dict:
    portfolio = build_portfolio(settings, now=now)
    exposure = {
        symbol: _dec(notional)
        for symbol, notional in portfolio.exposure_per_instrument.items()
    }
    report = stress_portfolio(exposure)
    report["as_of"] = portfolio.as_of.isoformat() if portfolio.as_of else None
    report["incomplete"] = portfolio.incomplete
    report["is_order"] = False
    return report


def build_daily_plan_view(
    settings: ControlSettings,
    *,
    instrument: str,
    fetch_bars: FetchBarsFn,
    now: datetime | None = None,
) -> dict:
    moment = now if now is not None else _now()
    if instrument not in _universe_symbols(settings.paths.universe):
        raise ValueError("instrument_not_in_universe")
    health = build_health(settings, now=moment, ping=lambda _url: True)
    risk = build_risk(settings)
    bars = bars_upto(_fetch_window(fetch_bars, instrument, "1d", moment), moment)
    snapshot = indicator_snapshot(bars, timeframe="1d")
    plan = build_daily_plan(
        instrument=instrument,
        as_of=moment,
        indicators=snapshot,
        remaining_daily_loss=risk.remaining_daily_loss,
        remaining_drawdown=risk.remaining_drawdown,
        remaining_orders_today=risk.remaining_orders_today,
        calendar_events=[],
        document_titles=_document_titles(settings, instrument, moment),
        venue_stale=health.venue != "connected",
    )
    plan["is_order"] = False
    return plan


def run_operator_analysis(
    settings: ControlSettings,
    *,
    instrument: str,
    analysis_type: str,
    timeframe: str,
    fetch_bars: FetchBarsFn,
    request_analysis: AnalyzeFn,
    now: datetime | None = None,
) -> AnalysisRunResponse:
    """Nivel 1: apelează /analyze. Nu trece prin RiskEngine sau OrderGateway."""
    moment = now if now is not None else _now()
    if analysis_type not in LEVEL1_ANALYSIS_TYPES:
        raise ValueError("analysis_type_not_in_level1")
    if instrument not in _universe_symbols(settings.paths.universe):
        raise ValueError("instrument_not_in_universe")
    daily = _fetch_window(fetch_bars, instrument, "1d", moment)
    selected = daily if timeframe == "1d" else _fetch_window(fetch_bars, instrument, timeframe, moment)
    facts = technical_facts_bundle(
        {"1d": daily, timeframe: selected},
        instrument=instrument,
        as_of=moment,
    )
    if analysis_type == "daily_plan":
        facts["daily_plan"] = build_daily_plan_view(
            settings, instrument=instrument, fetch_bars=fetch_bars, now=moment
        )
    external = _research_external(settings, instrument, moment)
    context = AnalysisContext(
        instrument=instrument,
        as_of=moment,
        analysis_type=analysis_type,  # type: ignore[arg-type]
        timeframe=timeframe,
        facts_bundle=facts,
        external_context=external,
    )
    result = request_analysis(context)
    analysis: ParsedAnalysis | None = result if isinstance(result, ParsedAnalysis) else None
    rejected: RejectedAnalysis | None = result if isinstance(result, RejectedAnalysis) else None
    payload = analysis.model_dump(mode="json") if analysis is not None else (
        rejected.model_dump(mode="json") if rejected is not None else {}
    )
    _audit(settings.paths).record(
        AuditEvent.now(
            correlation_id=uuid4(),
            event_type="analysis",
            payload={
                "instrument": instrument,
                "analysis_type": analysis_type,
                "is_order": False,
                "result": payload,
            },
        )
    )
    return AnalysisRunResponse(
        is_order=False,
        facts_bundle=facts,
        analysis=analysis,
        rejected=rejected,
    )


def list_analyses(
    settings: ControlSettings, *, instrument: str | None = None
) -> list[dict]:
    if not settings.paths.audit_db.is_file():
        return []
    rows = []
    for event in _audit(settings.paths).list_events():
        if event.event_type != "analysis":
            continue
        payload = event.payload
        if instrument and payload.get("instrument") != instrument:
            continue
        rows.append(
            {
                "timestamp": event.timestamp.isoformat(),
                "correlation_id": str(event.correlation_id),
                **payload,
            }
        )
    return rows[-50:]
