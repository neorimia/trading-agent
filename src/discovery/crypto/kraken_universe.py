"""Instrument discovery Kraken — AssetPairs/Ticker/OHLC publice, fără chei (§2.1, §10.6).

Zero autentificare, aceeași regulă ca `KrakenPublicOHLCSource` ("Interzis în procesul llm/").
Nu reutilizează `KrakenPublicOHLCSource.fetch_bars` direct — acela rezolvă simboluri din
`UNIVERSE_TO_KRAKEN` (universul activ, 2 intrări); aici lucrăm cu perechi Kraken brute,
încă nefiltrate/nemapate la universul propriu.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Sequence

import httpx

from src.discovery.models import DiscoveredInstrument, HistoricalStats, InstrumentSnapshot

KRAKEN_ASSET_PAIRS_URL = "https://api.kraken.com/0/public/AssetPairs"
KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"

_STATUS_MAP = {
    "online": "online",
    "cancel_only": "cancel_only",
    "post_only": "post_only",
    "limit_only": "limit_only",
    "reduce_only": "cancel_only",
    "maintenance": "cancel_only",
}
_BATCH_SIZE = 20


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _chunks(items: Sequence[str], size: int) -> list[list[str]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _normalize_altname(altname: str) -> str:
    """"XBT" (codul ISO-4217-style Kraken pentru Bitcoin) -> "BTC" (convenția restului repo-ului).

    Fără normalizare, altname-ul canonic Kraken pentru BTC/USD ("XBTUSD") nu s-ar potrivi
    niciodată cu cheia din `venue_registry._INSTRUMENTS` ("BTCUSD"), iar `has_execution_venue`
    n-ar recunoaște niciodată BTC drept deja executabil.
    """
    if altname.startswith("XBT"):
        return "BTC" + altname[3:]
    return altname


class KrakenAssetUniverseProvider:
    """`AssetUniverseProvider` + `InstrumentMetadataProvider` pentru Kraken spot."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        min_interval_s: float = 1.0,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http_client = http_client
        self._owns_client = http_client is None
        self._min_interval_s = min_interval_s
        self._time_fn = time_fn
        self._sleep_fn = sleep_fn
        self._last_request_at: float | None = None
        # Populat de discover(): altname (ex. "ETHUSD") -> cheia brută AssetPairs (ex. "XETHZUSD").
        # Kraken confirmă empiric (Ticker/OHLC) că răspunsul e indexat după cheia cerută în query —
        # dar NU după altname dacă alias-ul diferă de cheia canonică (ex. query altname="BTCUSD" ->
        # rezultat cheie "XXBTZUSD", nu "BTCUSD"). Interogăm deci cu cheia brută și traducem
        # rezultatul înapoi la altname, ca output-ul să rămână identificat consistent cu discover().
        self._raw_key_by_altname: dict[str, str] = {}

    def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=30.0)
        return self._http_client

    def _throttle(self) -> None:
        now = self._time_fn()
        if self._last_request_at is not None:
            wait = self._min_interval_s - (now - self._last_request_at)
            if wait > 0:
                self._sleep_fn(wait)
        self._last_request_at = self._time_fn()

    def _get(self, url: str, params: dict[str, str]) -> dict:
        self._throttle()
        response = self._client().get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"unexpected Kraken payload from {url}")
        errors = payload.get("error") or []
        if errors:
            raise ValueError(f"Kraken error from {url}: {errors}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError(f"Kraken result missing from {url}")
        return result

    def discover(self, *, quote_currencies: frozenset[str] = frozenset({"ZUSD", "USD"})) -> list[DiscoveredInstrument]:
        result = self._get(KRAKEN_ASSET_PAIRS_URL, {})
        instruments: list[DiscoveredInstrument] = []
        for pair_code, entry in result.items():
            if not isinstance(entry, dict):
                continue
            quote = entry.get("quote")
            if quote not in quote_currencies:
                continue
            base = entry.get("base")
            status = _STATUS_MAP.get(entry.get("status"))
            if not base or status is None:
                continue
            # `altname` (ex. "ETHUSD"), nu cheia din dict (ex. "XETHZUSD") — Ticker/OHLC accept
            # ambele, dar `venue_registry.py`/`kraken.py` folosesc altname ca identificator canonic
            # (vezi `_INSTRUMENTS["ETHUSD"].kraken_pair == "ETHUSD"`); altfel `has_execution_venue`
            # nu ar recunoaște niciodată instrumentele deja executabile.
            altname = entry.get("altname")
            if not altname:
                continue
            altname = _normalize_altname(str(altname))
            self._raw_key_by_altname[altname] = pair_code
            instruments.append(
                DiscoveredInstrument(
                    exchange_pair=altname,
                    base=str(base),
                    quote=str(quote),
                    status=status,
                    ordermin=_decimal_or_none(entry.get("ordermin")),
                    costmin=_decimal_or_none(entry.get("costmin")),
                )
            )
        return instruments

    def snapshot(self, exchange_pairs: Sequence[str]) -> dict[str, InstrumentSnapshot]:
        # Traducem la cheia brută (dacă discover() a populat maparea) — Kraken răspunde indexat
        # după cheia din query, nu neapărat după altname (vezi comentariul din __init__).
        requested_by_raw_key: dict[str, str] = {}
        query_keys: list[str] = []
        for pair in exchange_pairs:
            raw_key = self._raw_key_by_altname.get(pair, pair)
            requested_by_raw_key[raw_key] = pair
            query_keys.append(raw_key)

        snapshots: dict[str, InstrumentSnapshot] = {}
        for batch in _chunks(query_keys, _BATCH_SIZE):
            result = self._get(KRAKEN_TICKER_URL, {"pair": ",".join(batch)})
            for pair_code, entry in result.items():
                if not isinstance(entry, dict):
                    continue
                ask = entry.get("a")
                bid = entry.get("b")
                last = entry.get("c")
                volume = entry.get("v")
                if not (isinstance(ask, list) and isinstance(bid, list) and isinstance(last, list) and isinstance(volume, list)):
                    continue
                requested = requested_by_raw_key.get(pair_code, pair_code)
                snapshots[requested] = InstrumentSnapshot(
                    exchange_pair=requested,
                    last_price=Decimal(str(last[0])),
                    bid=Decimal(str(bid[0])),
                    ask=Decimal(str(ask[0])),
                    volume_24h=Decimal(str(volume[1])),
                )
        return snapshots

    def _fetch_daily_ohlc(self, exchange_pair: str, since: datetime) -> list[list]:
        raw_key = self._raw_key_by_altname.get(exchange_pair, exchange_pair)
        result = self._get(
            KRAKEN_OHLC_URL,
            {"pair": raw_key, "interval": "1440", "since": str(int(since.timestamp()))},
        )
        series = None
        for key, value in result.items():
            if key == "last":
                continue
            series = value
            break
        if not isinstance(series, list):
            raise ValueError(f"Kraken OHLC series missing for {exchange_pair!r}")
        return [row for row in series if isinstance(row, list) and len(row) >= 7]

    def historical_stats(
        self,
        exchange_pair: str,
        *,
        history_days_requested: int = 90,
        now: datetime | None = None,
    ) -> HistoricalStats:
        moment = now if now is not None else datetime.now(timezone.utc)

        recent_rows = self._fetch_daily_ohlc(exchange_pair, moment - timedelta(days=history_days_requested))
        closes = [float(row[4]) for row in recent_rows]
        volumes = [float(row[6]) for row in recent_rows]

        # Vechimea listării: interval public zilnic Kraken întoarce max ~720 bare — un `since`
        # foarte vechi capătă efectiv "cât de departe merge istoricul disponibil" (§2.1).
        oldest_rows = self._fetch_daily_ohlc(exchange_pair, moment - timedelta(days=2000))
        if oldest_rows:
            first_ts = datetime.fromtimestamp(int(oldest_rows[0][0]), tz=timezone.utc)
            listing_age_days = max(0, (moment - first_ts).days)
        else:
            listing_age_days = 0

        return HistoricalStats(
            exchange_pair=exchange_pair,
            listing_age_days=listing_age_days,
            history_days_available=len(recent_rows),
            history_days_requested=history_days_requested,
            daily_closes=closes,
            daily_volumes=volumes,
        )
