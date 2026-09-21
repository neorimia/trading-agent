"""R2 — RawDocumentStore, MetadataStore, extracție+normalizare (design-research-financiar.md §5, §6.3).

RawDocumentStore: fișiere imutabile, cheie = raw_payload_ref (mirror src/data/cache.py MarketDataCache).
MetadataStore: SQLite peste schema §5. Deduplicare pe content_hash — al doilea document cu același
hash NU primește rând propriu în `documents` (constrângere UNIQUE), ci doar o relație `duplicate_of`
către primul; el nu dispare, rămâne vizibil prin document_relations (Risc R2, workflow §6).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import trafilatura

from src.research.models import DocumentCategory, RawDocument, ResearchDocument

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id           TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    kind                 TEXT NOT NULL CHECK (kind IN ('rss', 'api', 'html_crawler', 'browser_automation')),
    base_url             TEXT NOT NULL,
    credibility_score    REAL NOT NULL CHECK (credibility_score BETWEEN 0 AND 1),
    robots_txt_status    TEXT NOT NULL CHECK (robots_txt_status IN ('allowed', 'disallowed', 'not_applicable_api')),
    tos_reviewed_at      TEXT NOT NULL,
    active               INTEGER NOT NULL DEFAULT 1,
    rate_limit_per_min   INTEGER
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id               TEXT PRIMARY KEY,
    url                  TEXT NOT NULL,
    title                TEXT NOT NULL,
    source_id            TEXT NOT NULL,
    author               TEXT,
    published_at         TEXT,
    fetched_at           TEXT NOT NULL,
    event_date           TEXT,
    category             TEXT NOT NULL CHECK (category IN
                             ('news','earnings','filing','macro_indicator','market_analysis','sentiment','geopolitical',
                              'protocol_upgrade','token_unlock','governance','listing','onchain_alert','funding_regime','regulatory')),
    language             TEXT NOT NULL DEFAULT 'en',
    extracted_text        TEXT NOT NULL,
    raw_payload_ref      TEXT,
    summary              TEXT,
    sentiment_score      REAL,
    impact_magnitude     TEXT CHECK (impact_magnitude IN ('low','medium','high') OR impact_magnitude IS NULL),
    impact_direction     TEXT CHECK (impact_direction IN ('bullish','bearish','neutral','unclear') OR impact_direction IS NULL),
    confidence_score     REAL NOT NULL DEFAULT 0.0,
    data_quality_score   REAL CHECK (data_quality_score BETWEEN 0 AND 1 OR data_quality_score IS NULL),
    last_verified_at     TEXT NOT NULL,
    content_hash         TEXT NOT NULL,
    UNIQUE (content_hash)
);
CREATE INDEX IF NOT EXISTS idx_documents_fetched_at ON documents(fetched_at);
CREATE INDEX IF NOT EXISTS idx_documents_event_date ON documents(event_date);

CREATE TABLE IF NOT EXISTS document_assets (
    doc_id               TEXT NOT NULL,
    instrument           TEXT NOT NULL,
    PRIMARY KEY (doc_id, instrument)
);
CREATE INDEX IF NOT EXISTS idx_document_assets_instrument ON document_assets(instrument);

CREATE TABLE IF NOT EXISTS document_relations (
    doc_id               TEXT NOT NULL,
    related_doc_id        TEXT NOT NULL,
    relation_type        TEXT NOT NULL CHECK (relation_type IN
                             ('confirms','contradicts','duplicate_of','retracted_by','follow_up_of')),
    PRIMARY KEY (doc_id, related_doc_id, relation_type)
);

CREATE TABLE IF NOT EXISTS document_occurrences (
    occurrence_id       TEXT PRIMARY KEY,
    canonical_doc_id    TEXT NOT NULL,
    url                 TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    raw_payload_ref     TEXT
);
"""
# Notă: FK-urile din design §5 (REFERENCES documents(doc_id)) sunt declarative — nu activăm
# `PRAGMA foreign_keys`, la fel ca restul repo-ului. Documentele deduplicate au un doc_id
# valid (calculat, vezi compute_doc_id) chiar dacă nu primesc rând propriu în `documents`.


