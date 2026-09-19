"""Pipeline de filtrare — config-driven, rezultate mereu populate (design §3)."""

from __future__ import annotations

import pytest

from src.discovery.filters import (
    CandidateInput,
    FilterRuleConfig,
    all_passed,
    evaluate_all,
    load_filter_config,
)

REPO_ROOT_FILTERS = "config/discovery_filters.yaml"


def _base_input(**overrides: object) -> CandidateInput:
    defaults = dict(
        asset="ETHUSD",
        notional_volume_24h_usd=1_000_000.0,
        spread_bps=10.0,
        history_days_available=120,
        price_zscore=1.0,
        volume_zscore=1.0,
        status="online",
        operational_risk_score=0.1,
    )
    defaults.update(overrides)
    return CandidateInput(**defaults)


def test_load_filter_config_reads_default_yaml() -> None:
    rules = load_filter_config(REPO_ROOT_FILTERS)
    ids = {rule.rule_id for rule in rules}
    assert "min_liquidity" in ids
    assert "executable_venue" in ids


def test_load_filter_config_rejects_duplicate_ids(tmp_path) -> None:
    path = tmp_path / "filters.yaml"
    path.write_text(
        "filters:\n"
        "  - id: dup\n    kind: status_in\n    allowed: [online]\n"
        "  - id: dup\n    kind: status_in\n    allowed: [online]\n"
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_filter_config(path)


def test_min_notional_volume_24h_pass_and_fail() -> None:
    rule = FilterRuleConfig(rule_id="r", kind="min_notional_volume_24h", params={"threshold_usd": 500_000})
    passing = evaluate_all([rule], _base_input(notional_volume_24h_usd=600_000.0))
    failing = evaluate_all([rule], _base_input(notional_volume_24h_usd=100.0))
    assert all_passed(passing)
    assert not all_passed(failing)
    assert failing[0].reason and failing[0].observed_value is not None


def test_max_price_zscore_not_evaluated_when_none() -> None:
    rule = FilterRuleConfig(rule_id="r", kind="max_price_zscore", params={"threshold": 4.0})
    result = evaluate_all([rule], _base_input(price_zscore=None))[0]
    assert result.passed is True
    assert result.reason == "not_evaluated_insufficient_history"


def test_max_portfolio_concentration_not_evaluated_in_faza1() -> None:
    rule = FilterRuleConfig(rule_id="r", kind="max_portfolio_concentration_pct", params={"threshold_pct": 20})
    result = evaluate_all([rule], _base_input(portfolio_concentration_pct=None))[0]
    assert result.passed is True
    assert "not_evaluated" in result.reason


def test_status_in_rejects_non_tradable() -> None:
    rule = FilterRuleConfig(rule_id="r", kind="status_in", params={"allowed": ["online"]})
    result = evaluate_all([rule], _base_input(status="cancel_only"))[0]
    assert result.passed is False


def test_has_execution_venue_true_for_known_instrument() -> None:
    rule = FilterRuleConfig(rule_id="r", kind="has_execution_venue", params={})
    result = evaluate_all([rule], _base_input(asset="ETHUSD"))[0]
    assert result.passed is True


def test_has_execution_venue_false_for_unknown_instrument() -> None:
    rule = FilterRuleConfig(rule_id="r", kind="has_execution_venue", params={})
    result = evaluate_all([rule], _base_input(asset="SOMEUNKNOWNPAIR"))[0]
    assert result.passed is False


def test_unknown_filter_kind_raises() -> None:
    rule = FilterRuleConfig(rule_id="r", kind="not_a_real_kind", params={})
    with pytest.raises(ValueError, match="unknown filter kind"):
        evaluate_all([rule], _base_input())


def test_rejected_candidate_result_is_never_dropped_silently() -> None:
    """Toate regulile produc un FilterResult, indiferent de passed — nimic nu dispare tăcut."""
    rules = load_filter_config(REPO_ROOT_FILTERS)
    results = evaluate_all(rules, _base_input(notional_volume_24h_usd=1.0))
    assert len(results) == len(rules)
    assert not all_passed(results)
    assert all(result.reason for result in results)
