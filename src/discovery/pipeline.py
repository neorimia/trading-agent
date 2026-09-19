"""Orchestrare Faza 1: discover → cheap filters → OHLC pentru supraviețuitori → scoring → filtre complete → rank.

Funnel în 2 etape (§2.1, §3): Ticker (ieftin, un call batch) filtrează grosier înainte de a
cere OHLC per-instrument (mai scump, un call per pereche) — evită sute de cereri OHLC pentru
perechi care oricum n-ar trece filtrul de lichiditate/spread.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.discovery import scoring
from src.discovery.crypto.kraken_universe import KrakenAssetUniverseProvider
from src.discovery.filters import CandidateInput, FilterRuleConfig, all_passed, evaluate_all
from src.discovery.models import (
    AssetCandidate,
    CandidateFactors,
    DiscoveryRun,
    RejectedCandidate,
    SourceRef,
)

_BTC_BASE_ALIASES = frozenset({"XXBT", "XBT", "BTC"})
_ETH_BASE_ALIASES = frozenset({"XETH", "ETH"})


def _find_reference_pair(pairs: list[str], bases: dict[str, str], aliases: frozenset[str]) -> str | None:
    for pair in pairs:
        if bases.get(pair) in aliases:
            return pair
    return None


def run_discovery(
    provider: KrakenAssetUniverseProvider,
    filter_rules: list[FilterRuleConfig],
    *,
    exchange: str = "KRAKEN",
    history_days_requested: int = 90,
    research_horizon: str = "swing (days-weeks)",
    expires_after: timedelta = timedelta(hours=24),
    now: datetime | None = None,
) -> DiscoveryRun:
    moment = now if now is not None else datetime.now(timezone.utc)

    discovered = provider.discover()
    if not discovered:
        return DiscoveryRun(run_at=moment, exchange=exchange, candidates=[], rejected=[])
    base_by_pair = {inst.exchange_pair: inst.base for inst in discovered}

    pairs = [inst.exchange_pair for inst in discovered]
    snapshots = provider.snapshot(pairs)

    cheap_survivors: list[str] = []
    rejected: list[RejectedCandidate] = []
    cheap_rule_ids = {"min_liquidity", "max_spread"}
    cheap_rules = [rule for rule in filter_rules if rule.rule_id in cheap_rule_ids] or filter_rules

    for instrument in discovered:
        snapshot = snapshots.get(instrument.exchange_pair)
        if snapshot is None:
            rejected.append(
                RejectedCandidate(
                    asset=instrument.exchange_pair,
                    exchange=exchange,
                    evaluated_at=moment,
                    filter_results=[],
                )
            )
            continue
        try:
            notional = scoring.notional_volume_usd(snapshot.last_price, snapshot.volume_24h)
            spread = scoring.spread_bps(snapshot.bid, snapshot.ask)
        except ValueError:
            rejected.append(
                RejectedCandidate(
                    asset=instrument.exchange_pair,
                    exchange=exchange,
                    evaluated_at=moment,
                    filter_results=[],
                )
            )
            continue
        cheap_input = CandidateInput(
            asset=instrument.exchange_pair,
            notional_volume_24h_usd=float(notional),
            spread_bps=spread,
            history_days_available=history_days_requested,
            price_zscore=None,
            volume_zscore=None,
            status=instrument.status,
            operational_risk_score=0.0,
        )
        cheap_results = evaluate_all(cheap_rules, cheap_input)
        if all_passed(cheap_results):
            cheap_survivors.append(instrument.exchange_pair)
        else:
            rejected.append(
                RejectedCandidate(
                    asset=instrument.exchange_pair,
                    exchange=exchange,
                    evaluated_at=moment,
                    filter_results=cheap_results,
                )
            )

    btc_pair = _find_reference_pair(cheap_survivors, base_by_pair, _BTC_BASE_ALIASES) or _find_reference_pair(
        pairs, base_by_pair, _BTC_BASE_ALIASES
    )
    eth_pair = _find_reference_pair(cheap_survivors, base_by_pair, _ETH_BASE_ALIASES) or _find_reference_pair(
        pairs, base_by_pair, _ETH_BASE_ALIASES
    )
    btc_returns = (
        scoring.log_returns(provider.historical_stats(btc_pair, history_days_requested=history_days_requested, now=moment).daily_closes)
        if btc_pair
        else []
    )
    eth_returns = (
        scoring.log_returns(provider.historical_stats(eth_pair, history_days_requested=history_days_requested, now=moment).daily_closes)
        if eth_pair
        else []
    )

    candidates: list[AssetCandidate] = []
    for exchange_pair in cheap_survivors:
        instrument = next(inst for inst in discovered if inst.exchange_pair == exchange_pair)
        snapshot = snapshots[exchange_pair]
        stats = provider.historical_stats(exchange_pair, history_days_requested=history_days_requested, now=moment)

        notional = scoring.notional_volume_usd(snapshot.last_price, snapshot.volume_24h)
        spread = scoring.spread_bps(snapshot.bid, snapshot.ask)
        vol = scoring.volatility(stats.daily_closes)
        price_z = scoring.zscore(stats.daily_closes[:-1], stats.daily_closes[-1]) if len(stats.daily_closes) >= 3 else None
        volume_z = scoring.zscore(stats.daily_volumes[:-1], stats.daily_volumes[-1]) if len(stats.daily_volumes) >= 3 else None
        op_risk = scoring.operational_risk_score(
            status=instrument.status,
            listing_age_days=stats.listing_age_days,
            spread_bps_value=spread,
        )

        full_input = CandidateInput(
            asset=exchange_pair,
            notional_volume_24h_usd=float(notional),
            spread_bps=spread,
            history_days_available=stats.history_days_available,
            price_zscore=price_z,
            volume_zscore=volume_z,
            status=instrument.status,
            operational_risk_score=op_risk,
        )
        filter_results = evaluate_all(filter_rules, full_input)
        if not all_passed(filter_results):
            rejected.append(
                RejectedCandidate(
                    asset=exchange_pair,
                    exchange=exchange,
                    evaluated_at=moment,
                    filter_results=filter_results,
                )
            )
            continue

        liquidity = scoring.liquidity_score(notional)
        spread_sc = scoring.spread_score(spread)
        dq = scoring.data_quality_score(stats.history_days_available, history_days_requested)
        risk = scoring.risk_score(operational_risk=op_risk, volatility_value=vol)
        opportunity = scoring.opportunity_score(liquidity=liquidity, spread=spread_sc, data_quality=dq)
        confidence = scoring.confidence_score(data_quality=dq, operational_risk=op_risk)
        correlation_btc = scoring.correlation(scoring.log_returns(stats.daily_closes), btc_returns) if exchange_pair != btc_pair else 1.0
        correlation_eth = scoring.correlation(scoring.log_returns(stats.daily_closes), eth_returns) if exchange_pair != eth_pair else 1.0

        missing_data = []
        if correlation_btc is None:
            missing_data.append("correlation_btc")
        if correlation_eth is None:
            missing_data.append("correlation_eth")
        missing_data.append("news_sentiment")
        missing_data.append("catalyst_score")

        candidates.append(
            AssetCandidate(
                asset=exchange_pair,
                asset_class="crypto",
                exchange=exchange,
                timestamp=moment,
                research_horizon=research_horizon,
                candidate_status="research",
                opportunity_score=opportunity,
                risk_score=risk,
                confidence_score=confidence,
                data_quality_score=dq,
                factors=CandidateFactors(
                    notional_volume_24h_usd=notional,
                    spread_bps=spread,
                    liquidity_score=liquidity,
                    spread_score=spread_sc,
                    volatility=vol,
                    data_quality_score=dq,
                    operational_risk_score=op_risk,
                    correlation_btc=correlation_btc,
                    correlation_eth=correlation_eth,
                    min_order_notional_usd=instrument.costmin,
                    listing_age_days=stats.listing_age_days,
                    exchange_status=instrument.status,
                ),
                missing_data=missing_data,
                sources=[
                    SourceRef(source_id="kraken_public_api", url="https://api.kraken.com/0/public", fetched_at=moment)
                ],
                expires_at=moment + expires_after,
            )
        )

    return DiscoveryRun(run_at=moment, exchange=exchange, candidates=candidates, rejected=rejected)