def compute_doc_id(url: str, fetched_at: datetime) -> str:
    """sha256(url|fetched_at) — identic cu _raw_payload_ref din connectors.py (design §5: doc_id = sha256(url+fetched_at))."""
    digest = hashlib.sha256()
    digest.update(url.encode("utf-8"))
    digest.update(b"|")
    digest.update(fetched_at.astimezone(timezone.utc).isoformat().encode("utf-8"))
    return digest.hexdigest()


def compute_content_hash(extracted_text: str) -> str:
    """Hash pe text normalizat (whitespace colapsat, lowercase), nu pe titlu — Risc R2 (workflow §6)."""
    normalized = re.sub(r"\s+", " ", extracted_text).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def extract_text(raw_payload: bytes, *, url: str) -> str:
    """Boilerplate removal (trafilatura) — HTML tratat strict ca date brute, niciodată ca instrucțiuni."""
    extracted = trafilatura.extract(
        raw_payload, url=url, include_comments=False, favor_precision=True
    )
    if not extracted or not extracted.strip():
        raise ValueError(f"could not extract content from {url!r}")
    return extracted.strip()


def find_mentioned_assets(text: str, known_instruments: Sequence[str]) -> list[str]:
    """Keyword match simplu, whole-word case-insensitive (MVP din research-crawling-financiar.md §9)."""
    return [
        symbol
        for symbol in known_instruments
        if re.search(rf"\b{re.escape(symbol)}\b", text, flags=re.IGNORECASE)
    ]


def normalize_document(
    raw: RawDocument,
    raw_payload: bytes,
    *,
    title: str,
    category: DocumentCategory,
    known_instruments: Sequence[str] = (),
    author: str | None = None,
    published_at: datetime | None = None,
    event_date: datetime | None = None,
) -> ResearchDocument:
    """Extracție + normalizare → ResearchDocument. `category` e furnizat de caller (nu inferat aici) —
    clasificarea automată completă rămâne scop R6, nu se aproximează silențios în R2."""
    text = extract_text(raw_payload, url=raw.url)
    return ResearchDocument(
        doc_id=compute_doc_id(raw.url, raw.fetched_at),
        url=raw.url,
        title=title,
        source_id=raw.source_id,
        author=author,
        published_at=published_at,
        fetched_at=raw.fetched_at,
        event_date=event_date,
        assets_mentioned=find_mentioned_assets(text, known_instruments),
        category=category,
        extracted_text=text,
        summary=None,
        sentiment_score=None,
        impact_magnitude=None,
        impact_direction=None,
        confidence_score=0.0,
        raw_payload_ref=raw.raw_payload_ref,
        data_quality_score=None,
        last_verified_at=raw.fetched_at,
        content_hash=compute_content_hash(text),
    )


class RawDocumentStore:
    """Fișiere imutabile, cheie = raw_payload_ref — mirror MarketDataCache (src/data/cache.py)."""

    def __init__(self, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir)

    def save(self, doc: RawDocument, payload: bytes) -> str:
        self._root_dir.mkdir(parents=True, exist_ok=True)
        path = self._root_dir / doc.raw_payload_ref
        if not path.is_file():
            path.write_bytes(payload)
        return doc.raw_payload_ref

    def load(self, raw_payload_ref: str) -> bytes:
        path = self._root_dir / raw_payload_ref
        if not path.is_file():
            raise ValueError(f"no raw payload for ref {raw_payload_ref!r}")
        return path.read_bytes()


def _dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _iso_to_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


