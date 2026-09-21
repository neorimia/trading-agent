"""Idempotent OHLCV backfill into `ohlcv_candles` with a JSON reconciliation report.

Same shape as `scripts/db/import_research.py`: seed reference data with the migration
owner's elevated connection, ingest bars, write a report an operator can gate on
before flipping `MARKET_DATA_STORE_BACKEND=postgres` (docs/database-cutover-playbook.md
§Market data; the market data cutover plan's "Cutover sequence (ops)").

Provenance: JSON window-cache files under `.cache/market_data/` do not record which
vendor (Kraken vs Binance) produced them, so `--source` is always required and network
re-backfill (the default) is the only path that can attribute bars to a source with
certainty. `--from-cache` is best-effort — it reads a frozen cache copy instead of
calling the network, and the report is always marked `provenance_incomplete: true`
for the instruments it served from cache, so operators do not mistake a guess for a
confirmed backfill.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.db.seed import seed_reference_data
from src.data.cache import _bar_from_json, _cache_key, canonical_dataset_hash
from src.data.historical import make_historical_source
from src.data.postgres_store import PostgresCandleStore
from src.data.sources import Bar
from src.data.validation import DataValidator
from src.data.venue_registry import HistoricalSource, listed_crypto_symbols
from src.db.config import require_database_url
from src.db.pool import close_database_pools

_SOURCE_NAME = {
    "KRAKEN": "kraken_public_ohlc",
    "BINANCE": "binance_public_klines",
}


def _parse_dt(raw: str) -> datetime:
    moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _load_cache_window(
    cache_dir: Path,
    instrument: str,
    start: datetime,
    end: datetime,
    timeframe: str,
) -> list[Bar] | None:
    """Best-effort read of a frozen `MarketDataCache` window file. `None` when the
    window was never fetched under this exact `(instrument, timeframe, start, end)`
    key — the caller must not guess a substitute window."""
    path = cache_dir / _cache_key(instrument, start, end, timeframe)
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("bars"), list):
        raise ValueError(f"invalid cache file: {path}")
    return [_bar_from_json(item) for item in raw["bars"]]


def import_market_data(
    *,
    database_url: str,
    universe_path: Path,
    research_sources_path: Path,
    instruments: list[str],
    timeframe: str,
    start: datetime,
    end: datetime,
    source: HistoricalSource,
    cache_dir: Path | None,
    dry_run: bool,
) -> dict[str, Any]:
    source_name = _SOURCE_NAME[source]
    validator = DataValidator()
    now = datetime.now(timezone.utc)

    if not dry_run:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            seed_reference_data(
                connection,
                universe_path=universe_path,
                sources_path=research_sources_path,
            )

    data_source = make_historical_source(source) if cache_dir is None else None
    store = PostgresCandleStore(database_url) if not dry_run else None
    provenance_incomplete = False
    per_instrument: dict[str, Any] = {}

    try:
        for instrument in instruments:
            entry: dict[str, Any] = {
                "source_window_count": 0,
                "rejected_bar_count": 0,
                "natural_key_conflicts": 0,
                "written": 0,
                "destination_count": None,
                "canonical_dataset_hash": None,
                "gaps": [],
                "used_cache": cache_dir is not None,
            }
            try:
                if cache_dir is not None:
                    cached = _load_cache_window(cache_dir, instrument, start, end, timeframe)
                    if cached is None:
                        entry["error"] = (
                            "no matching cache window file for this exact "
                            "(instrument, timeframe, start, end); skipped, not guessed"
                        )
                        provenance_incomplete = True
                        per_instrument[instrument] = entry
                        continue
                    bars = cached
                    provenance_incomplete = True
                else:
                    assert data_source is not None
                    bars = data_source.fetch_bars(instrument, start, end, timeframe)

                entry["source_window_count"] = len(bars)
                fetch_report = validator.validate(bars, timeframe, now=now)
                entry["rejected_bar_count"] = len(fetch_report.issues)
                if not fetch_report.ok:
                    entry["error"] = "; ".join(
                        f"{issue.code}: {issue.message}" for issue in fetch_report.issues
                    )
                    per_instrument[instrument] = entry
                    continue

                if store is not None:
                    existing = {
                        bar.timestamp: bar
                        for bar in store.load_bars(instrument, source_name, timeframe, start, end)
                    }
                    entry["natural_key_conflicts"] = sum(
                        1
                        for bar in bars
                        if bar.timestamp in existing
                        and (
                            existing[bar.timestamp].open != bar.open
                            or existing[bar.timestamp].high != bar.high
                            or existing[bar.timestamp].low != bar.low
                            or existing[bar.timestamp].close != bar.close
                            or existing[bar.timestamp].volume != bar.volume
                        )
                    )
                    entry["written"] = store.upsert_bars(instrument, source_name, timeframe, bars)
                    loaded = store.load_bars(instrument, source_name, timeframe, start, end)
                else:
                    loaded = bars

                entry["destination_count"] = len(loaded)
                entry["canonical_dataset_hash"] = canonical_dataset_hash(loaded)
                post_report = validator.validate(loaded, timeframe, now=now)
                entry["gaps"] = [
                    issue.message for issue in post_report.issues if issue.code == "gap"
                ]
            except ValueError as exc:
                entry["error"] = str(exc)
            per_instrument[instrument] = entry
    finally:
        if store is not None:
            store.close()
        if data_source is not None and hasattr(data_source, "close"):
            data_source.close()

    return {
        "dry_run": dry_run,
        "source": source,
        "source_name": source_name,
        "timeframe": timeframe,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "provenance_incomplete": provenance_incomplete,
        "instruments": per_instrument,
        "idempotent_key": "source_id/instrument_id/timeframe/open_time",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("MIGRATION_DATABASE_URL"))
    parser.add_argument("--universe", type=Path, default=REPO_ROOT / "config/universe.yaml")
    parser.add_argument(
        "--research-sources",
        type=Path,
        default=REPO_ROOT / "config/research_sources.yaml",
    )
    parser.add_argument(
        "--instrument",
        dest="instruments",
        action="append",
        help="Repeatable; defaults to every Kraken-listed universe symbol",
    )
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--source",
        required=True,
        choices=("KRAKEN", "BINANCE"),
        help="Vendor attribution for the ingested rows (market_data_sources.name)",
    )
    parser.add_argument(
        "--from-cache",
        type=Path,
        default=None,
        help=(
            "Read a frozen .cache/market_data/ window instead of the network "
            "(best-effort; marks the report provenance_incomplete=true)"
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    url = require_database_url(args.database_url, variable="MIGRATION_DATABASE_URL")
    instruments = args.instruments or list(listed_crypto_symbols())
    report = import_market_data(
        database_url=url,
        universe_path=args.universe,
        research_sources_path=args.research_sources,
        instruments=instruments,
        timeframe=args.timeframe,
        start=_parse_dt(args.start),
        end=_parse_dt(args.end),
        source=args.source,
        cache_dir=args.from_cache,
        dry_run=args.dry_run,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    close_database_pools()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
