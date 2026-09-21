"""PostgreSQL implementation of the research repository."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.db.pool import get_database_pool
from src.research.models import ResearchDocument


class PostgresMetadataStore:
    def __init__(self, database_url: str) -> None:
        self._pool = get_database_pool(database_url)

    def close(self) -> None:
        """Pool lifetime belongs to the process, not an individual request."""

    def upsert(self, doc: ResearchDocument) -> bool:
        with self._pool.connection() as connection:
            with connection.transaction():
                inserted = connection.execute(
                    """
                    INSERT INTO research_documents (
                        doc_id, url, title, source_id, author, published_at, fetched_at,
                        event_date, category, extracted_text, content_hash,
                        raw_payload_ref, summary, sentiment_score, impact_magnitude,
                        impact_direction, confidence_score, data_quality_score,
                        last_verified_at
                    ) VALUES (
                        %(doc_id)s, %(url)s, %(title)s, %(source_id)s, %(author)s,
                        %(published_at)s, %(fetched_at)s, %(event_date)s, %(category)s,
                        %(extracted_text)s, %(content_hash)s, %(raw_payload_ref)s,
                        %(summary)s, %(sentiment_score)s, %(impact_magnitude)s,
                        %(impact_direction)s, %(confidence_score)s,
                        %(data_quality_score)s, %(last_verified_at)s
                    )
                    ON CONFLICT (content_hash) DO NOTHING
                    RETURNING doc_id
                    """,
                    self._document_params(doc),
                ).fetchone()
                canonical_id = (
                    inserted["doc_id"]
                    if inserted is not None
                    else connection.execute(
                        """
                        SELECT doc_id FROM research_documents
                        WHERE content_hash = %s
                        """,
                        (doc.content_hash,),
                    ).fetchone()["doc_id"]
                )
                is_canonical = canonical_id == doc.doc_id
                if is_canonical and inserted is None:
                    connection.execute(
                        """
                        UPDATE research_documents SET
                            url = %(url)s,
                            title = %(title)s,
                            source_id = %(source_id)s,
                            author = %(author)s,
                            published_at = %(published_at)s,
                            fetched_at = %(fetched_at)s,
                            event_date = %(event_date)s,
                            category = %(category)s,
                            extracted_text = %(extracted_text)s,
                            raw_payload_ref = %(raw_payload_ref)s,
                            summary = %(summary)s,
                            sentiment_score = %(sentiment_score)s,
                            impact_magnitude = %(impact_magnitude)s,
                            impact_direction = %(impact_direction)s,
                            confidence_score = %(confidence_score)s,
                            data_quality_score = %(data_quality_score)s,
                            last_verified_at = %(last_verified_at)s
                        WHERE doc_id = %(doc_id)s
                        """,
                        self._document_params(doc),
                    )

                connection.execute(
                    """
                    INSERT INTO research_document_occurrences (
                        occurrence_id, canonical_doc_id, url, source_id, fetched_at,
                        raw_payload_ref
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (occurrence_id) DO UPDATE SET
                        canonical_doc_id = EXCLUDED.canonical_doc_id,
                        url = EXCLUDED.url,
                        source_id = EXCLUDED.source_id,
                        fetched_at = EXCLUDED.fetched_at,
                        raw_payload_ref = EXCLUDED.raw_payload_ref
                    """,
                    (
                        doc.doc_id,
                        canonical_id,
                        doc.url,
                        doc.source_id,
                        doc.fetched_at,
                        doc.raw_payload_ref,
                    ),
                )
                if is_canonical:
                    self._replace_assets(connection, doc)
                return is_canonical

    def find_by_content_hash(self, content_hash: str) -> ResearchDocument | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_documents WHERE content_hash = %s",
                (content_hash,),
            ).fetchone()
            return self._row_to_document(connection, row) if row else None

    def list_documents(
        self, *, instrument: str | None = None, limit: int = 50
    ) -> list[ResearchDocument]:
        with self._pool.connection() as connection:
            if instrument:
                rows = connection.execute(
                    """
                    SELECT DISTINCT d.* FROM research_documents d
                    JOIN document_assets da ON da.doc_id = d.doc_id
                    JOIN instruments i ON i.instrument_id = da.instrument_id
                    WHERE i.canonical_symbol = %s
                    ORDER BY d.fetched_at DESC
                    LIMIT %s
                    """,
                    (instrument, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM research_documents
                    ORDER BY fetched_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            return [self._row_to_document(connection, row) for row in rows]

    def query_for_context(
        self, instrument: str, as_of: datetime, *, limit: int
    ) -> list[ResearchDocument]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT d.* FROM research_documents d
                JOIN document_assets da ON da.doc_id = d.doc_id
                JOIN instruments i ON i.instrument_id = da.instrument_id
                WHERE i.canonical_symbol = %s
                  AND d.fetched_at <= %s
                  AND (d.published_at IS NULL OR d.published_at <= %s)
                ORDER BY d.fetched_at DESC
                LIMIT %s
                """,
                (instrument, as_of, as_of, limit),
            ).fetchall()
            return [self._row_to_document(connection, row) for row in rows]

    def related_documents(self, doc_id: str) -> list[tuple[str, str]]:
        with self._pool.connection() as connection:
            relation_rows = connection.execute(
                """
                SELECT related_doc_id, relation_type
                FROM document_relations
                WHERE doc_id = %s
                ORDER BY related_doc_id, relation_type
                """,
                (doc_id,),
            ).fetchall()
            occurrence_rows = connection.execute(
                """
                SELECT occurrence_id AS related_doc_id, 'duplicate_of' AS relation_type
                FROM research_document_occurrences
                WHERE canonical_doc_id = %s AND occurrence_id <> canonical_doc_id
                ORDER BY occurrence_id
                """,
                (doc_id,),
            ).fetchall()
            return [
                (row["related_doc_id"], row["relation_type"])
                for row in [*relation_rows, *occurrence_rows]
            ]

    @staticmethod
    def _document_params(doc: ResearchDocument) -> dict[str, Any]:
        return {
            "doc_id": doc.doc_id,
            "url": doc.url,
            "title": doc.title,
            "source_id": doc.source_id,
            "author": doc.author,
            "published_at": doc.published_at,
            "fetched_at": doc.fetched_at,
            "event_date": doc.event_date,
            "category": doc.category,
            "extracted_text": doc.extracted_text,
            "content_hash": doc.content_hash,
            "raw_payload_ref": doc.raw_payload_ref,
            "summary": doc.summary,
            "sentiment_score": doc.sentiment_score,
            "impact_magnitude": doc.impact_magnitude,
            "impact_direction": doc.impact_direction,
            "confidence_score": Decimal(str(doc.confidence_score)),
            "data_quality_score": (
                Decimal(str(doc.data_quality_score))
                if doc.data_quality_score is not None
                else None
            ),
            "last_verified_at": doc.last_verified_at,
        }

    @staticmethod
    def _replace_assets(connection: Any, doc: ResearchDocument) -> None:
        connection.execute("DELETE FROM document_assets WHERE doc_id = %s", (doc.doc_id,))
        for symbol in doc.assets_mentioned:
            row = connection.execute(
                "SELECT instrument_id FROM instruments WHERE canonical_symbol = %s",
                (symbol,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown instrument symbol {symbol!r}")
            connection.execute(
                """
                INSERT INTO document_assets (doc_id, instrument_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (doc.doc_id, row["instrument_id"]),
            )

    @staticmethod
    def _row_to_document(connection: Any, row: dict[str, Any]) -> ResearchDocument:
        assets = connection.execute(
            """
            SELECT i.canonical_symbol
            FROM document_assets da
            JOIN instruments i ON i.instrument_id = da.instrument_id
            WHERE da.doc_id = %s
            ORDER BY i.canonical_symbol
            """,
            (row["doc_id"],),
        ).fetchall()
        return ResearchDocument(
            doc_id=row["doc_id"],
            url=row["url"],
            title=row["title"],
            source_id=row["source_id"],
            author=row["author"],
            published_at=row["published_at"],
            fetched_at=row["fetched_at"],
            event_date=row["event_date"],
            assets_mentioned=[asset["canonical_symbol"] for asset in assets],
            category=row["category"],
            extracted_text=row["extracted_text"],
            raw_payload_ref=row["raw_payload_ref"],
            summary=row["summary"],
            sentiment_score=row["sentiment_score"],
            impact_magnitude=row["impact_magnitude"],
            impact_direction=row["impact_direction"],
            confidence_score=row["confidence_score"],
            data_quality_score=row["data_quality_score"],
            last_verified_at=row["last_verified_at"],
            content_hash=row["content_hash"],
        )
