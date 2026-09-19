"""Normalizer Nivel 1: analizele nu devin niciodată ParsedProposal.

Nivelul 2 poate înlocui această funcție cu reguli deterministe (expiry, quality,
contradicții, confluență EMA). Până atunci întoarce mereu None.
"""

from __future__ import annotations

from src.engine.analysis_types import ParsedAnalysis
from src.engine.proposal_types import ParsedProposal


def normalize_analysis(_analysis: ParsedAnalysis) -> ParsedProposal | None:
    """Nivel 1 — research report only. Zero semnale, zero ordine."""
    return None
