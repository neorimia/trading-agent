"""HTTP loopback — singurul punct de intrare extern al procesului LLM.

Host-ul e forțat pe loopback (127.0.0.1 / localhost / ::1); 0.0.0.0 e refuzat.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.llm.schema import (
    AnalysisType,
    LLMAnalysis,
    LLMProposal,
    RejectedAnalysis,
    RejectedProposal,
)
from src.llm.service import (
    AnalysisInput,
    ProposalInput,
    generate_analysis,
    generate_proposal,
    load_llm_settings,
    load_universe,
    validate_analysis_against_universe,
    validate_against_universe,
)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ENGINE_BROKER_KEYS = (
    "BROKER_PAPER_MODE",
    "BROKER_NAME",
    "BROKER_API_KEY",
    "BROKER_API_SECRET",
    "BROKER_ACCOUNT_ID",
    "KRAKEN_SPOT_API_KEY",
    "KRAKEN_SPOT_API_SECRET",
    "KRAKEN_FUTURES_API_KEY",
    "KRAKEN_FUTURES_API_SECRET",
    "KRAKEN_FUTURES_DEMO_API_KEY",
    "KRAKEN_FUTURES_DEMO_API_SECRET",
    "LIVE_TRADING_ENABLED",
)


class ProposeRequest(BaseModel):
    """Corpul POST /propose — independent de engine.ProposalContext."""

    model_config = ConfigDict(extra="forbid")

    instrument: str = Field(min_length=1)
    as_of: datetime
    market_summary: str
    external_context: str | None = None


class AnalyzeRequest(BaseModel):
    """Corpul POST /analyze — research only, niciodată un ordin."""

    model_config = ConfigDict(extra="forbid")

    instrument: str = Field(min_length=1)
    as_of: datetime
    analysis_type: AnalysisType
    timeframe: str = Field(default="1d", min_length=1)
    facts_bundle: dict = Field(default_factory=dict)
    external_context: str | None = None


app = FastAPI(title="trading-agent-llm", docs_url=None, redoc_url=None)


def validate_bind_host(host: str) -> str:
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f"LLM server must bind to loopback, not {host!r}")
    return host


def assert_no_broker_keys(environ: dict[str, str] | None = None) -> None:
    """Refuză pornirea dacă procesul vede cheile de broker din .env.engine."""
    env = environ if environ is not None else os.environ
    present = [key for key in _ENGINE_BROKER_KEYS if key in env]
    if present:
        raise RuntimeError(
            "LLM process must not see broker env vars: " + ", ".join(present)
        )


def _load_dotenv_llm() -> None:
    env_path = Path(".env.llm")
    if env_path.is_file():
        load_dotenv(env_path, override=False)


@app.post("/propose")
def propose(body: ProposeRequest) -> LLMProposal | RejectedProposal:
    config, universe_path = load_llm_settings()
    try:
        universe = load_universe(universe_path)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    context = ProposalInput(
        instrument=body.instrument,
        as_of=body.as_of,
        market_summary=body.market_summary,
        external_context=body.external_context,
    )
    result = generate_proposal(context, config)
    if isinstance(result, LLMProposal):
        return validate_against_universe(result, universe)
    return result


@app.post("/analyze")
def analyze(body: AnalyzeRequest) -> LLMAnalysis | RejectedAnalysis:
    config, universe_path = load_llm_settings()
    try:
        universe = load_universe(universe_path)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    context = AnalysisInput(
        instrument=body.instrument,
        as_of=body.as_of,
        analysis_type=body.analysis_type,
        timeframe=body.timeframe,
        facts_bundle=body.facts_bundle,
        external_context=body.external_context,
    )
    result = generate_analysis(context, config)
    if isinstance(result, LLMAnalysis):
        return validate_analysis_against_universe(
            result, universe, expected_instrument=body.instrument
        )
    return result


def main() -> None:
    _load_dotenv_llm()
    assert_no_broker_keys()
    host = validate_bind_host(os.environ.get("LLM_SERVER_HOST", "127.0.0.1"))
    port_raw = os.environ.get("LLM_SERVER_PORT", "8765")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise SystemExit(f"invalid LLM_SERVER_PORT: {port_raw!r}") from exc
    # Re-validare la boot: universe trebuie să existe, altfel refuzăm pornirea.
    _, universe_path = load_llm_settings()
    load_universe(universe_path)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
