"""Research persistence boundary and backend selection."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from src.db.config import require_database_url
from src.research.models import ResearchDocument
from src.research.store import MetadataStore


class ResearchRepository(Protocol):
    def close(self) -> None: ...

    def upsert(self, doc: ResearchDocument) -> bool: ...

    def find_by_content_hash(self, content_hash: str) -> ResearchDocument | None: ...

    def list_documents(
        self, *, instrument: str | None = None, limit: int = 50
    ) -> list[ResearchDocument]: ...

    def query_for_context(
        self, instrument: str, as_of: datetime, *, limit: int
    ) -> list[ResearchDocument]: ...

    def related_documents(self, doc_id: str) -> list[tuple[str, str]]: ...


def open_research_repository(
    *,
    backend: str,
    sqlite_path: str | Path,
    database_url: str | None,
) -> ResearchRepository:
    normalized = backend.strip().lower()
    if normalized == "sqlite":
        return MetadataStore(sqlite_path)
    if normalized == "postgres":
        from src.research.postgres_store import PostgresMetadataStore

        url = require_database_url(database_url, variable="RESEARCH_DATABASE_URL")
        return PostgresMetadataStore(url)
    raise ValueError("RESEARCH_STORE_BACKEND must be 'sqlite' or 'postgres'")
