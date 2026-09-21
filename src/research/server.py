"""HTTP loopback — singurul punct de intrare extern al procesului research (design §1, §4).

Host-ul e forțat pe loopback (127.0.0.1 / localhost / ::1), mirror src/llm/server.py.
Un singur endpoint: GET /context. Randarea e determinist (context_builder), acest proces
nu invocă niciun LLM — nu generează liber, doar interoghează MetadataStore și randează.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from src.research.context_builder import build_external_context
from src.research.store import MetadataStore

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument: str
    as_of: datetime
    max_documents: int = 5


class ContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument: str
    as_of: datetime
    external_context: str
    sources: list[str]
    generated_at: datetime
    document_count: int


app = FastAPI(title="trading-agent-research", docs_url=None, redoc_url=None)


def validate_bind_host(host: str) -> str:
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f"research server must bind to loopback, not {host!r}")
    return host


def _load_dotenv_research() -> None:
    env_path = Path(".env.research")
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def _metadata_store() -> MetadataStore:
    db_path = Path(os.environ.get("RESEARCH_METADATA_DB_PATH", "data/research/metadata.db"))
    return MetadataStore(db_path)


def _stale_after() -> timedelta:
    hours_raw = os.environ.get("RESEARCH_STALE_AFTER_HOURS", "24")
    try:
        hours = float(hours_raw)
    except ValueError:
        hours = 24.0
    return timedelta(hours=hours)


def _contradicting_pairs(
    metadata: MetadataStore, documents: list
) -> list[tuple[str, str]]:
    """Perechi (doc_id, doc_id) cu relation_type='contradicts', doar între documentele selectate."""
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []
    for doc in documents:
        for related_id, relation_type in metadata.related_documents(doc.doc_id):
            if relation_type != "contradicts":
                continue
            pair = tuple(sorted((doc.doc_id, related_id)))
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
    return pairs


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness only — does not touch the metadata DB or Ollama."""
    return {"status": "up"}


@app.get("/context", response_model=ContextResponse | None)
def get_context(request: Request) -> ContextResponse | Response:
    try:
        params = ContextRequest.model_validate(dict(request.query_params))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    metadata = _metadata_store()
    try:
        documents = metadata.query_for_context(
            params.instrument, params.as_of, limit=params.max_documents
        )
        if not documents:
            return Response(status_code=204)
        contradicting_pairs = _contradicting_pairs(metadata, documents)
        external_context = build_external_context(
            params.instrument,
            params.as_of,
            documents,
            contradicting_pairs=contradicting_pairs,
            stale_after=_stale_after(),
        )
    finally:
        metadata.close()

    return ContextResponse(
        instrument=params.instrument,
        as_of=params.as_of,
        external_context=external_context,
        sources=[doc.url for doc in documents],
        generated_at=datetime.now(timezone.utc),
        document_count=len(documents),
    )


def main() -> None:
    _load_dotenv_research()
    host = validate_bind_host(os.environ.get("RESEARCH_SERVER_HOST", "127.0.0.1"))
    port_raw = os.environ.get("RESEARCH_SERVER_PORT", "8766")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise SystemExit(f"invalid RESEARCH_SERVER_PORT: {port_raw!r}") from exc
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
