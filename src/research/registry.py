"""Registry de surse — nicio sursă nu e utilizabilă fără tos_reviewed_at valid (Regula absolută 1)."""

from __future__ import annotations

from pathlib import Path

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
