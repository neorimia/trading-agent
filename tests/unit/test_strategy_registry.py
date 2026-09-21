"""Registry de strategii: validare, versionare imutabilă, construcție de spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.engine.strategy_registry import (
    StrategyDefinition,
    build_spec_from_kind_and_params,
    build_strategy_spec,
    default_params_for_kind,
    list_version_snapshots,
    load_strategy_definitions,
    next_version,
    write_strategy_definitions,
    write_version_snapshot,
)


def test_default_params_for_known_kinds() -> None:
    for kind in ("ema_cross", "donchian_breakout", "rsi_mean_reversion"):
        params = default_params_for_kind(kind)
        assert isinstance(params, dict)
        assert params


def test_default_params_empty_for_llm() -> None:
    assert default_params_for_kind("llm") == {}


def test_build_spec_from_kind_and_params_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown strategy kind"):
        build_spec_from_kind_and_params("not_a_kind", {})


def test_build_spec_from_kind_and_params_rejects_llm() -> None:
    with pytest.raises(ValueError, match="no local StrategySpec"):
        build_spec_from_kind_and_params("llm", {})


def test_build_spec_from_kind_and_params_rejects_invalid_params() -> None:
    with pytest.raises(ValueError, match="invalid params"):
        build_spec_from_kind_and_params("ema_cross", {"fast_ema_period": -1})


def test_build_strategy_spec_from_definition() -> None:
    definition = StrategyDefinition(
        id="ema_cross_test",
        name="EMA test",
        kind="ema_cross",
        enabled=True,
        params={"fast_ema_period": 5, "slow_ema_period": 15},
    )
    spec = build_strategy_spec(definition)
    assert spec.id == "ema_cross_test"
    assert spec.params.fast_ema_period == 5


def test_load_and_write_strategy_definitions_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "strategies.yaml"
    definitions = [
        StrategyDefinition(id="a", name="A", kind="ema_cross", enabled=True, params={}),
        StrategyDefinition(id="b", name="B", kind="llm", enabled=False, params={}),
    ]
    write_strategy_definitions(path, definitions)
    loaded = load_strategy_definitions(path)
    assert [d.id for d in loaded] == ["a", "b"]
    assert loaded[0].kind == "ema_cross"


def test_load_strategy_definitions_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_strategy_definitions(tmp_path / "missing.yaml") == []


def test_load_strategy_definitions_rejects_invalid_entry(tmp_path: Path) -> None:
    path = tmp_path / "strategies.yaml"
    path.write_text("strategies:\n  - id: a\n    name: A\n    kind: ema_cross\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_strategy_definitions(path)


def test_version_snapshot_is_immutable(tmp_path: Path) -> None:
    definition = StrategyDefinition(id="a", name="A", kind="ema_cross", enabled=True, version=1, params={})
    write_version_snapshot(tmp_path, definition, change_note="initial")
    with pytest.raises(ValueError, match="immutable"):
        write_version_snapshot(tmp_path, definition, change_note="again")


def test_next_version_increments(tmp_path: Path) -> None:
    assert next_version(tmp_path, "a") == 1
    definition = StrategyDefinition(id="a", name="A", kind="ema_cross", enabled=True, version=1, params={})
    write_version_snapshot(tmp_path, definition, change_note="v1")
    assert next_version(tmp_path, "a") == 2


def test_list_version_snapshots_sorted(tmp_path: Path) -> None:
    for version in (1, 2, 3):
        definition = StrategyDefinition(
            id="a", name="A", kind="ema_cross", enabled=True, version=version, params={}
        )
        write_version_snapshot(tmp_path, definition, change_note=f"v{version}")
    snapshots = list_version_snapshots(tmp_path, "a")
    assert [s["version"] for s in snapshots] == [1, 2, 3]
