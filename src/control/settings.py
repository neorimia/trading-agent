"""Căi și mediu pentru control plane. Nu încarcă .env.llm."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.execution.key_policy import LIVE_TRADING_FLAG, _FALSY, _TRUTHY

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_CORS = ("http://127.0.0.1:4200", "http://localhost:4200")
RISK_CONFIRMATION_TOKEN = "MAX_DAILY_LOSS"
STRATEGY_ENABLE_TOKEN = "ENABLE_STRATEGY"
STRATEGY_DISABLE_TOKEN = "DISABLE_STRATEGY"


def validate_bind_host(host: str) -> str:
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f"control server must bind to loopback, not {host!r}")
    return host


def _flag(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    return default


@dataclass(frozen=True)
class RuntimePaths:
    repo_root: Path
    runtime_dir: Path
    halt_flag: Path
    heartbeat: Path
    last_bar: Path
    reconciliation: Path
    local_positions: Path
    approvals_dir: Path
    audit_db: Path
    agent_pid: Path
    broker_monitor: Path
    broker_monitor_pid: Path
    strategies: Path
    risk_limits: Path
    universe: Path
    paper_config: Path
    research_db: Path
    backtest_reports: Path
    discovery_store: Path


@dataclass(frozen=True)
class ControlSettings:
    paths: RuntimePaths
    host: str
    port: int
    cors_origins: tuple[str, ...]
    operator_token: str
    operator_role: str
    environment: str
    llm_health_url: str
    research_health_url: str
    research_store_backend: str
    control_database_url: str | None
    ollama_url: str
    live_trading_enabled: bool
    broker_paper_mode: bool
    heartbeat_threshold_s: float
    stale_data_threshold_s: float
    approval_timeout_s: float


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_paths(
    *,
    root: Path | None = None,
    runtime_dir: Path | None = None,
    environ: dict[str, str] | None = None,
) -> RuntimePaths:
    env = environ if environ is not None else os.environ
    base = root if root is not None else repo_root()
    runtime = runtime_dir if runtime_dir is not None else Path(
        env.get("RUNTIME_DIR", str(base / "runtime" / "paper"))
    )
    return RuntimePaths(
        repo_root=base,
        runtime_dir=runtime,
        halt_flag=Path(env.get("HALT_FLAG_PATH", str(runtime / "control" / "halt.flag"))),
        heartbeat=runtime / "heartbeat" / "paper-engine.json",
        last_bar=runtime / "control" / "last_bar.json",
        reconciliation=runtime / "control" / "reconciliation.json",
        local_positions=runtime / "control" / "local_positions.json",
        approvals_dir=runtime / "control" / "approvals",
        audit_db=runtime / "audit" / "audit.sqlite",
        agent_pid=runtime / "control" / "agent.pid",
        broker_monitor=runtime / "control" / "broker_monitor.json",
        broker_monitor_pid=runtime / "control" / "broker_monitor.pid",
        strategies=Path(env.get("STRATEGIES_PATH", str(base / "config" / "strategies.yaml"))),
        risk_limits=Path(env.get("RISK_LIMITS_PATH", str(base / "config" / "risk_limits.yaml"))),
        universe=Path(env.get("UNIVERSE_PATH", str(base / "config" / "universe.yaml"))),
        paper_config=Path(
            env.get("PAPER_CONFIG_PATH", str(base / "config" / "paper_trading.yaml"))
        ),
        research_db=Path(
            env.get("RESEARCH_METADATA_DB_PATH", str(base / "data" / "research" / "metadata.db"))
        ),
        backtest_reports=base / "backtests" / "reports",
        discovery_store=Path(env.get("DISCOVERY_STORE_PATH", str(base / "data" / "discovery"))),
    )


def load_control_settings(
    *,
    root: Path | None = None,
    environ: dict[str, str] | None = None,
) -> ControlSettings:
    env = environ if environ is not None else dict(os.environ)
    paths = build_paths(root=root, environ=env)
    cors_raw = env.get("CONTROL_CORS_ORIGINS", ",".join(DEFAULT_CORS))
    origins = tuple(item.strip() for item in cors_raw.split(",") if item.strip())
    port_raw = env.get("CONTROL_SERVER_PORT", "8767")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"invalid CONTROL_SERVER_PORT: {port_raw!r}") from exc
    host = validate_bind_host(env.get("CONTROL_SERVER_HOST", "127.0.0.1"))
    research_backend = env.get("RESEARCH_STORE_BACKEND", "sqlite").strip().lower()
    if research_backend not in {"sqlite", "postgres"}:
        raise ValueError("RESEARCH_STORE_BACKEND must be 'sqlite' or 'postgres'")
    control_database_url = env.get("CONTROL_DATABASE_URL", "").strip() or None
    if research_backend == "postgres" and control_database_url is None:
        raise ValueError(
            "CONTROL_DATABASE_URL is required when RESEARCH_STORE_BACKEND=postgres"
        )
    timeout_s = 3600.0
    stale_s = 172800.0
    heartbeat_s = 30.0
    paper_path = paths.paper_config
    if paper_path.is_file():
        from src.engine.paper_config import load_paper_trading_config

        paper = load_paper_trading_config(paper_path)
        timeout_s = paper.approval_timeout_s
        stale_s = paper.stale_data_threshold_s
        heartbeat_s = paper.heartbeat_threshold_s
    return ControlSettings(
        paths=paths,
        host=host,
        port=port,
        cors_origins=origins or DEFAULT_CORS,
        operator_token=env.get("CONTROL_OPERATOR_TOKEN", "").strip(),
        operator_role=env.get("CONTROL_OPERATOR_ROLE", "operator").strip() or "operator",
        environment=env.get("ENVIRONMENT", "development"),
        llm_health_url=env.get("LLM_SERVICE_URL", "http://127.0.0.1:8765").rstrip("/"),
        research_health_url=env.get(
            "RESEARCH_SERVICE_URL", "http://127.0.0.1:8766"
        ).rstrip("/"),
        research_store_backend=research_backend,
        control_database_url=control_database_url,
        ollama_url=env.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
        live_trading_enabled=_flag(env.get(LIVE_TRADING_FLAG), default=False),
        broker_paper_mode=_flag(env.get("BROKER_PAPER_MODE"), default=True),
        heartbeat_threshold_s=heartbeat_s,
        stale_data_threshold_s=stale_s,
        approval_timeout_s=timeout_s,
    )
