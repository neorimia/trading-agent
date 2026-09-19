"""R3 — context builder determinist (design-research-financiar.md §6.4, research-crawling-financiar.md §8).

`build_external_context()` e o funcție pură: documente + as_of -> text. Niciun apel de rețea,
niciun LLM secundar — randare de template, nu generare liberă. Păstrează proprietatea deja
testată "external context is passed as untrusted data" din src/llm/service.py: acest string
ajunge neschimbat în ProposalContext.external_context.

Controale din research-crawling-financiar.md §8 mapate aici:
  1. citare sursă+URL obligatorie per item
  2. timestamp explicit (published_at / event_date / fetched_at, toate distincte)
  3. contradicții — ambele versiuni apar, cu eticheta "CONTRADICTING SOURCES:"
  4. confidence_score afișat, niciodată ascuns
  5. listă goală -> "No recent verified context available for {instrument}."
  6. staleness -> prefix "STALE CONTEXT — verify before use:"
  8. separare Facts:/Interpretation: per item
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

from src.research.models import ResearchDocument

DEFAULT_STALE_AFTER = timedelta(hours=24)
FRED_SOURCE_IDS = frozenset({"fred", "alfred"})
FRED_ATTRIBUTION_DISCLAIMER = (
    "This product uses the FRED® API but is not endorsed or certified by "
    "the Federal Reserve Bank of St. Louis."
)


def _require_utc(moment: datetime, field_name: str) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return moment.astimezone(timezone.utc)


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    return _require_utc(value, "timestamp").isoformat()


def _interpretation(doc: ResearchDocument) -> str:
    """Strat de analiză/semnal (§7: rezumat/analiză), separat explicit de Facts:."""
    parts: list[str] = []
    if doc.sentiment_score is not None:
        parts.append(f"sentiment={doc.sentiment_score:.2f}")
    if doc.impact_magnitude is not None:
        parts.append(f"impact_magnitude={doc.impact_magnitude}")
    if doc.impact_direction is not None:
        parts.append(f"impact_direction={doc.impact_direction}")
    if doc.summary:
        parts.append(f"summary={doc.summary}")
    return ", ".join(parts) if parts else "not yet analyzed"


def _render_document(index: int, doc: ResearchDocument, *, contradicts: list[str]) -> str:
    lines = [
        f"[{index}] source={doc.source_id} url={doc.url}",
        f"    published_at={_fmt_dt(doc.published_at)} | event_date={_fmt_dt(doc.event_date)}"
        f" | fetched_at={_fmt_dt(doc.fetched_at)}",
        f"    confidence_score={doc.confidence_score:.2f}",
        f"    Facts: {doc.extracted_text}",
        f"    Interpretation: {_interpretation(doc)}",
    ]
    if contradicts:
        lines.append(f"    CONTRADICTS: {', '.join(contradicts)}")
    return "\n".join(lines)


def build_external_context(
    instrument: str,
    as_of: datetime,
    documents: list[ResearchDocument],
    *,
    contradicting_pairs: Sequence[tuple[str, str]] = (),
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> str:
    """Randare determinist — aceleași `documents` + `as_of` (+ contradicting_pairs) → același string.

    `contradicting_pairs`: perechi (doc_id, doc_id) cu relation_type='contradicts' — caller
    (MetadataStore.related_documents, filtrat la 'contradicts') le trece explicit; funcția
    rămâne pură și nu interoghează DB direct.
    """
    as_of = _require_utc(as_of, "as_of")
    if not documents:
        return f"No recent verified context available for {instrument}."

    by_doc_id = {doc.doc_id: doc for doc in documents}
    contradicts_by_doc: dict[str, list[str]] = {}
    relevant_pairs: list[tuple[str, str]] = []
    for doc_id_a, doc_id_b in contradicting_pairs:
        if doc_id_a in by_doc_id and doc_id_b in by_doc_id:
            relevant_pairs.append((doc_id_a, doc_id_b))
            contradicts_by_doc.setdefault(doc_id_a, []).append(doc_id_b)
            contradicts_by_doc.setdefault(doc_id_b, []).append(doc_id_a)

    header = f"EXTERNAL CONTEXT for {instrument} as of {_fmt_dt(as_of)}:"
    blocks = [
        _render_document(i, doc, contradicts=contradicts_by_doc.get(doc.doc_id, []))
        for i, doc in enumerate(documents, start=1)
    ]
    sections = [header, "\n\n".join(blocks)]

    if relevant_pairs:
        contradiction_lines = ["CONTRADICTING SOURCES:"]
        for doc_id_a, doc_id_b in relevant_pairs:
            doc_a, doc_b = by_doc_id[doc_id_a], by_doc_id[doc_id_b]
            contradiction_lines.append(
                f"  [{doc_a.source_id}] {doc_a.url} vs [{doc_b.source_id}] {doc_b.url}"
            )
        sections.append("\n".join(contradiction_lines))

    max_verified = max(_require_utc(doc.last_verified_at, "last_verified_at") for doc in documents)
    if as_of - max_verified > stale_after:
        sections.insert(0, "STALE CONTEXT — verify before use:")

    if any(doc.source_id in FRED_SOURCE_IDS for doc in documents):
        sections.append(FRED_ATTRIBUTION_DISCLAIMER)

    return "\n\n".join(sections)
