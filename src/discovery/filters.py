"""Pipeline de eligibilitate configurabil (§3) — config/discovery_filters.yaml, nu hardcodat.

Un candidat respins nu dispare silențios: `FilterResult` se păstrează mereu, cu motiv,
mirror pe `RejectedProposal` din `src/engine/proposal_types.py`. Regulile ale căror date
de intrare nu sunt disponibile în Faza 1 (ex. `portfolio_limit` — cere `src.risk`, interzis
aici prin regula de izolare §1) raportează `passed=True` cu motiv explicit `not_evaluated_*`,
nu sunt omise tăcut din pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

from src.data.venue_registry import get_instrument
from src.discovery.models import FilterResult, InstrumentStatus


@dataclass(frozen=True)
class CandidateInput:
    """Toate valorile observate de care regulile de filtrare au nevoie pentru un instrument."""

    asset: str
    notional_volume_24h_usd: float
    spread_bps: float
    history_days_available: int
    price_zscore: float | None
    volume_zscore: float | None
    status: InstrumentStatus
    operational_risk_score: float
    portfolio_concentration_pct: float | None = None


@dataclass(frozen=True)
class FilterRuleConfig:
    rule_id: str
    kind: str
    params: dict[str, object]


class FilterRule(Protocol):
    def evaluate(self, candidate_input: CandidateInput) -> FilterResult: ...


def load_filter_config(path: str | Path) -> list[FilterRuleConfig]:
    config_path = Path(path)
    if not config_path.is_file():
        raise ValueError(f"discovery_filters.yaml missing or not a file: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("filters"), list):
        raise ValueError("discovery_filters.yaml must contain a filters list")
    rules: list[FilterRuleConfig] = []
    seen_ids: set[str] = set()
    for item in raw["filters"]:
        if not isinstance(item, dict) or "id" not in item or "kind" not in item:
            raise ValueError("each filter must have an id and a kind")
        rule_id = str(item["id"])
        if rule_id in seen_ids:
            raise ValueError(f"duplicate filter id: {rule_id}")
        seen_ids.add(rule_id)
        params = {k: v for k, v in item.items() if k not in ("id", "kind")}
        rules.append(FilterRuleConfig(rule_id=rule_id, kind=str(item["kind"]), params=params))
    return rules


def _min_notional_volume_24h(rule: FilterRuleConfig, candidate: CandidateInput) -> FilterResult:
    threshold = float(rule.params["threshold_usd"])
    passed = candidate.notional_volume_24h_usd >= threshold
    return FilterResult(
        rule_id=rule.rule_id,
        passed=passed,
        reason=f"notional_volume_24h_usd={candidate.notional_volume_24h_usd:.2f} vs threshold={threshold}",
        observed_value=f"{candidate.notional_volume_24h_usd:.2f}",
    )


def _max_spread_bps(rule: FilterRuleConfig, candidate: CandidateInput) -> FilterResult:
    threshold = float(rule.params["threshold_bps"])
    passed = candidate.spread_bps <= threshold
    return FilterResult(
        rule_id=rule.rule_id,
        passed=passed,
        reason=f"spread_bps={candidate.spread_bps:.2f} vs threshold={threshold}",
        observed_value=f"{candidate.spread_bps:.2f}",
    )


def _min_history_days(rule: FilterRuleConfig, candidate: CandidateInput) -> FilterResult:
    threshold = int(rule.params["threshold_days"])
    passed = candidate.history_days_available >= threshold
    return FilterResult(
        rule_id=rule.rule_id,
        passed=passed,
        reason=f"history_days_available={candidate.history_days_available} vs threshold={threshold}",
        observed_value=str(candidate.history_days_available),
    )


def _max_price_zscore(rule: FilterRuleConfig, candidate: CandidateInput) -> FilterResult:
    if candidate.price_zscore is None:
        return FilterResult(
            rule_id=rule.rule_id,
            passed=True,
            reason="not_evaluated_insufficient_history",
        )
    threshold = float(rule.params["threshold"])
    passed = abs(candidate.price_zscore) <= threshold
    return FilterResult(
        rule_id=rule.rule_id,
        passed=passed,
        reason=f"price_zscore={candidate.price_zscore:.2f} vs threshold={threshold}",
        observed_value=f"{candidate.price_zscore:.2f}",
    )


def _max_volume_zscore(rule: FilterRuleConfig, candidate: CandidateInput) -> FilterResult:
    if candidate.volume_zscore is None:
        return FilterResult(
            rule_id=rule.rule_id,
            passed=True,
            reason="not_evaluated_insufficient_history",
        )
    threshold = float(rule.params["threshold"])
    passed = abs(candidate.volume_zscore) <= threshold
    return FilterResult(
        rule_id=rule.rule_id,
        passed=passed,
        reason=f"volume_zscore={candidate.volume_zscore:.2f} vs threshold={threshold}",
        observed_value=f"{candidate.volume_zscore:.2f}",
    )


def _status_in(rule: FilterRuleConfig, candidate: CandidateInput) -> FilterResult:
    allowed = set(rule.params["allowed"])  # type: ignore[arg-type]
    passed = candidate.status in allowed
    return FilterResult(
        rule_id=rule.rule_id,
        passed=passed,
        reason=f"status={candidate.status!r} vs allowed={sorted(allowed)}",
        observed_value=candidate.status,
    )


def _max_operational_risk_score(rule: FilterRuleConfig, candidate: CandidateInput) -> FilterResult:
    threshold = float(rule.params["threshold"])
    passed = candidate.operational_risk_score <= threshold
    return FilterResult(
        rule_id=rule.rule_id,
        passed=passed,
        reason=f"operational_risk_score={candidate.operational_risk_score:.2f} vs threshold={threshold}",
        observed_value=f"{candidate.operational_risk_score:.2f}",
    )


def _max_portfolio_concentration_pct(rule: FilterRuleConfig, candidate: CandidateInput) -> FilterResult:
    if candidate.portfolio_concentration_pct is None:
        return FilterResult(
            rule_id=rule.rule_id,
            passed=True,
            reason="not_evaluated_portfolio_state_out_of_scope_faza1",
        )
    threshold = float(rule.params["threshold_pct"])
    passed = candidate.portfolio_concentration_pct <= threshold
    return FilterResult(
        rule_id=rule.rule_id,
        passed=passed,
        reason=f"portfolio_concentration_pct={candidate.portfolio_concentration_pct:.2f} vs threshold={threshold}",
        observed_value=f"{candidate.portfolio_concentration_pct:.2f}",
    )


def _has_execution_venue(rule: FilterRuleConfig, candidate: CandidateInput) -> FilterResult:
    spec = get_instrument(candidate.asset)
    passed = spec.execution_venue != "NONE"
    return FilterResult(
        rule_id=rule.rule_id,
        passed=passed,
        reason=f"execution_venue={spec.execution_venue!r}",
        observed_value=spec.execution_venue,
    )


_RULE_EVALUATORS = {
    "min_notional_volume_24h": _min_notional_volume_24h,
    "max_spread_bps": _max_spread_bps,
    "min_history_days": _min_history_days,
    "max_price_zscore": _max_price_zscore,
    "max_volume_zscore": _max_volume_zscore,
    "status_in": _status_in,
    "max_operational_risk_score": _max_operational_risk_score,
    "max_portfolio_concentration_pct": _max_portfolio_concentration_pct,
    "has_execution_venue": _has_execution_venue,
}


def evaluate_all(rules: list[FilterRuleConfig], candidate: CandidateInput) -> list[FilterResult]:
    results: list[FilterResult] = []
    for rule in rules:
        evaluator = _RULE_EVALUATORS.get(rule.kind)
        if evaluator is None:
            raise ValueError(f"unknown filter kind: {rule.kind!r} (rule {rule.rule_id!r})")
        results.append(evaluator(rule, candidate))
    return results


def all_passed(results: list[FilterResult]) -> bool:
    return all(result.passed for result in results)
