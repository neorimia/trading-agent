"""Idempotently seed reference and research-source data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import psycopg
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.db.config import require_database_url
from src.research.registry import load_source_registry


def _instrument_assets(symbol: str, asset_class: str) -> tuple[str, str | None]:
    if asset_class in {"crypto", "fx"}:
        for quote in ("USDT", "USDC", "USD", "EUR", "GBP", "JPY"):
            if symbol.endswith(quote) and len(symbol) > len(quote):
                return symbol[: -len(quote)], quote
        raise ValueError(f"cannot infer quote asset from {symbol!r}")
    return symbol, "USD"


def seed_reference_data(
    connection: psycopg.Connection,
    *,
    universe_path: Path,
    sources_path: Path,
) -> dict[str, int]:
    universe_raw = yaml.safe_load(universe_path.read_text(encoding="utf-8"))
    instruments = universe_raw.get("instruments", [])
    if not isinstance(instruments, list):
        raise ValueError("universe.yaml must contain an instruments list")

    exchanges = {
        "KRAKEN": ("Kraken", "crypto_exchange", True, True),
        "BINANCE": ("Binance", "crypto_exchange", False, True),
        "IBKR": ("Interactive Brokers", "broker", False, False),
        "NASDAQ": ("Nasdaq", "stock_exchange", False, False),
    }
    for code, (name, kind, execution, historical) in exchanges.items():
        connection.execute(
            """
            INSERT INTO exchanges (
                code, name, kind, supports_execution, supports_historical_data
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                kind = EXCLUDED.kind,
                supports_execution = EXCLUDED.supports_execution,
                supports_historical_data = EXCLUDED.supports_historical_data
            """,
            (code, name, kind, execution, historical),
        )

    for item in instruments:
        if not isinstance(item, dict):
            raise ValueError("each universe instrument must be a mapping")
        symbol = str(item["symbol"]).strip().upper()
        asset_class = str(item["asset_class"]).strip()
        venue = str(item["venue"]).strip().upper()
        base_symbol, quote_symbol = _instrument_assets(symbol, asset_class)
        for asset_symbol, stored_class in (
            (base_symbol, asset_class),
            (quote_symbol, "cash"),
        ):
            if asset_symbol is None:
                continue
            connection.execute(
                """
                INSERT INTO assets (symbol, asset_class, name)
                VALUES (%s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET asset_class = EXCLUDED.asset_class
                """,
                (asset_symbol, stored_class, asset_symbol),
            )
        row = connection.execute(
            """
            INSERT INTO instruments (
                base_asset_id, quote_asset_id, asset_class, canonical_symbol,
                min_notional, lot_size, tick_size
            ) VALUES (
                (SELECT asset_id FROM assets WHERE symbol = %s),
                (SELECT asset_id FROM assets WHERE symbol = %s),
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (canonical_symbol) DO UPDATE SET
                min_notional = EXCLUDED.min_notional,
                lot_size = EXCLUDED.lot_size,
                tick_size = EXCLUDED.tick_size,
                status = 'active'
            RETURNING instrument_id
            """,
            (
                base_symbol,
                quote_symbol,
                asset_class,
                symbol,
                Decimal(str(item.get("min_notional", 1))),
                Decimal(str(item.get("lot_size", 1))),
                Decimal(str(item.get("tick_size", "0.01"))),
            ),
        ).fetchone()
        exchange = connection.execute(
            "SELECT exchange_id FROM exchanges WHERE code = %s",
            (venue,),
        ).fetchone()
        if row is None or exchange is None:
            raise ValueError(f"failed to seed instrument {symbol}")
        instrument_id = (
            row["instrument_id"] if isinstance(row, dict) else row[0]
        )
        exchange_id = (
            exchange["exchange_id"] if isinstance(exchange, dict) else exchange[0]
        )
        connection.execute(
            """
            INSERT INTO instrument_symbols (
                instrument_id, exchange_id, venue_symbol, role, is_primary
            ) VALUES (%s, %s, %s, 'both', true)
            ON CONFLICT (instrument_id, exchange_id, role) DO UPDATE SET
                venue_symbol = EXCLUDED.venue_symbol,
                is_primary = true
            """,
            (instrument_id, exchange_id, symbol),
        )

    sources = load_source_registry(sources_path)
    for source in sources:
        connection.execute(
            """
            INSERT INTO research_sources (
                source_id, name, kind, base_url, credibility_score,
                robots_txt_status, tos_reviewed_at, active, rate_limit_per_min,
                min_request_interval_s, review_status, docs_url, terms_url,
                robots_url, rate_limit_source, rate_limit_notes, last_verified_at,
                attribution_required, redistribution_allowed, retention_policy, notes
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (source_id) DO UPDATE SET
                name = EXCLUDED.name,
                kind = EXCLUDED.kind,
                base_url = EXCLUDED.base_url,
                credibility_score = EXCLUDED.credibility_score,
                robots_txt_status = EXCLUDED.robots_txt_status,
                tos_reviewed_at = EXCLUDED.tos_reviewed_at,
                rate_limit_per_min = EXCLUDED.rate_limit_per_min,
                min_request_interval_s = EXCLUDED.min_request_interval_s,
                review_status = EXCLUDED.review_status,
                docs_url = EXCLUDED.docs_url,
                terms_url = EXCLUDED.terms_url,
                robots_url = EXCLUDED.robots_url,
                rate_limit_source = EXCLUDED.rate_limit_source,
                rate_limit_notes = EXCLUDED.rate_limit_notes,
                last_verified_at = EXCLUDED.last_verified_at,
                attribution_required = EXCLUDED.attribution_required,
                redistribution_allowed = EXCLUDED.redistribution_allowed,
                retention_policy = EXCLUDED.retention_policy,
                notes = EXCLUDED.notes
            """,
            (
                source.source_id,
                source.name,
                source.kind,
                source.base_url,
                Decimal(str(source.credibility_score)),
                source.robots_txt_status,
                source.tos_reviewed_at,
                source.rate_limit_per_min,
                source.min_request_interval_s,
                source.review_status,
                source.docs_url,
                source.terms_url,
                source.robots_url,
                source.rate_limit_source,
                source.rate_limit_notes,
                source.last_verified_at,
                source.attribution_required,
                source.redistribution_allowed,
                source.retention_policy,
                json.dumps(source.notes),
            ),
        )
    return {"instruments": len(instruments), "research_sources": len(sources)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("MIGRATION_DATABASE_URL"))
    parser.add_argument("--universe", type=Path, default=REPO_ROOT / "config/universe.yaml")
    parser.add_argument(
        "--research-sources",
        type=Path,
        default=REPO_ROOT / "config/research_sources.yaml",
    )
    args = parser.parse_args(argv)
    url = require_database_url(args.database_url, variable="MIGRATION_DATABASE_URL")
    with psycopg.connect(url) as connection:
        counts = seed_reference_data(
            connection,
            universe_path=args.universe,
            sources_path=args.research_sources,
        )
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