_DOCUMENTS_REBUILD = """
CREATE TABLE documents (
    doc_id               TEXT PRIMARY KEY,
    url                  TEXT NOT NULL,
    title                TEXT NOT NULL,
    source_id            TEXT NOT NULL,
    author               TEXT,
    published_at         TEXT,
    fetched_at           TEXT NOT NULL,
    event_date           TEXT,
    category             TEXT NOT NULL CHECK (category IN
                             ('news','earnings','filing','macro_indicator','market_analysis','sentiment','geopolitical',
                              'protocol_upgrade','token_unlock','governance','listing','onchain_alert','funding_regime','regulatory')),
    language             TEXT NOT NULL DEFAULT 'en',
    extracted_text        TEXT NOT NULL,
    raw_payload_ref      TEXT,
    summary              TEXT,
    sentiment_score      REAL,
    impact_magnitude     TEXT CHECK (impact_magnitude IN ('low','medium','high') OR impact_magnitude IS NULL),
    impact_direction     TEXT CHECK (impact_direction IN ('bullish','bearish','neutral','unclear') OR impact_direction IS NULL),
    confidence_score     REAL NOT NULL DEFAULT 0.0,
    data_quality_score   REAL CHECK (data_quality_score BETWEEN 0 AND 1 OR data_quality_score IS NULL),
    last_verified_at     TEXT NOT NULL,
    content_hash         TEXT NOT NULL,
    UNIQUE (content_hash)
);
"""


def _migrate_document_categories(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents'"
    ).fetchone()
    if row is None or "protocol_upgrade" in (row[0] or ""):
        return
    connection.execute("ALTER TABLE documents RENAME TO documents_legacy")
    connection.executescript(_DOCUMENTS_REBUILD)
    connection.execute(
        """
        INSERT INTO documents (
            doc_id, url, title, source_id, author, published_at, fetched_at, event_date,
            category, language, extracted_text, summary, sentiment_score, impact_magnitude,
            impact_direction, confidence_score, last_verified_at, content_hash
        )
        SELECT
            doc_id, url, title, source_id, author, published_at, fetched_at, event_date,
            category, language, extracted_text, summary, sentiment_score, impact_magnitude,
            impact_direction, confidence_score, last_verified_at, content_hash
        FROM documents_legacy
        """
    )
    connection.execute("DROP TABLE documents_legacy")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_fetched_at ON documents(fetched_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_event_date ON documents(event_date)"
    )


def _migrate_research_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(documents)").fetchall()
    }
    if "raw_payload_ref" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN raw_payload_ref TEXT")
    if "data_quality_score" not in columns:
        connection.execute(
            "ALTER TABLE documents ADD COLUMN data_quality_score REAL "
            "CHECK (data_quality_score BETWEEN 0 AND 1 OR data_quality_score IS NULL)"
        )


