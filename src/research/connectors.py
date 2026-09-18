"""Connectors — Protocol comun (mirror DataSource din src/data/sources.py) + RSS/API (design §6.2).

Rate limiting e explicit, per sursă, citit din SourceConfig.rate_limit_per_min —
niciodată hardcodat în cod (Riscuri R1a/R1b, workflow_research-financiar.md §6).
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from time import struct_time
from typing import Callable, Protocol
from urllib.parse import urlparse

import feedparser
import httpx

from src.research.models import RawDocument, SourceConfig

_FRED_API_BASE = "https://api.stlouisfed.org/fred"
_SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"

# Macro: dobânzi, inflație, șomaj (R1b — FRED series id -> pagina publică pentru citare).
_FRED_SERIES = {
    "FEDFUNDS": "https://fred.stlouisfed.org/series/FEDFUNDS",
    "CPIAUCSL": "https://fred.stlouisfed.org/series/CPIAUCSL",
    "UNRATE": "https://fred.stlouisfed.org/series/UNRATE",
}


class Connector(Protocol):
    def fetch(self, source: SourceConfig, since: datetime) -> list[RawDocument]: ...


def _raw_payload_ref(url: str, fetched_at: datetime) -> str:
    """Cheie stabilă sha256(url|fetched_at) — pointer pe care RawDocumentStore (R2) îl va folosi ca nume de fișier."""
    digest = hashlib.sha256()
    digest.update(url.encode("utf-8"))
    digest.update(b"|")
    digest.update(fetched_at.astimezone(timezone.utc).isoformat().encode("utf-8"))
    return digest.hexdigest()


def _struct_time_to_utc(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime(*value[:6], tzinfo=timezone.utc)


class RssConnector:
    """Poll pe feed RSS/Atom oficial — mirror stilistic al BinanceKlinesSource (owns_client)."""

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=30.0)
        return self._http_client

    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        *,
        now: datetime | None = None,
    ) -> list[RawDocument]:
        if source.kind != "rss":
            raise ValueError(f"RssConnector cannot fetch source kind {source.kind!r}")
        response = self._client().get(source.base_url)
        response.raise_for_status()
        feed = feedparser.parse(response.content)

        fetched_at = now if now is not None else datetime.now(timezone.utc)
        documents: list[RawDocument] = []
        for entry in feed.entries:
            link = entry.get("link")
            if not link:
                continue
            published = _struct_time_to_utc(entry.get("published_parsed")) or _struct_time_to_utc(
                entry.get("updated_parsed")
            )
            if published is not None and published <= since:
                continue
            documents.append(
                RawDocument(
                    url=link,
                    source_id=source.source_id,
                    fetched_at=fetched_at,
                    raw_payload_ref=_raw_payload_ref(link, fetched_at),
                )
            )
        return documents


class ApiConnector:
    """Adapter per API oficial (FRED, SEC EDGAR) — dispatch intern după host-ul din base_url."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        api_key: str | None = None,
        user_agent: str | None = None,
        cik_by_symbol: dict[str, str] | None = None,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http_client = http_client
        self._owns_client = http_client is None
        self._api_key = api_key
        self._user_agent = user_agent
        self._cik_by_symbol = cik_by_symbol or {}
        self._time_fn = time_fn
        self._sleep_fn = sleep_fn
        self._last_request_at: float | None = None

    def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=30.0)
        return self._http_client

    def _throttle(self, source: SourceConfig) -> None:
        """Impune rate_limit_per_min al sursei (config, nu hardcodat) — un sleep măsurabil în teste."""
        if not source.rate_limit_per_min:
            return
        min_interval = 60.0 / source.rate_limit_per_min
        now = self._time_fn()
        if self._last_request_at is not None:
            wait = min_interval - (now - self._last_request_at)
            if wait > 0:
                self._sleep_fn(wait)
        self._last_request_at = self._time_fn()

    def fetch(
        self,
        source: SourceConfig,
        since: datetime,
        *,
        now: datetime | None = None,
    ) -> list[RawDocument]:
        if source.kind != "api":
            raise ValueError(f"ApiConnector cannot fetch source kind {source.kind!r}")
        fetched_at = now if now is not None else datetime.now(timezone.utc)
        host = urlparse(source.base_url).netloc
        if host.endswith("stlouisfed.org"):
            return self._fetch_fred(source, since, fetched_at)
        if host.endswith("sec.gov"):
            return self._fetch_sec_edgar(source, since, fetched_at)
        raise ValueError(f"no ApiConnector adapter for host {host!r}")

    def _fetch_fred(
        self, source: SourceConfig, since: datetime, fetched_at: datetime
    ) -> list[RawDocument]:
        if not self._api_key:
            raise ValueError("FRED requires an explicit api_key (fail loud, no silent default)")
        documents: list[RawDocument] = []
        for series_id, series_url in _FRED_SERIES.items():
            self._throttle(source)
            response = self._client().get(
                f"{_FRED_API_BASE}/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": self._api_key,
                    "file_type": "json",
                    "observation_start": since.date().isoformat(),
                },
            )
            response.raise_for_status()
            payload = response.json()
            observations = payload.get("observations", []) if isinstance(payload, dict) else []
            for obs in observations:
                obs_date_raw = obs.get("date")
                value = obs.get("value")
                if not obs_date_raw or value in (None, "."):
                    continue
                obs_date = datetime.fromisoformat(obs_date_raw).replace(tzinfo=timezone.utc)
                if obs_date <= since:
                    continue
                url = f"{series_url}#{obs_date_raw}"
                documents.append(
                    RawDocument(
                        url=url,
                        source_id=source.source_id,
                        fetched_at=fetched_at,
                        raw_payload_ref=_raw_payload_ref(url, fetched_at),
                    )
                )
        return documents

    def _fetch_sec_edgar(
        self, source: SourceConfig, since: datetime, fetched_at: datetime
    ) -> list[RawDocument]:
        if not self._user_agent:
            raise ValueError(
                "SEC EDGAR requires an explicit User-Agent with contact info "
                "(fail loud, no silent default — see sec.gov fair access policy)"
            )
        if not self._cik_by_symbol:
            raise ValueError(
                "SEC EDGAR requires an explicit cik_by_symbol mapping (no CIK discovery in R1b)"
            )
        documents: list[RawDocument] = []
        for cik in self._cik_by_symbol.values():
            self._throttle(source)
            padded_cik = cik.zfill(10)
            response = self._client().get(
                f"{_SEC_SUBMISSIONS_BASE}/CIK{padded_cik}.json",
                headers={"User-Agent": self._user_agent},
            )
            response.raise_for_status()
            payload = response.json()
            recent = payload.get("filings", {}).get("recent", {}) if isinstance(payload, dict) else {}
            forms = recent.get("form", [])
            filing_dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            primary_docs = recent.get("primaryDocument", [])
            for _form, filing_date_raw, accession, primary_doc in zip(
                forms, filing_dates, accessions, primary_docs
            ):
                if not filing_date_raw:
                    continue
                filing_date = datetime.fromisoformat(filing_date_raw).replace(tzinfo=timezone.utc)
                if filing_date <= since:
                    continue
                accession_no_dashes = accession.replace("-", "")
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{primary_doc}"
                documents.append(
                    RawDocument(
                        url=url,
                        source_id=source.source_id,
                        fetched_at=fetched_at,
                        raw_payload_ref=_raw_payload_ref(url, fetched_at),
                    )
                )
        return documents
