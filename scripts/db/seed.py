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
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.db.config import require_database_url
from src.research.registry import load_source_registry

# The 4 `runtime/paper*` directories the design doc calls out (docs/database-design.md
# §8.4) as 4 comparable rulări/scenarii — seeded as portfolios regardless of whether
# the directory currently exists on disk (fresh checkouts have none of them yet).
# "paper-csv" is the CSV-fixture backtest harness (src/data/sources.py
# CsvBarDataSource) and never talks to Kraken, so it gets no exchange_account_id.
PAPER_PORTFOLIOS: tuple[str, ...] = ("paper", "paper-kraken", "paper-csv", "paper-faza5")
_KRAKEN_PORTFOLIO_ACCOUNT_LABEL = "paper-kraken-spot"


def _optional_decimal(raw: object) -> Decimal | None:
    if raw is None:
        return None
    return Decimal(str(raw))


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

    # Vendors that supply OHLCV candles (distinct from research_sources above, which
    # are news/filing sources — docs/database-design.md §8.3). csv_fixture has no
    # exchange (used only by tests/local CSV backtests, src/data/sources.py
    # CsvBarDataSource).
    market_data_sources = (
        ("kraken_public_ohlc", "KRAKEN", "rest_public", False, None),
        ("binance_public_klines", "BINANCE", "rest_public", False, None),
        ("csv_fixture", None, "vendor_bulk", False, None),
    )
    for name, exchange_code, kind, requires_auth, rate_limit in market_data_sources:
        exchange_id = None
        if exchange_code is not None:
            exchange_row = connection.execute(
                "SELECT exchange_id FROM exchanges WHERE code = %s",
                (exchange_code,),
            ).fetchone()
            if exchange_row is None:
                raise ValueError(
                    f"unknown exchange code {exchange_code!r} for market data source {name!r}"
                )
            exchange_id = (
                exchange_row["exchange_id"]
                if isinstance(exchange_row, dict)
                else exchange_row[0]
            )
        connection.execute(
            """
            INSERT INTO market_data_sources (
                name, exchange_id, kind, requires_auth, rate_limit_per_min
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                exchange_id = EXCLUDED.exchange_id,
                kind = EXCLUDED.kind,
                requires_auth = EXCLUDED.requires_auth,
                rate_limit_per_min = EXCLUDED.rate_limit_per_min,
                active = true
            """,
            (name, exchange_id, kind, requires_auth, rate_limit),
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
    return {
        "instruments": len(instruments),
        "research_sources": len(sources),
        "market_data_sources": len(market_data_sources),
    }


def seed_execution_reference_data(
    connection: psycopg.Connection,
    *,
    strategies_path: Path,
    strategy_versions_dir: Path,
    risk_limits_path: Path,
    paper_config_path: Path,
) -> dict[str, int]:
    """Versioned strategy/risk config + paper portfolios (design Phases 3+4).

    Must run after `seed_reference_data` (needs `exchanges`) and requires
    `migrations/versions/0003_execution_risk.py` to already be applied.

    Strategy version rows come only from the immutable
    `config/strategy_versions/<id>/vN.json` snapshots — never invented from the
    mutable `strategies.yaml` alone. A strategy with no matching snapshot file fails
    the seed loudly instead of fabricating version history.

    `risk_limits` versioning: if the current YAML values differ from the open row
    (`effective_to IS NULL`), the open row is closed (`effective_to = now()`) and a
    new version is inserted; if they match, this is a no-op. Never an UPDATE of an
    already-active version's values (docs/database-design.md §8.9).
    """
    strategies_raw = yaml.safe_load(strategies_path.read_text(encoding="utf-8"))
    strategies = strategies_raw.get("strategies", [])
    if not isinstance(strategies, list):
        raise ValueError("strategies.yaml must contain a strategies list")

    with connection.cursor(row_factory=dict_row) as cur:
        for item in strategies:
            if not isinstance(item, dict):
                raise ValueError("each strategy must be a mapping")
            strategy_id = str(item["id"]).strip()
            kind = str(item["kind"]).strip()
            cur.execute(
                """
                INSERT INTO strategies (strategy_id, name, kind, enabled)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (strategy_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    kind = EXCLUDED.kind,
                    enabled = EXCLUDED.enabled,
                    updated_at = now()
                """,
                (strategy_id, str(item["name"]), kind, bool(item.get("enabled", False))),
            )
            version = int(item.get("version", 1))
            version_path = strategy_versions_dir / strategy_id / f"v{version}.json"
            if not version_path.is_file():
                raise ValueError(
                    f"missing immutable strategy version snapshot for {strategy_id!r}: "
                    f"{version_path} — seed never invents a version from "
                    "strategies.yaml alone"
                )
            snapshot = json.loads(version_path.read_text(encoding="utf-8"))
            cur.execute(
                """
                INSERT INTO strategy_versions (
                    strategy_id, version, params, change_note, is_active
                ) VALUES (%s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (strategy_id, version) DO NOTHING
                """,
                (
                    strategy_id,
                    int(snapshot["version"]),
                    json.dumps(snapshot.get("params", {})),
                    snapshot.get("change_note"),
                    bool(snapshot.get("enabled", True)),
                ),
            )

        risk_raw = yaml.safe_load(risk_limits_path.read_text(encoding="utf-8"))
        if not isinstance(risk_raw, dict):
            raise ValueError("risk_limits.yaml must contain a mapping")
        circuit = risk_raw.get("circuit_breaker") or {}
        candidate = {
            "max_notional_per_order": Decimal(str(risk_raw["max_notional_per_order"])),
            "max_exposure_per_instrument": Decimal(str(risk_raw["max_exposure_per_instrument"])),
            "max_exposure_per_asset_class": Decimal(str(risk_raw["max_exposure_per_asset_class"])),
            "max_daily_loss": Decimal(str(risk_raw["max_daily_loss"])),
            "max_drawdown": Decimal(str(risk_raw["max_drawdown"])),
            "max_orders_per_day": int(risk_raw["max_orders_per_day"]),
            "max_consecutive_errors": int(circuit["max_consecutive_errors"]),
            "max_consecutive_losses": int(circuit["max_consecutive_losses"]),
            "halt_on_unknown_order_result": bool(circuit["halt_on_unknown_order_result"]),
            "max_risk_per_trade": _optional_decimal(risk_raw.get("max_risk_per_trade")),
            "min_reward_risk_ratio": _optional_decimal(risk_raw.get("min_reward_risk_ratio")),
            "max_spread_bps": _optional_decimal(risk_raw.get("max_spread_bps")),
            "min_bar_volume": _optional_decimal(risk_raw.get("min_bar_volume")),
            "max_correlated_exposure": _optional_decimal(risk_raw.get("max_correlated_exposure")),
        }
        cur.execute(
            """
            SELECT risk_limits_version_id, max_notional_per_order,
                   max_exposure_per_instrument, max_exposure_per_asset_class,
                   max_daily_loss, max_drawdown, max_orders_per_day,
                   max_consecutive_errors, max_consecutive_losses,
                   halt_on_unknown_order_result, max_risk_per_trade,
                   min_reward_risk_ratio, max_spread_bps, min_bar_volume,
                   max_correlated_exposure
            FROM risk_limits WHERE effective_to IS NULL
            """
        )
        current = cur.fetchone()
        changed = current is None or any(
            current[key] != value for key, value in candidate.items()
        )
        risk_limits_inserted = 0
        if changed:
            if current is not None:
                cur.execute(
                    "UPDATE risk_limits SET effective_to = now() "
                    "WHERE risk_limits_version_id = %s",
                    (current["risk_limits_version_id"],),
                )
            cur.execute(
                """
                INSERT INTO risk_limits (
                    effective_from, max_notional_per_order, max_exposure_per_instrument,
                    max_exposure_per_asset_class, max_daily_loss, max_drawdown,
                    max_orders_per_day, max_consecutive_errors, max_consecutive_losses,
                    halt_on_unknown_order_result, max_risk_per_trade,
                    min_reward_risk_ratio, max_spread_bps, min_bar_volume,
                    max_correlated_exposure, changed_by
                ) VALUES (
                    now(), %(max_notional_per_order)s, %(max_exposure_per_instrument)s,
                    %(max_exposure_per_asset_class)s, %(max_daily_loss)s, %(max_drawdown)s,
                    %(max_orders_per_day)s, %(max_consecutive_errors)s,
                    %(max_consecutive_losses)s, %(halt_on_unknown_order_result)s,
                    %(max_risk_per_trade)s, %(min_reward_risk_ratio)s, %(max_spread_bps)s,
                    %(min_bar_volume)s, %(max_correlated_exposure)s, %(changed_by)s
                )
                """,
                {**candidate, "changed_by": "seed:risk_limits.yaml"},
            )
            risk_limits_inserted = 1

        paper_raw: dict[str, object] = {}
        if paper_config_path.is_file():
            loaded = yaml.safe_load(paper_config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                paper_raw = loaded
        starting_cash = Decimal(str(paper_raw.get("starting_cash", "10000")))
        venue = str(paper_raw.get("venue", "KRAKEN")).strip().upper()

        cur.execute(
            """
            INSERT INTO exchange_accounts (exchange_id, label, trading_mode, scope)
            VALUES ((SELECT exchange_id FROM exchanges WHERE code = %s), %s, 'paper', 'spot')
            ON CONFLICT (exchange_id, trading_mode, scope, label) DO UPDATE SET
                label = EXCLUDED.label
            RETURNING exchange_account_id
            """,
            (venue, _KRAKEN_PORTFOLIO_ACCOUNT_LABEL),
        )
        account_row = cur.fetchone()
        if account_row is None:
            raise ValueError(f"unknown exchange code {venue!r} for paper exchange account")
        kraken_account_id = account_row["exchange_account_id"]

        for name in PAPER_PORTFOLIOS:
            account_id = None if name == "paper-csv" else kraken_account_id
            cur.execute(
                """
                INSERT INTO portfolios (
                    name, trading_mode, exchange_account_id, base_currency, starting_cash
                ) VALUES (%s, 'paper', %s, 'USD', %s)
                ON CONFLICT (name) DO UPDATE SET
                    exchange_account_id = EXCLUDED.exchange_account_id,
                    starting_cash = EXCLUDED.starting_cash
                """,
                (name, account_id, starting_cash),
            )

    return {
        "strategies": len(strategies),
        "risk_limits_versions_inserted": risk_limits_inserted,
        "portfolios": len(PAPER_PORTFOLIOS),
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
    parser.add_argument("--strategies", type=Path, default=REPO_ROOT / "config/strategies.yaml")
    parser.add_argument(
        "--strategy-versions",
        type=Path,
        default=REPO_ROOT / "config/strategy_versions",
    )
    parser.add_argument(
        "--risk-limits", type=Path, default=REPO_ROOT / "config/risk_limits.yaml"
    )
    parser.add_argument(
        "--paper-config", type=Path, default=REPO_ROOT / "config/paper_trading.yaml"
    )
    parser.add_argument(
        "--skip-execution",
        action="store_true",
        help="only seed reference/research data (0001+0002); skip Phase 3+4 tables",
    )
    args = parser.parse_args(argv)
    url = require_database_url(args.database_url, variable="MIGRATION_DATABASE_URL")
    with psycopg.connect(url) as connection:
        counts = seed_reference_data(
            connection,
            universe_path=args.universe,
            sources_path=args.research_sources,
        )
        if not args.skip_execution:
            counts.update(
                seed_execution_reference_data(
                    connection,
                    strategies_path=args.strategies,
                    strategy_versions_dir=args.strategy_versions,
                    risk_limits_path=args.risk_limits,
                    paper_config_path=args.paper_config,
                )
            )
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
