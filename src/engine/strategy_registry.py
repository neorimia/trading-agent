"""Registry de strategii — validare strictă + instantanee imutabile de versiune.

Citește/scrie `config/strategies.yaml` (mutabil, oglindă a stării curente) și
`config/strategy_versions/<id>/v<N>.json` (imutabil — o schimbare de parametri creează
un fișier nou, niciodată o suprascriere). Nu importă `src.execution` sau `src.risk`
direct — doar construiește `StrategySpec` din parametri validați.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.engine.strategies.donchian_breakout import DonchianBreakoutParams, DonchianBreakoutSpec
from src.engine.strategies.ema_cross import EmaTrendFilterParams, EmaTrendFilterSpec
from src.engine.strategies.rsi_mean_reversion import RsiMeanReversionParams, RsiMeanReversionSpec
from src.engine.strategy_spec import StrategyParams, StrategySpec, StrategyStatus

_STRICT = ConfigDict(extra="forbid")

RULE_BASED_KINDS: dict[str, tuple[type[StrategyParams], Callable[..., StrategySpec]]] = {
    "ema_cross": (EmaTrendFilterParams, EmaTrendFilterSpec),
    "donchian_breakout": (DonchianBreakoutParams, DonchianBreakoutSpec),
    "rsi_mean_reversion": (RsiMeanReversionParams, RsiMeanReversionSpec),
}

# "llm" nu are un StrategySpec local — rulează prin clientul LLM existent
# (src/engine/strategy_llm_assisted.py), neschimbat de acest registry.
NON_SPEC_KINDS = frozenset({"llm"})
ALL_KINDS = frozenset(RULE_BASED_KINDS) | NON_SPEC_KINDS


class StrategyDefinition(BaseModel):
    """O intrare validată din config/strategies.yaml."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: str
    enabled: bool
    status: StrategyStatus = "experimental"
    version: int = Field(default=1, ge=1)
    hypothesis: str = ""
    supported_assets: list[str] = Field(default_factory=list)
    supported_timeframes: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def build_strategy_spec(definition: StrategyDefinition) -> StrategySpec:
    """Validează params strict prin schema kind-ului și construiește StrategySpec-ul."""
    return build_spec_from_kind_and_params(
        definition.kind,
        definition.params,
        id=definition.id,
        version=definition.version,
        status=definition.status,
        updated_at=definition.updated_at,
    )


def build_spec_from_kind_and_params(
    kind: str,
    params: dict[str, Any],
    *,
    id: str = "",
    version: int = 1,
    status: StrategyStatus = "experimental",
    updated_at: datetime | None = None,
) -> StrategySpec:
    if kind not in RULE_BASED_KINDS:
        if kind in NON_SPEC_KINDS:
            raise ValueError(f"kind {kind!r} has no local StrategySpec — it runs via the LLM client")
        raise ValueError(f"unknown strategy kind: {kind!r}")
    params_cls, spec_cls = RULE_BASED_KINDS[kind]
    try:
        parsed_params = params_cls.model_validate(params)
    except ValidationError as exc:
        raise ValueError(f"invalid params for strategy kind {kind!r}: {exc}") from exc
    return spec_cls(
        id=id,
        version=version,
        status=status,
        updated_at=updated_at or datetime.now(timezone.utc),
        params=parsed_params,
    )


def default_params_for_kind(kind: str) -> dict[str, Any]:
    if kind not in RULE_BASED_KINDS:
        return {}
    params_cls, _ = RULE_BASED_KINDS[kind]
    return json.loads(params_cls().model_dump_json())


def load_strategy_definitions(path: str | Path) -> list[StrategyDefinition]:
    strategies_path = Path(path)
    if not strategies_path.is_file():
        return []
    raw = yaml.safe_load(strategies_path.read_text(encoding="utf-8"))
    items = raw.get("strategies") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    definitions: list[StrategyDefinition] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            definitions.append(StrategyDefinition.model_validate(item))
        except ValidationError as exc:
            raise ValueError(f"config/strategies.yaml entry invalid: {exc}") from exc
    return definitions


def write_strategy_definitions(path: str | Path, definitions: list[StrategyDefinition]) -> None:
    payload = {
        "strategies": [
            json.loads(definition.model_dump_json(exclude_none=False)) for definition in definitions
        ]
    }
    strategies_path = Path(path)
    strategies_path.parent.mkdir(parents=True, exist_ok=True)
    strategies_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def version_snapshot_path(versions_dir: str | Path, strategy_id: str, version: int) -> Path:
    return Path(versions_dir) / strategy_id / f"v{version}.json"


def write_version_snapshot(
    versions_dir: str | Path,
    definition: StrategyDefinition,
    *,
    change_note: str,
) -> Path:
    """Instantaneu imutabil — respinge scrierea dacă versiunea există deja."""
    path = version_snapshot_path(versions_dir, definition.id, definition.version)
    if path.is_file():
        raise ValueError(f"version snapshot already exists, versions are immutable: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(definition.model_dump_json())
    payload["change_note"] = change_note
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def list_version_snapshots(versions_dir: str | Path, strategy_id: str) -> list[dict[str, Any]]:
    directory = Path(versions_dir) / strategy_id
    if not directory.is_dir():
        return []
    snapshots: list[dict[str, Any]] = []
    for file in sorted(directory.glob("v*.json")):
        try:
            snapshots.append(json.loads(file.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    snapshots.sort(key=lambda item: item.get("version", 0))
    return snapshots


def next_version(versions_dir: str | Path, strategy_id: str) -> int:
    existing = list_version_snapshots(versions_dir, strategy_id)
    if not existing:
        return 1
    return max(int(item.get("version", 0)) for item in existing) + 1
