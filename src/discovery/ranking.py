"""Combină scorurile unui `AssetCandidate` fără să le colapseze (§4.4).

`composite_rank` e doar pentru sortare/afișare — candidatul păstrează toate componentele.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.discovery.models import AssetCandidate
from src.discovery.scoring import composite_rank

DEFAULT_RANK_WEIGHTS = {
    "opportunity_score": 0.4,
    "data_quality_score": 0.3,
    "risk_score_inverted": 0.3,
}


@dataclass(frozen=True)
class RankedCandidate:
    candidate: AssetCandidate
    composite_rank: float


def rank_candidates(
    candidates: list[AssetCandidate],
    *,
    weights: dict[str, float] | None = None,
) -> list[RankedCandidate]:
    effective_weights = weights if weights is not None else DEFAULT_RANK_WEIGHTS
    ranked = [
        RankedCandidate(
            candidate=candidate,
            composite_rank=composite_rank(
                {
                    "opportunity_score": candidate.opportunity_score,
                    "data_quality_score": candidate.data_quality_score,
                    "risk_score_inverted": 1.0 - candidate.risk_score,
                },
                effective_weights,
            ),
        )
        for candidate in candidates
    ]
    ranked.sort(key=lambda item: item.composite_rank, reverse=True)
    return ranked
