"""Validare hard paper_trading.yaml — dry_run obligatoriu."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.engine.paper_config import load_paper_trading_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def _valid() -> dict:
    return {
        "path": "B",
        "dry_run": True,
        "venue": "KRAKEN",
        "instrument": "ETHUSD",
        "timeframe": "1d",
        "starting_cash": "10000",
        "lookback_bars": 20,
        "fast_ema_period": 10,
        "slow_ema_period": 20,
        "approval_timeout_s": 3600,
        "stale_data_threshold_s": 172800,
        "heartbeat_threshold_s": 30,
        "session_count_target": 30,
    }


def test_real_paper_config_loads() -> None:
    config = load_paper_trading_config(REPO_ROOT / "config" / "paper_trading.yaml")
    assert config.path == "B"
    assert config.dry_run is True
    assert config.venue == "KRAKEN"
    assert config.session_count_target == 30


def test_dry_run_false_refused(tmp_path: Path) -> None:
    payload = _valid()
    payload["dry_run"] = False
    path = tmp_path / "paper.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="dry_run"):
        load_paper_trading_config(path)


def test_path_a_refused(tmp_path: Path) -> None:
    payload = _valid()
    payload["path"] = "A"
    path = tmp_path / "paper.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        load_paper_trading_config(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing"):
        load_paper_trading_config(tmp_path / "nope.yaml")
