"""Persistență append-only pentru rulări de discovery — un fișier JSONL per zi (§5, §6).

Fiecare rulare scrie un rând per `AssetCandidate` (nu suprascrie ziua anterioară) — pattern
identic cu `src/data/cache.py`/`src/research/store.py`: reproductibil, niciodată mutat retroactiv.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.discovery.models import AssetCandidate, DiscoveryRun


def _daily_path(directory: Path, run_at: datetime) -> Path:
    day = run_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return directory / f"{day}.jsonl"


def append_run(run: DiscoveryRun, directory: str | Path) -> Path:
    """Adaugă fiecare candidat al rulării ca linie JSON separată. Nu scrie `rejected` (audit efemer)."""
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = _daily_path(target_dir, run.run_at)
    with path.open("a", encoding="utf-8") as handle:
        for candidate in run.candidates:
            handle.write(candidate.model_dump_json())
            handle.write("\n")
    return path


def load_day(directory: str | Path, day: str) -> list[AssetCandidate]:
    """`day` în format `YYYY-MM-DD`. Fișier lipsă → listă goală, nu eroare (poate fi o zi fără rulare)."""
    path = Path(directory) / f"{day}.jsonl"
    if not path.is_file():
        return []
    candidates: list[AssetCandidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        candidates.append(AssetCandidate.model_validate_json(line))
    return candidates
