"""Connectors — Protocol comun (mirror DataSource din src/data/sources.py) + RSS/API (design §6.2).

Rate limiting e citit din SourceConfig (min_request_interval_s sau rate_limit_per_min).
Dispatch pe source_id: alfred ≠ fred, deși folosesc același host.
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
from src.research.registry import require_fetchable

_FRED_API_BASE = "https://api.stlouisfed.org/fred"
_SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
_SEC_COMPANYFACTS_BASE = "https://data.sec.gov/api/xbrl/companyfacts"
_BLS_TIMESERIES_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
_BEA_DATA_URL = "https://apps.bea.gov/api/data"

_FRED_SERIES = {
    "FEDFUNDS": "https://fred.stlouisfed.org/series/FEDFUNDS",
    "CPIAUCSL": "https://fred.stlouisfed.org/series/CPIAUCSL",
    "UNRATE": "https://fred.stlouisfed.org/series/UNRATE",
}
_BLS_SERIES = ("CUUR0000SA0", "LNS14000000")
_CRYPTO_SYMBOLS = frozenset({"BTCUSD", "ETHUSD", "BTC", "ETH"})


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


def _min_interval_s(source: SourceConfig) -> float | None:
    if source.min_request_interval_s is not None:
        return source.min_request_interval_s
    if source.rate_limit_per_min:
        return 60.0 / source.rate_limit_per_min
    return None


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
        require_fetchable(source)
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
    """Adapter per API oficial. Dispatch pe source_id, nu doar pe host."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        api_key: str | None = None,
        bls_api_key: str | None = None,
        bea_api_key: str | None = None,
        user_agent: str | None = None,
        cik_by_symbol: dict[str, str] | None = None,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http_client = http_client
        self._owns_client = http_client is None
        self._api_key = api_key
        self._bls_api_key = bls_api_key
        self._bea_api_key = bea_api_key
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
        """Interval din min_request_interval_s, altfel 60/rate_limit_per_min."""
        interval = _min_interval_s(source)
        if interval is None:
            return
        now = self._time_fn()
        if self._last_request_at is not None:
            wait = interval - (now - self._last_request_at)
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
        require_fetchable(source)
        if source.kind != "api":
            raise ValueError(f"ApiConnector cannot fetch source kind {source.kind!r}")
        fetched_at = now if now is not None else datetime.now(timezone.utc)
        if source.source_id == "fred":
            return self._fetch_fred(source, since, fetched_at, vintage=False)
        if source.source_id == "alfred":
            return self._fetch_fred(source, since, fetched_at, vintage=True)
        if source.source_id == "sec_edgar":
            return self._fetch_sec_edgar(source, since, fetched_at)
        if source.source_id == "bls":
            return self._fetch_bls(source, since, fetched_at)
        if source.source_id == "bea":
            return self._fetch_bea(source, since, fetched_at)
        host = urlparse(source.base_url).netloc
        raise ValueError(f"no ApiConnector adapter for source {source.source_id!r} host {host!r}")

    def _fetch_fred(
        self,
        source: SourceConfig,
        since: datetime,
        fetched_at: datetime,
        *,
        vintage: bool,
    ) -> list[RawDocument]:
        if not self._api_key:
            raise ValueError("FRED requires an explicit api_key (fail loud, no silent default)")
        documents: list[RawDocument] = []
        as_of_date = fetched_at.date().isoformat()
        for series_id, series_url in _FRED_SERIES.items():
            self._throttle(source)
            params: dict[str, str] = {
                "series_id": series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "observation_start": since.date().isoformat(),
            }
            if vintage:
                params["realtime_start"] = as_of_date
                params["realtime_end"] = as_of_date
            response = self._client().get(f"{_FRED_API_BASE}/series/observations", params=params)
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

    def _equity_ciks(self) -> dict[str, str]:
        return {
            symbol: cik
            for symbol, cik in self._cik_by_symbol.items()
            if symbol.upper() not in _CRYPTO_SYMBOLS
        }

    def _fetch_sec_edgar(
        self, source: SourceConfig, since: datetime, fetched_at: datetime
    ) -> list[RawDocument]:
        if not self._user_agent:
            raise ValueError(
                "SEC EDGAR requires an explicit User-Agent with contact info "
                "(fail loud, no silent default — see sec.gov fair access policy)"
            )
        equity = self._equity_ciks()
        if not equity:
            raise ValueError(
                "SEC EDGAR requires an explicit cik_by_symbol mapping for equities "
                "(no CIK discovery in R1b; crypto symbols are skipped)"
            )
        documents: list[RawDocument] = []
        headers = {"User-Agent": self._user_agent}
        for cik in equity.values():
            self._throttle(source)
            padded_cik = cik.zfill(10)
            response = self._client().get(
                f"{_SEC_SUBMISSIONS_BASE}/CIK{padded_cik}.json",
                headers=headers,
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
            self._throttle(source)
            facts_url = f"{_SEC_COMPANYFACTS_BASE}/CIK{padded_cik}.json"
            facts_response = self._client().get(facts_url, headers=headers)
            facts_response.raise_for_status()
            documents.append(
                RawDocument(
                    url=facts_url,
                    source_id=source.source_id,
                    fetched_at=fetched_at,
                    raw_payload_ref=_raw_payload_ref(facts_url, fetched_at),
                )
            )
        return documents

    def _fetch_bls(
        self, source: SourceConfig, since: datetime, fetched_at: datetime
    ) -> list[RawDocument]:
        self._throttle(source)
        body: dict[str, object] = {
            "seriesid": list(_BLS_SERIES),
            "startyear": str(since.year),
            "endyear": str(fetched_at.year),
        }
        if self._bls_api_key:
            body["registrationkey"] = self._bls_api_key
        response = self._client().post(_BLS_TIMESERIES_URL, json=body)
        response.raise_for_status()
        payload = response.json() if response.content else {}
        series_rows = []
        if isinstance(payload, dict):
            series_rows = payload.get("Results", {}).get("series", [])
        documents: list[RawDocument] = []
        cutoff_year = since.year
        for row in series_rows:
            series_id = row.get("seriesID") if isinstance(row, dict) else None
            points = row.get("data", []) if isinstance(row, dict) else []
            if not series_id:
                continue
            for point in points:
                year_raw = point.get("year") if isinstance(point, dict) else None
                period = point.get("period") if isinstance(point, dict) else None
                value = point.get("value") if isinstance(point, dict) else None
                if not year_raw or value in (None, ""):
                    continue
                try:
                    year = int(year_raw)
                except (TypeError, ValueError):
                    continue
                if year < cutoff_year:
                    continue
                url = f"https://api.bls.gov/publicAPI/v2/timeseries/{series_id}#{year_raw}-{period or 'NA'}"
                documents.append(
                    RawDocument(
                        url=url,
                        source_id=source.source_id,
                        fetched_at=fetched_at,
                        raw_payload_ref=_raw_payload_ref(url, fetched_at),
                    )
                )
        return documents

    def _fetch_bea(
        self, source: SourceConfig, since: datetime, fetched_at: datetime
    ) -> list[RawDocument]:
        if not self._bea_api_key:
            raise ValueError("BEA requires an explicit api_key (fail loud, no silent default)")
        params = {
            "UserID": self._bea_api_key,
            "method": "GetData",
            "DataSetName": "NIPA",
            "TableName": "T10101",
            "Frequency": "Q",
            "Year": str(fetched_at.year),
            "ResultFormat": "JSON",
        }
        response = self._request_bea(source, params)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            try:
                wait_s = float(retry_after)
            except ValueError:
                wait_s = 1.0
            self._sleep_fn(wait_s)
            response = self._request_bea(source, params)
        response.raise_for_status()
        url = (
            f"{_BEA_DATA_URL}?method=GetData&DataSetName=NIPA&TableName=T10101"
            f"&Year={fetched_at.year}"
        )
        if fetched_at.year < since.year:
            return []
        return [
            RawDocument(
                url=url,
                source_id=source.source_id,
                fetched_at=fetched_at,
                raw_payload_ref=_raw_payload_ref(url, fetched_at),
            )
        ]

    def _request_bea(self, source: SourceConfig, params: dict[str, str]) -> httpx.Response:
        self._throttle(source)
        return self._client().get(_BEA_DATA_URL, params=params)
