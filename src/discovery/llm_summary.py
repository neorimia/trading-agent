"""LLM narrative layer pentru candidați de discovery (design §1, §4, §5 — Faza 2).

Reutilizează procesul LLM izolat existent (`src.engine.analysis_types.AnalysisContext`,
`src.engine.analysis_client.LLMAnalysisClient`, `POST /analyze`) în loc să dubleze
schema/guardrail-urile. Acest modul nu calculează niciun scor — consumă `CandidateFactors`
deja calculate de `scoring.py` ca `facts_bundle` read-only și adaugă doar text narativ.

Zero import din `src.risk`/`src.execution` (aceeași regulă de izolare ca la LLM/engine).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Protocol

from src.discovery.models import AssetCandidate, SourceRef
from src.engine.analysis_types import AnalysisContext, ParsedAnalysis, RejectedAnalysis

_FORBIDDEN_PHRASES = (
    "guaranteed",
    "guarantee",
    "certain to",
    "will definitely",
    "risk-free",
    "riskfree",
    "cannot lose",
    "can't lose",
    "sure thing",
    "sigur",
    "garantat",
    "garanteaza",
    "garantează",
    "va creste",
    "va crește",
    "va scadea",
    "va scădea",
)
FORBIDDEN_PATTERNS = tuple(
    re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE) for phrase in _FORBIDDEN_PHRASES
)


def contains_forbidden_language(text: str) -> str | None:
    """Returnează prima expresie interzisă găsită, sau `None` dacă textul e curat."""
    for pattern in FORBIDDEN_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


class RequestSummaryFn(Protocol):
    def __call__(self, context: AnalysisContext) -> ParsedAnalysis | RejectedAnalysis: ...


def build_context(candidate: AssetCandidate) -> AnalysisContext:
    return AnalysisContext(
        instrument=candidate.asset,
        as_of=candidate.timestamp,
        analysis_type="discovery",
        timeframe=candidate.research_horizon,
        facts_bundle=candidate.factors.model_dump(mode="json"),
        external_context=None,
    )


def _reject(candidate: AssetCandidate, reason: str) -> AssetCandidate:
    if reason in candidate.missing_data:
        return candidate
    return candidate.model_copy(update={"missing_data": [*candidate.missing_data, reason]})


def summarize_candidate(
    candidate: AssetCandidate,
    request_summary: Callable[[AnalysisContext], ParsedAnalysis | RejectedAnalysis] | RequestSummaryFn,
    *,
    now: datetime | None = None,
) -> AssetCandidate:
    """Apelează procesul LLM izolat și atașează narativul. Nu repară output invalid."""
    moment = now if now is not None else datetime.now(timezone.utc)
    context = build_context(candidate)
    result = request_summary(context)

    if isinstance(result, RejectedAnalysis):
        return _reject(candidate, f"llm_summary_rejected:{result.reason}")

    narrative_fields = (result.factual_summary, result.bullish_case, result.bearish_case, result.neutral_case)
    for text in narrative_fields:
        if contains_forbidden_language(text) is not None:
            return _reject(candidate, "llm_summary_rejected:forbidden_phrase")

    return candidate.model_copy(
        update={
            "bullish_case": [result.bullish_case],
            "bearish_case": [result.bearish_case],
            "neutral_case": [result.neutral_case],
            "invalidation_conditions": list(result.invalidation_conditions),
            "sources": [
                *candidate.sources,
                SourceRef(
                    source_id="llm_discovery_summary",
                    url="internal:llm/analyze",
                    fetched_at=moment,
                ),
            ],
        }
    )
