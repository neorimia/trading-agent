"""Registry de surse — prezența în YAML nu activează ingestia (Regula absolută 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import yaml
from pydantic import ValidationError

from src.research.models import SourceConfig


def load_source_registry(path: str | Path) -> list[SourceConfig]:
    """Încarcă și validează config/research_sources.yaml. Lipsă/invalid → ValueError, fără fallback."""
    registry_path = Path(path)
    if not registry_path.is_file():
        raise ValueError(f"research_sources.yaml missing or not a file: {registry_path}")
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("sources"), list):
        raise ValueError("research_sources.yaml must contain a sources list")

    sources: list[SourceConfig] = []
    seen_ids: set[str] = set()
    for item in raw["sources"]:
        if not isinstance(item, dict):
            raise ValueError("each research source must be a mapping")
        try:
            source = SourceConfig.model_validate(item)
        except ValidationError as exc:
            raise ValueError(f"research_sources.yaml invalid: {exc}") from exc
        if source.source_id in seen_ids:
            raise ValueError(f"duplicate source_id: {source.source_id}")
        seen_ids.add(source.source_id)
        sources.append(source)
    return sources


def active_sources(sources: Sequence[SourceConfig]) -> list[SourceConfig]:
    """Doar surse cu ToS semnat și review_status reviewed / reviewed_with_dynamic_limit."""
    return [source for source in sources if source.is_fetchable()]


def require_fetchable(source: SourceConfig) -> None:
    """Fail loud înainte de HTTP. YAML ≠ permisiune de ingestie."""
    if not source.is_fetchable():
        raise ValueError(
            f"source {source.source_id!r} is not fetchable "
            f"(review_status={source.review_status!r}, tos_reviewed_at={source.tos_reviewed_at})"
        )
    if source.review_status == "reviewed_with_dynamic_limit" and source.min_request_interval_s is None:
        raise ValueError(
            f"source {source.source_id!r} reviewed_with_dynamic_limit requires min_request_interval_s"
        )
