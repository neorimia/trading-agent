"""Validare hard a config/risk_limits.yaml — fără fallback la valori implicite."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from src.risk.config_schema import load_risk_limits

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_LIMITS = REPO_ROOT / "config" / "risk_limits.yaml"


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _valid_payload() -> dict:
    return {
        "max_notional_per_order": 1000,
        "max_exposure_per_instrument": 2000,
        "max_exposure_per_asset_class": 5000,
        "max_daily_loss": 200,
        "max_drawdown": 500,
        "max_orders_per_day": 10,
        "circuit_breaker": {
            "max_consecutive_errors": 3,
            "max_consecutive_losses": 3,
            "halt_on_unknown_order_result": True,
        },
    }


def test_real_risk_limits_file_loads() -> None:
    limits = load_risk_limits(REAL_LIMITS)
    assert limits.max_notional_per_order == Decimal("1000")
    assert limits.max_orders_per_day == 10
    assert limits.circuit_breaker.halt_on_unknown_order_result is True


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing"):
        load_risk_limits(tmp_path / "does-not-exist.yaml")


def test_missing_field_raises(tmp_path: Path) -> None:
    payload = _valid_payload()
    del payload["max_drawdown"]
    path = _write_yaml(tmp_path / "limits.yaml", payload)
    with pytest.raises(ValueError, match="invalid"):
        load_risk_limits(path)


def test_negative_limit_raises(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["max_daily_loss"] = -1
    path = _write_yaml(tmp_path / "limits.yaml", payload)
    with pytest.raises(ValueError, match="invalid"):
        load_risk_limits(path)


def test_zero_orders_per_day_raises(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["max_orders_per_day"] = 0
    path = _write_yaml(tmp_path / "limits.yaml", payload)
    with pytest.raises(ValueError, match="invalid"):
        load_risk_limits(path)


def test_halt_on_unknown_false_raises(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["circuit_breaker"]["halt_on_unknown_order_result"] = False
    path = _write_yaml(tmp_path / "limits.yaml", payload)
    with pytest.raises(ValueError, match="halt_on_unknown_order_result"):
        load_risk_limits(path)


def test_empty_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        load_risk_limits(path)


def test_extra_field_is_rejected(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["llm_override"] = 1
    path = _write_yaml(tmp_path / "limits.yaml", payload)
    with pytest.raises(ValueError, match="invalid"):
        load_risk_limits(path)
