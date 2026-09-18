"""Cache pe disc al propunerilor LLM, cheie = sha256(ProposalContext canonic).

Nu importă src.llm. Re-rulările de backtest citesc cache-ul și nu depind de
eșantionarea modelului.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from src.engine.proposal_types import ParsedProposal, ProposalContext, RejectedProposal


class ProposalClient(Protocol):
    def request_proposal(
        self,
        context: ProposalContext,
        timeout_s: float | None = None,
    ) -> ParsedProposal | RejectedProposal:
        ...


def context_cache_key(context: ProposalContext) -> str:
    payload = context.model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CachingLLMProposalClient:
    def __init__(
        self,
        cache_dir: str | Path,
        inner: ProposalClient | None = None,
        *,
        read_only: bool = False,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._inner = inner
        self._read_only = read_only
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def request_proposal(
        self,
        context: ProposalContext,
        timeout_s: float | None = None,
    ) -> ParsedProposal | RejectedProposal:
        key = context_cache_key(context)
        path = self._cache_dir / f"{key}.json"
        if path.is_file():
            return _load_cached(path)
        if self._read_only or self._inner is None:
            return RejectedProposal(
                reason="model_error",
                raw_output=f"proposal cache miss for {key}",
            )
        result = self._inner.request_proposal(context, timeout_s=timeout_s)
        _save_cached(path, result)
        return result


def _save_cached(path: Path, result: ParsedProposal | RejectedProposal) -> None:
    if isinstance(result, ParsedProposal):
        payload = {"kind": "parsed", "body": result.model_dump(mode="json")}
    else:
        payload = {"kind": "rejected", "body": result.model_dump(mode="json")}
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _load_cached(path: Path) -> ParsedProposal | RejectedProposal:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("kind") not in {"parsed", "rejected"}:
        return RejectedProposal(reason="schema_invalid", raw_output=path.read_text(encoding="utf-8"))
    body = raw.get("body")
    try:
        if raw["kind"] == "parsed":
            return ParsedProposal.model_validate(body)
        return RejectedProposal.model_validate(body)
    except ValidationError:
        return RejectedProposal(reason="schema_invalid", raw_output=json.dumps(raw))
