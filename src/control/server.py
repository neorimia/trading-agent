"""HTTP loopback — singurul punct de intrare al consolei de operator.

Nu importă src.llm. Nu apelează /propose. POST /analyze e research-only (Nivel 1).
Host-ul e forțat pe loopback (127.0.0.1 / localhost / ::1).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4

import uvicorn
from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware

from src.control.agent_process import AgentProcessController, SubprocessAgentProcess
from src.control.models import (
    AckResponse,
    ApprovalDecisionRequest,
    HaltRequest,
    HealthResponse,
    OperatorAnalyzeRequest,
    RiskLimitsWrite,
    StrategyToggleRequest,
    WsEnvelope,
)
from src.control.runtime_state import (
    AnalyzeFn,
    FetchBarsFn,
    PidAliveFn,
    PingFn,
    build_alerts,
    build_bars,
    build_daily_plan_view,
    build_health,
    build_indicator_snapshot,
    build_market,
    build_portfolio,
    build_risk,
    build_security,
    build_signal,
    build_stress_view,
    list_agent_events,
    list_analyses,
    list_orders,
    list_pending,
    list_positions,
    list_research,
    list_strategies,
    pid_is_alive,
    ping_http,
    reset_halt,
    run_operator_analysis,
    set_strategy_enabled,
    trigger_halt,
    write_approval,
    write_risk_limits,
)
from src.control.settings import (
    DEFAULT_CORS,
    ControlSettings,
    load_control_settings,
    validate_bind_host,
)
from src.data.kraken import KrakenPublicOHLCSource
from src.data.sources import Bar
from src.engine.analysis_client import LLMAnalysisClient
from src.engine.analysis_types import AnalysisContext
from src.engine.paper_config import load_paper_trading_config
from src.execution.key_policy import redact_secrets

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _fetch_kraken_bars(
    instrument: str, start: datetime, end: datetime, timeframe: str
) -> list[Bar]:
    source = KrakenPublicOHLCSource()
    try:
        return source.fetch_bars(instrument, start, end, timeframe)
    finally:
        source.close()


@dataclass
class ControlContext:
    settings: ControlSettings
    environ: dict[str, str]
    fetch_bars: FetchBarsFn = _fetch_kraken_bars
    ping: PingFn = ping_http
    alive: PidAliveFn = pid_is_alive
    process: AgentProcessController = field(default_factory=SubprocessAgentProcess)
    idempotency: dict[str, tuple[int, dict]] = field(default_factory=dict)
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    request_analysis: AnalyzeFn | None = None


def _ws_snapshot(ctx: ControlContext, sent_at: datetime) -> tuple:
    health = build_health(ctx.settings, now=sent_at, ping=ctx.ping, alive=ctx.alive)
    pending = list_pending(ctx.settings, now=sent_at)
    alerts = build_alerts(ctx.settings, now=sent_at)
    return health, pending, alerts


def _load_dotenv_control() -> None:
    env_path = Path(".env.control")
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    engine_path = Path(".env.engine")
    if engine_path.is_file():
        load_dotenv(engine_path, override=False)


def create_app(ctx: ControlContext | None = None) -> FastAPI:
    context = ctx
    app = FastAPI(title="trading-agent-control", docs_url=None, redoc_url=None)

    def get_ctx() -> ControlContext:
        if context is not None:
            return context
        stored = getattr(app.state, "ctx", None)
        if stored is None:
            settings = load_control_settings()
            stored = ControlContext(settings=settings, environ=dict(os.environ))
            app.state.ctx = stored
        return stored

    origins = list(context.settings.cors_origins if context is not None else DEFAULT_CORS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Idempotency-Key", "Content-Type"],
    )

    def require_auth(
        request: Request,
        authorization: str | None = Header(default=None),
        ctx: ControlContext = Depends(get_ctx),
    ) -> ControlContext:
        token = ctx.settings.operator_token
        if token:
            expected = f"Bearer {token}"
            if authorization != expected:
                raise HTTPException(status_code=401, detail="invalid operator token")
        return ctx

    def require_operator(ctx: ControlContext = Depends(require_auth)) -> ControlContext:
        if ctx.settings.operator_role != "operator":
            raise HTTPException(status_code=403, detail="observer cannot mutate")
        return ctx

    def require_idempotency(
        ctx: ControlContext,
        idempotency_key: str | None,
    ) -> dict | None:
        if not idempotency_key or not idempotency_key.strip():
            raise HTTPException(status_code=400, detail="Idempotency-Key required")
        cached = ctx.idempotency.get(idempotency_key)
        if cached is not None:
            return {"status": cached[0], "body": cached[1], "replay": True}
        return None

    def store_idempotency(ctx: ControlContext, key: str, status: int, body: dict) -> None:
        ctx.idempotency[key] = (status, body)

    @app.get("/v1/health", response_model=HealthResponse)
    def health(ctx: ControlContext = Depends(require_auth)) -> HealthResponse:
        return build_health(ctx.settings, now=ctx.now(), ping=ctx.ping, alive=ctx.alive)

    @app.get("/v1/portfolio")
    def portfolio(ctx: ControlContext = Depends(require_auth)):
        return build_portfolio(ctx.settings, now=ctx.now())

    @app.get("/v1/alerts")
    def alerts(ctx: ControlContext = Depends(require_auth)):
        return build_alerts(ctx.settings, now=ctx.now())

    @app.get("/v1/market")
    def market(
        symbols: str | None = Query(default=None),
        ctx: ControlContext = Depends(require_auth),
    ):
        wanted = [item.strip() for item in symbols.split(",") if item.strip()] if symbols else None
        return build_market(
            ctx.settings, symbols=wanted, fetch_bars=ctx.fetch_bars, now=ctx.now()
        )

    @app.get("/v1/market/{symbol}/bars")
    def market_bars(
        symbol: str,
        timeframe: str = Query(default="1d"),
        from_ts: datetime | None = Query(default=None, alias="from"),
        to_ts: datetime | None = Query(default=None, alias="to"),
        ctx: ControlContext = Depends(require_auth),
    ):
        end = to_ts if to_ts is not None else ctx.now()
        start = from_ts if from_ts is not None else end - timedelta(days=90)
        try:
            return build_bars(
                ctx.settings,
                symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                fetch_bars=ctx.fetch_bars,
                now=ctx.now(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/market/{symbol}/indicators")
    def market_indicators(
        symbol: str,
        timeframe: str = Query(default="1d"),
        ctx: ControlContext = Depends(require_auth),
    ):
        try:
            return build_indicator_snapshot(
                ctx.settings,
                symbol,
                timeframe=timeframe,
                fetch_bars=ctx.fetch_bars,
                now=ctx.now(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/signals")
    def signals(
        symbol: str = Query(min_length=1),
        ctx: ControlContext = Depends(require_auth),
    ):
        return build_signal(ctx.settings, symbol, fetch_bars=ctx.fetch_bars, now=ctx.now())

    @app.get("/v1/positions")
    def positions(ctx: ControlContext = Depends(require_auth)):
        return list_positions(ctx.settings)

    @app.get("/v1/orders")
    def orders(
        status: str | None = Query(default=None),
        ctx: ControlContext = Depends(require_auth),
    ):
        rows = list_orders(ctx.settings)
        if status:
            rows = [row for row in rows if row.status == status]
        return rows

    @app.get("/v1/approvals/pending")
    def pending(ctx: ControlContext = Depends(require_auth)):
        return list_pending(ctx.settings, now=ctx.now())

    @app.post("/v1/approvals/{correlation_id}")
    def decide_approval(
        correlation_id: UUID,
        body: ApprovalDecisionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        ctx: ControlContext = Depends(require_operator),
    ):
        replay = require_idempotency(ctx, idempotency_key)
        if replay is not None:
            return replay["body"]
        health = build_health(ctx.settings, now=ctx.now(), ping=ctx.ping, alive=ctx.alive)
        if body.approved:
            if health.trading_mode == "live":
                raise HTTPException(status_code=403, detail="live approvals are blocked")
            if health.agent == "halted":
                raise HTTPException(status_code=409, detail="agent_halted")
            if health.venue != "connected":
                raise HTTPException(status_code=409, detail="stale_or_disconnected")
        try:
            write_approval(
                ctx.settings,
                correlation_id,
                approved=body.approved,
                reason=body.reason,
                decided_by=body.decided_by,
                now=ctx.now(),
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        payload = AckResponse(ok=True, detail="decision recorded").model_dump()
        store_idempotency(ctx, idempotency_key or "", 200, payload)
        return payload

    @app.get("/v1/risk/limits")
    def risk_get(ctx: ControlContext = Depends(require_auth)):
        return build_risk(ctx.settings)

    @app.put("/v1/risk/limits")
    def risk_put(
        body: RiskLimitsWrite,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        ctx: ControlContext = Depends(require_operator),
    ):
        replay = require_idempotency(ctx, idempotency_key)
        if replay is not None:
            return replay["body"]
        try:
            write_risk_limits(ctx.settings, body, correlation_id=uuid4())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = AckResponse(
            ok=True,
            detail="limits written; restart required before they apply",
            restart_required=True,
        ).model_dump()
        store_idempotency(ctx, idempotency_key or "", 200, payload)
        return payload

    @app.post("/v1/risk/halt")
    def halt(
        body: HaltRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        ctx: ControlContext = Depends(require_operator),
    ):
        replay = require_idempotency(ctx, idempotency_key)
        if replay is not None:
            return replay["body"]
        trigger_halt(ctx.settings, body.reason)
        payload = AckResponse(ok=True, detail="halt flag written").model_dump()
        store_idempotency(ctx, idempotency_key or "", 200, payload)
        return payload

    @app.post("/v1/risk/halt/reset")
    def halt_reset(
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        ctx: ControlContext = Depends(require_operator),
    ):
        replay = require_idempotency(ctx, idempotency_key)
        if replay is not None:
            return replay["body"]
        reset_halt(ctx.settings)
        payload = AckResponse(ok=True, detail="halt flag cleared; resume is manual").model_dump()
        store_idempotency(ctx, idempotency_key or "", 200, payload)
        return payload

    @app.get("/v1/agent/events")
    def agent_events(
        cursor: int = Query(default=0, ge=0),
        limit: int = Query(default=200, ge=1, le=500),
        ctx: ControlContext = Depends(require_auth),
    ):
        return list_agent_events(ctx.settings, cursor=cursor, limit=limit)

    @app.post("/v1/agent/start")
    def agent_start(
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        ctx: ControlContext = Depends(require_operator),
    ):
        replay = require_idempotency(ctx, idempotency_key)
        if replay is not None:
            return replay["body"]
        if ctx.settings.live_trading_enabled:
            raise HTTPException(status_code=403, detail="live start is blocked")
        pid = ctx.process.start(ctx.settings)
        payload = AckResponse(ok=True, detail=f"agent pid {pid}").model_dump()
        store_idempotency(ctx, idempotency_key or "", 200, payload)
        return payload

    @app.post("/v1/agent/stop")
    def agent_stop(
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        ctx: ControlContext = Depends(require_operator),
    ):
        replay = require_idempotency(ctx, idempotency_key)
        if replay is not None:
            return replay["body"]
        ctx.process.stop(ctx.settings)
        payload = AckResponse(ok=True, detail="agent stop requested").model_dump()
        store_idempotency(ctx, idempotency_key or "", 200, payload)
        return payload

    @app.get("/v1/research/documents")
    def research_docs(
        instrument: str | None = Query(default=None),
        ctx: ControlContext = Depends(require_auth),
    ):
        return list_research(ctx.settings, instrument=instrument, now=ctx.now())

    @app.get("/v1/portfolio/stress")
    def portfolio_stress(ctx: ControlContext = Depends(require_auth)):
        return build_stress_view(ctx.settings, now=ctx.now())

    @app.get("/v1/research/daily-plan")
    def daily_plan(
        instrument: str | None = Query(default=None),
        ctx: ControlContext = Depends(require_auth),
    ):
        paper = load_paper_trading_config(ctx.settings.paths.paper_config)
        symbol = instrument or paper.instrument
        try:
            return build_daily_plan_view(
                ctx.settings,
                instrument=symbol,
                fetch_bars=ctx.fetch_bars,
                now=ctx.now(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/research/analyses")
    def research_analyses(
        instrument: str | None = Query(default=None),
        ctx: ControlContext = Depends(require_auth),
    ):
        return list_analyses(ctx.settings, instrument=instrument)

    @app.post("/v1/research/analyze")
    def research_analyze(
        body: OperatorAnalyzeRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        ctx: ControlContext = Depends(require_operator),
    ):
        replay = require_idempotency(ctx, idempotency_key)
        if replay is not None:
            return replay["body"]

        def _call(context: AnalysisContext):
            if ctx.request_analysis is not None:
                return ctx.request_analysis(context)
            client = LLMAnalysisClient(ctx.settings.llm_health_url)
            try:
                return client.request_analysis(context)
            finally:
                client.close()

        try:
            result = run_operator_analysis(
                ctx.settings,
                instrument=body.instrument,
                analysis_type=body.analysis_type,
                timeframe=body.timeframe,
                fetch_bars=ctx.fetch_bars,
                request_analysis=_call,
                now=ctx.now(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = result.model_dump(mode="json")
        store_idempotency(ctx, idempotency_key or "", 200, payload)
        return payload

    @app.get("/v1/settings/security")
    def security(ctx: ControlContext = Depends(require_auth)):
        payload = build_security(ctx.settings, ctx.environ).model_dump()
        text = redact_secrets(str(payload), ctx.environ)
        if any(
            ctx.environ.get(key) and ctx.environ.get(key) in text
            for key in (
                "KRAKEN_SPOT_API_KEY",
                "KRAKEN_SPOT_API_SECRET",
                "BROKER_API_KEY",
                "BROKER_API_SECRET",
            )
            if ctx.environ.get(key)
        ):
            raise HTTPException(status_code=500, detail="refusing to serialize secrets")
        return payload

    @app.get("/v1/strategies")
    def strategies(ctx: ControlContext = Depends(require_auth)):
        return list_strategies(ctx.settings)

    @app.post("/v1/strategies/{strategy_id}")
    def strategy_toggle(
        strategy_id: str,
        body: StrategyToggleRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        ctx: ControlContext = Depends(require_operator),
    ):
        replay = require_idempotency(ctx, idempotency_key)
        if replay is not None:
            return replay["body"]
        try:
            set_strategy_enabled(
                ctx.settings,
                strategy_id,
                enabled=body.enabled,
                confirmation_token=body.confirmation_token,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        payload = AckResponse(
            ok=True,
            detail="strategy file written; restart required",
            restart_required=True,
        ).model_dump()
        store_idempotency(ctx, idempotency_key or "", 200, payload)
        return payload

    @app.websocket("/v1/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        ctx = get_ctx()
        await websocket.accept()
        origin = websocket.headers.get("origin")
        if origin is not None and origin not in ctx.settings.cors_origins:
            await websocket.close(code=1008)
            return
        token = ctx.settings.operator_token
        if token:
            offered = websocket.query_params.get("token")
            header = websocket.headers.get("authorization")
            if offered != token and header != f"Bearer {token}":
                await websocket.close(code=1008)
                return
        try:
            while True:
                sent_at = ctx.now()
                health, pending, alerts = await asyncio.to_thread(
                    _ws_snapshot, ctx, sent_at
                )
                await websocket.send_json(
                    WsEnvelope(
                        channel="health",
                        payload=health.model_dump(mode="json"),
                        sent_at=sent_at,
                    ).model_dump(mode="json")
                )
                await websocket.send_json(
                    WsEnvelope(
                        channel="approvals",
                        payload={
                            "items": [item.model_dump(mode="json") for item in pending]
                        },
                        sent_at=sent_at,
                    ).model_dump(mode="json")
                )
                await websocket.send_json(
                    WsEnvelope(
                        channel="alerts",
                        payload={
                            "items": [item.model_dump(mode="json") for item in alerts]
                        },
                        sent_at=sent_at,
                    ).model_dump(mode="json")
                )
                await asyncio.sleep(2)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    app.dependency_overrides = {}
    app.state.get_ctx = get_ctx
    return app


app = create_app()


def main() -> None:
    _load_dotenv_control()
    settings = load_control_settings()
    host = validate_bind_host(settings.host)
    application = create_app(
        ControlContext(settings=settings, environ=dict(os.environ))
    )
    uvicorn.run(application, host=host, port=settings.port)


if __name__ == "__main__":
    main()
