"""Politică de chei: paper fără chei; live fără withdraw, cu subcont și IP whitelist."""

from __future__ import annotations

import pytest

from src.execution.key_policy import (
    assert_live_key_policy,
    assert_no_kraken_trading_keys,
    redact_secrets,
)


def _live_ok() -> dict[str, str]:
    return {
        "LIVE_TRADING_ENABLED": "true",
        "KRAKEN_SPOT_API_KEY": "key",
        "KRAKEN_SPOT_API_SECRET": "c2VjcmV0",
        "KRAKEN_SUBACCOUNT": "true",
        "KRAKEN_IP_WHITELIST_CONFIGURED": "true",
        "KRAKEN_KEY_WITHDRAW_ENABLED": "false",
    }


def test_paper_rejects_spot_secret() -> None:
    with pytest.raises(RuntimeError, match="forbids Kraken API keys"):
        assert_no_kraken_trading_keys({"KRAKEN_SPOT_API_SECRET": "abc"})


def test_paper_allows_empty() -> None:
    assert_no_kraken_trading_keys({})
    assert_no_kraken_trading_keys({"KRAKEN_SPOT_API_KEY": ""})


def test_live_policy_accepts_minimal_safe_key() -> None:
    policy = assert_live_key_policy(_live_ok())
    assert policy.withdraw_enabled is False
    assert policy.subaccount is True
    assert policy.ip_whitelist_configured is True


def test_live_policy_rejects_withdraw_enabled() -> None:
    env = _live_ok()
    env["KRAKEN_KEY_WITHDRAW_ENABLED"] = "true"
    with pytest.raises(RuntimeError, match="Withdraw Funds forbidden"):
        assert_live_key_policy(env)


def test_live_policy_rejects_missing_whitelist_and_subaccount() -> None:
    env = _live_ok()
    env["KRAKEN_IP_WHITELIST_CONFIGURED"] = "false"
    env["KRAKEN_SUBACCOUNT"] = "false"
    with pytest.raises(RuntimeError, match="live key policy rejected"):
        assert_live_key_policy(env)


def test_live_policy_rejects_without_kill_switch_flag() -> None:
    env = _live_ok()
    del env["LIVE_TRADING_ENABLED"]
    with pytest.raises(RuntimeError, match="LIVE_TRADING_ENABLED"):
        assert_live_key_policy(env)


def test_live_policy_rejects_futures_keys() -> None:
    env = _live_ok()
    env["KRAKEN_FUTURES_API_KEY"] = "fx"
    with pytest.raises(RuntimeError, match="non-spot"):
        assert_live_key_policy(env)


def test_redact_secrets_strips_key_material() -> None:
    env = {"KRAKEN_SPOT_API_SECRET": "super-secret-value"}
    assert "super-secret-value" not in redact_secrets("err super-secret-value", env)
    assert "KRAKEN_SPOT_API_SECRET_REDACTED" in redact_secrets("err super-secret-value", env)