class MetadataStore:
    """Wrapper SQLite peste schema design-research-financiar.md §5."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        _migrate_document_categories(self._conn)
        _migrate_research_columns(self._conn)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert(self, doc: ResearchDocument) -> bool:
        """True dacă rândul a fost scris în `documents`. False dacă doc.content_hash exista deja
        sub alt doc_id — caz în care se scrie doar o relație `duplicate_of`, fără al doilea rând."""
        existing = self.find_by_content_hash(doc.content_hash)
        if existing is not None and existing.doc_id != doc.doc_id:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO document_occurrences (
                    occurrence_id, canonical_doc_id, url, source_id, fetched_at, raw_payload_ref
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    doc.doc_id,
                    existing.doc_id,
                    doc.url,
                    doc.source_id,
                    _dt_to_iso(doc.fetched_at),
                    doc.raw_payload_ref,
                ),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO document_relations (doc_id, related_doc_id, relation_type) "
                "VALUES (?, ?, 'duplicate_of')",
                (existing.doc_id, doc.doc_id),
            )
            self._conn.commit()
            return False

        self._conn.execute(
            """
            INSERT OR REPLACE INTO documents (
                doc_id, url, title, source_id, author, published_at, fetched_at, event_date,
                category, extracted_text, raw_payload_ref, summary, sentiment_score,
                impact_magnitude, impact_direction, confidence_score, data_quality_score,
                last_verified_at, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc.doc_id,
                doc.url,
                doc.title,
                doc.source_id,
                doc.author,
                _dt_to_iso(doc.published_at),
                _dt_to_iso(doc.fetched_at),
                _dt_to_iso(doc.event_date),
                doc.category,
                doc.extracted_text,
                doc.raw_payload_ref,
                doc.summary,
                doc.sentiment_score,
                doc.impact_magnitude,
                doc.impact_direction,
                doc.confidence_score,
                doc.data_quality_score,
                _dt_to_iso(doc.last_verified_at),
                doc.content_hash,
            ),
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO document_occurrences (
                occurrence_id, canonical_doc_id, url, source_id, fetched_at, raw_payload_ref
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                doc.doc_id,
                doc.doc_id,
                doc.url,
                doc.source_id,
                _dt_to_iso(doc.fetched_at),
                doc.raw_payload_ref,
            ),
        )
        self._conn.execute("DELETE FROM document_assets WHERE doc_id = ?", (doc.doc_id,))
        self._conn.executemany(
            "INSERT INTO document_assets (doc_id, instrument) VALUES (?, ?)",
            [(doc.doc_id, symbol) for symbol in doc.assets_mentioned],
        )
        self._conn.commit()
        return True

    def find_by_content_hash(self, content_hash: str) -> ResearchDocument | None:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_document(row)

    def list_documents(
        self, *, instrument: str | None = None, limit: int = 50
    ) -> list[ResearchDocument]:
        """Listare pentru control plane — read-only, fără rețea."""
        if instrument:
            rows = self._conn.execute(
                """
                SELECT DISTINCT d.* FROM documents d
                JOIN document_assets a ON a.doc_id = d.doc_id
                WHERE a.instrument = ?
                ORDER BY d.fetched_at DESC
                LIMIT ?
                """,
                (instrument, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM documents ORDER BY fetched_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_document(row) for row in rows]

    def query_for_context(
        self, instrument: str, as_of: datetime, *, limit: int
    ) -> list[ResearchDocument]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT d.* FROM documents d
            JOIN document_assets a ON a.doc_id = d.doc_id
            WHERE a.instrument = ?
              AND d.fetched_at <= ?
              AND (d.published_at IS NULL OR d.published_at <= ?)
            ORDER BY d.fetched_at DESC
            LIMIT ?
            """,
            (instrument, _dt_to_iso(as_of), _dt_to_iso(as_of), limit),
        ).fetchall()
        return [self._row_to_document(row) for row in rows]

    def related_documents(self, doc_id: str) -> list[tuple[str, str]]:
        """(related_doc_id, relation_type) pentru un doc_id — folosit de teste de dedup/adversariale."""
        rows = self._conn.execute(
            "SELECT related_doc_id, relation_type FROM document_relations WHERE doc_id = ?",
            (doc_id,),
        ).fetchall()
        return [(row["related_doc_id"], row["relation_type"]) for row in rows]

    def _row_to_document(self, row: sqlite3.Row) -> ResearchDocument:
        assets = [
            asset_row["instrument"]
            for asset_row in self._conn.execute(
                "SELECT instrument FROM document_assets WHERE doc_id = ? ORDER BY instrument",
                (row["doc_id"],),
            ).fetchall()
        ]
        return ResearchDocument(
            doc_id=row["doc_id"],
            url=row["url"],
            title=row["title"],
            source_id=row["source_id"],
            author=row["author"],
            published_at=_iso_to_dt(row["published_at"]),
            fetched_at=_iso_to_dt(row["fetched_at"]),
            event_date=_iso_to_dt(row["event_date"]),
            assets_mentioned=assets,
            category=row["category"],
            extracted_text=row["extracted_text"],
            raw_payload_ref=row["raw_payload_ref"],
            summary=row["summary"],
            sentiment_score=row["sentiment_score"],
            impact_magnitude=row["impact_magnitude"],
            impact_direction=row["impact_direction"],
            confidence_score=row["confidence_score"],
            data_quality_score=row["data_quality_score"],
            last_verified_at=_iso_to_dt(row["last_verified_at"]),
            content_hash=row["content_hash"],
        )
