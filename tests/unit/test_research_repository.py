from __future__ import annotations

from pathlib import Path

import pytest

from src.research.repository import open_research_repository
from src.research.store import MetadataStore


def test_sqlite_backend_opens_legacy_store(tmp_path: Path) -> None:
    store = open_research_repository(
        backend="sqlite",
        sqlite_path=tmp_path / "metadata.db",
        database_url=None,
    )
    try:
        assert isinstance(store, MetadataStore)
    finally:
        store.close()


def test_postgres_backend_requires_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="RESEARCH_DATABASE_URL"):
        open_research_repository(
            backend="postgres",
            sqlite_path=tmp_path / "unused.db",
            database_url=None,
        )


def test_unknown_backend_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="RESEARCH_STORE_BACKEND"):
        open_research_repository(
            backend="memory",
            sqlite_path=tmp_path / "unused.db",
            database_url=None,
        )
