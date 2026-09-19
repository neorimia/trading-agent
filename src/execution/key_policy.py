"""Politică de chei API pentru engine: paper forbids keys; live cere attestări.

LLM-ul nu importă acest modul. Cheile trăiesc doar în procesul engine.
Retragerea fondurilor e interzisă prin attestare explicită — Kraken nu expune
permisiunile cheii prin API public, deci operatorul trebuie să confirme.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict

_STRICT = ConfigDict(extra="forbid")

KRAKEN_TRADING_KEYS = (
    "KRAKEN_SPOT_API_KEY",
    "KRAKEN_SPOT_API_SECRET",
    "KRAKEN_FUTURES_API_KEY",
    "KRAKEN_FUTURES_API_SECRET",
    "KRAKEN_FUTURES_DEMO_API_KEY",
    "KRAKEN_FUTURES_DEMO_API_SECRET",
)

# Attestări operator — nu sunt secrete, dar trebuie setate explicit pentru live.
WITHDRAW_ENABLED_FLAG = "KRAKEN_KEY_WITHDRAW_ENABLED"
IP_WHITELIST_FLAG = "KRAKEN_IP_WHITELIST_CONFIGURED"
SUBACCOUNT_FLAG = "KRAKEN_SUBACCOUNT"
LIVE_TRADING_FLAG = "LIVE_TRADING_ENABLED"

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off", ""})


class LiveKeyPolicy(BaseModel):
    model_config = _STRICT

    venue: Literal["KRAKEN"] = "KRAKEN"
    subaccount: bool
    ip_whitelist_configured: bool
    withdraw_enabled: bool
    has_spot_key: bool
    has_spot_secret: bool


def _flag(environ: dict[str, str], name: str) -> bool:
    raw = environ.get(name, "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    raise ValueError(f"{name} must be true or false, got {environ.get(name)!r}")


_BROKER_SECRET_KEYS = ("BROKER_API_KEY", "BROKER_API_SECRET")
_SPOT_KEYS = ("KRAKEN_SPOT_API_KEY", "KRAKEN_SPOT_API_SECRET")


def present_kraken_keys(environ: dict[str, str] | None = None) -> list[str]:
    env = environ if environ is not None else os.environ
    return [key for key in KRAKEN_TRADING_KEYS if env.get(key)]


def paper_child_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """Copy environ for a paper subprocess, without exchange trading secrets."""
    env = dict(os.environ if source is None else source)
    for key in KRAKEN_TRADING_KEYS:
        env.pop(key, None)
    for key in _BROKER_SECRET_KEYS:
        env.pop(key, None)
    return env


def withdraw_enabled(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return env.get(WITHDRAW_ENABLED_FLAG, "false").strip().lower() in _TRUTHY


def has_spot_keys(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return bool(env.get("KRAKEN_SPOT_API_KEY") and env.get("KRAKEN_SPOT_API_SECRET"))


def monitor_child_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """Keep Kraken spot keys for Balance/OpenOrders. Drop futures keys. Live flag off."""
    env = dict(os.environ if source is None else source)
    for key in KRAKEN_TRADING_KEYS:
        if key not in _SPOT_KEYS:
            env.pop(key, None)
    env[LIVE_TRADING_FLAG] = "false"
    return env


def assert_no_kraken_trading_keys(environ: dict[str, str] | None = None) -> None:
    """Paper / dry_run: zero chei Kraken în mediu."""
    present = present_kraken_keys(environ)
    if present:
        raise RuntimeError(
            "Path B dry_run forbids Kraken API keys in the environment: "
            + ", ".join(present)
        )


def load_live_key_policy(environ: dict[str, str] | None = None) -> LiveKeyPolicy:
    env = environ if environ is not None else os.environ
    return LiveKeyPolicy(
        subaccount=_flag(env, SUBACCOUNT_FLAG),
        ip_whitelist_configured=_flag(env, IP_WHITELIST_FLAG),
        withdraw_enabled=_flag(env, WITHDRAW_ENABLED_FLAG),
        has_spot_key=bool(env.get("KRAKEN_SPOT_API_KEY")),
        has_spot_secret=bool(env.get("KRAKEN_SPOT_API_SECRET")),
    )


def assert_live_key_policy(environ: dict[str, str] | None = None) -> LiveKeyPolicy:
    """Gate de startup pentru live: subcont, IP whitelist, fără withdraw, chei spot."""
    env = environ if environ is not None else os.environ
    if env.get(LIVE_TRADING_FLAG, "").strip().lower() not in _TRUTHY:
        raise RuntimeError(
            "live trading requires LIVE_TRADING_ENABLED=true after paper tests pass"
        )
    policy = load_live_key_policy(env)
    errors: list[str] = []
    if not policy.has_spot_key or not policy.has_spot_secret:
        errors.append("KRAKEN_SPOT_API_KEY and KRAKEN_SPOT_API_SECRET are required")
    if not policy.subaccount:
        errors.append("KRAKEN_SUBACCOUNT must be true (dedicated subaccount, limited funds)")
    if not policy.ip_whitelist_configured:
        errors.append("KRAKEN_IP_WHITELIST_CONFIGURED must be true (set in Kraken UI)")
    if policy.withdraw_enabled:
        errors.append("KRAKEN_KEY_WITHDRAW_ENABLED must be false (Withdraw Funds forbidden)")
    extra = [
        key
        for key in KRAKEN_TRADING_KEYS
        if key not in {"KRAKEN_SPOT_API_KEY", "KRAKEN_SPOT_API_SECRET"} and env.get(key)
    ]
    if extra:
        errors.append("non-spot Kraken keys are forbidden: " + ", ".join(extra))
    if errors:
        raise RuntimeError("live key policy rejected: " + "; ".join(errors))
    return policy


def redact_secrets(text: str, environ: dict[str, str] | None = None) -> str:
    """Șterge valorile cheilor din mesaje de log. Nu loga niciodată secretul brut."""
    env = environ if environ is not None else os.environ
    redacted = text
    for key in KRAKEN_TRADING_KEYS:
        value = env.get(key)
        if value:
            redacted = redacted.replace(value, f"[{key}_REDACTED]")
    for key in ("BROKER_API_KEY", "BROKER_API_SECRET"):
        value = env.get(key)
        if value:
            redacted = redacted.replace(value, f"[{key}_REDACTED]")
    return redacted
