"""One-shot ingest: registry → active_sources → fetch → normalize → MetadataStore.

RSS: doar itemele din feed (titlu/link/summary), fără crawl HTML de articol.
API fără adapter (ECB Data / Eurostat) e skip, nu crash. Nu apelează /propose.
Cheile se citesc doar din procesul research (.env.research), niciodată din .env.engine.
"""

from __future__ import annotations

import html
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import httpx
import yaml
from dotenv import load_dotenv

from src.research.connectors import ApiConnector, RssConnector
from src.research.models import DocumentCategory, RawDocument, SourceConfig
from src.research.registry import active_sources, require_fetchable
from src.research.repository import ResearchRepository
from src.research.store import RawDocumentStore, normalize_document

_API_CATEGORIES: dict[str, DocumentCategory] = {
    "fred": "macro_indicator",
    "alfred": "macro_indicator",
    "bls": "macro_indicator",
    "bea": "macro_indicator",
    "sec_edgar": "filing",
}
_KNOWN_API_IDS = frozenset(_API_CATEGORIES)
logger = logging.getLogger(__name__)


def load_research_env(*, env_path: Path | None = None) -> None:
    path = env_path if env_path is not None else Path(".env.research")
    if path.is_file():
        load_dotenv(path, override=False)


def load_cik_by_symbol(path: str | Path) -> dict[str, str]:
    cik_path = Path(path)
    if not cik_path.is_file():
        raise ValueError(f"sec cik map missing or not a file: {cik_path}")
    raw = yaml.safe_load(cik_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("cik_by_symbol"), dict):
        raise ValueError("sec cik map must contain cik_by_symbol")
    mapping: dict[str, str] = {}
    for symbol, cik in raw["cik_by_symbol"].items():
        mapping[str(symbol)] = str(cik).lstrip("0") or "0"
    return mapping


def required_credentials(sources: Sequence[SourceConfig]) -> None:
    """Fail loud înainte de HTTP dacă lipsește o cheie pentru o sursă activă."""
    fetchable = active_sources(sources)
    ids = {source.source_id for source in fetchable}
    if ids & {"fred", "alfred"} and not os.environ.get("FRED_API_KEY"):
        raise ValueError("FRED_API_KEY is required for fred/alfred ingest")
    if "bea" in ids and not os.environ.get("BEA_API_KEY"):
        raise ValueError("BEA_API_KEY is required for bea ingest")
    if ids & {"sec_edgar", "sec_press_rss"} and not os.environ.get("RESEARCH_USER_AGENT"):
        raise ValueError("RESEARCH_USER_AGENT is required for sec_edgar ingest")


def _title_for(raw: RawDocument) -> str:
    if raw.title:
        return raw.title
    return f"{raw.source_id} {raw.url}"


def _category_for(source: SourceConfig) -> DocumentCategory:
    if source.kind == "rss":
        return "news"
    return _API_CATEGORIES.get(source.source_id, "macro_indicator")


def _html_payload(raw: RawDocument, title: str) -> bytes:
    summary = raw.summary or (
        f"{title}. Official data point from source {raw.source_id} at {raw.url}. "
        "This record stores metadata and a short summary only."
    )
    return (
        "<html><body><article>"
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(summary)}</p>"
        "</article></body></html>"
    ).encode("utf-8")


def ingest_source(
    source: SourceConfig,
    *,
    connector: ApiConnector,
    metadata: ResearchRepository,
    since: datetime,
    now: datetime | None = None,
    known_instruments: Sequence[str] = (),
    rss_connector: RssConnector | None = None,
    raw_store: RawDocumentStore | None = None,
) -> int:
    """Fetch + normalize o sursă. Pending → ValueError. API fără adapter → 0, zero HTTP."""
    require_fetchable(source)
    fetched_at = now if now is not None else datetime.now(timezone.utc)
    if source.kind == "rss":
        if rss_connector is None:
            raise ValueError("rss_connector is required for rss ingest")
        try:
            documents = rss_connector.fetch(source, since, now=fetched_at)
        except httpx.HTTPError as exc:
            logger.warning("skip rss ingest for %s: %s", source.source_id, exc)
            return 0
    elif source.kind == "api":
        if source.source_id not in _KNOWN_API_IDS:
            logger.info("skip ingest for %s: no ApiConnector adapter", source.source_id)
            return 0
        documents = connector.fetch(source, since, now=fetched_at)
    else:
        raise ValueError(f"ingest does not start {source.kind} sources ({source.source_id})")
    written = 0
    for raw in documents:
        title = _title_for(raw)
        payload = _html_payload(raw, title)
        if raw_store is not None:
            raw_store.save(raw, payload)
        normalized = normalize_document(
            raw,
            payload,
            title=title,
            category=_category_for(source),
            known_instruments=known_instruments,
        )
        metadata.upsert(normalized)
        written += 1
    return written


def ingest_active(
    sources: Sequence[SourceConfig],
    *,
    connector: ApiConnector,
    metadata: ResearchRepository,
    since: datetime,
    now: datetime | None = None,
    known_instruments: Sequence[str] = (),
    rss_connector: RssConnector | None = None,
    raw_store: RawDocumentStore | None = None,
) -> int:
    written = 0
    for source in active_sources(sources):
        written += ingest_source(
            source,
            connector=connector,
            metadata=metadata,
            since=since,
            now=now,
            known_instruments=known_instruments,
            rss_connector=rss_connector,
            raw_store=raw_store,
        )
    return written


def build_api_connector_from_env(
    *,
    cik_by_symbol: dict[str, str] | None = None,
    http_client: httpx.Client | None = None,
) -> ApiConnector:
    return ApiConnector(
        http_client=http_client,
        api_key=os.environ.get("FRED_API_KEY") or None,
        bls_api_key=os.environ.get("BLS_API_KEY") or None,
        bea_api_key=os.environ.get("BEA_API_KEY") or None,
        user_agent=os.environ.get("RESEARCH_USER_AGENT") or None,
        cik_by_symbol=cik_by_symbol or {},
    )


def build_rss_connector_from_env(
    *,
    http_client: httpx.Client | None = None,
) -> RssConnector:
    return RssConnector(
        http_client=http_client,
        user_agent=os.environ.get("RESEARCH_USER_AGENT") or None,
    )
