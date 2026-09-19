"""Client HTTP către POST /analyze — zero import din src.llm.

Nu produce ordine. Deserializare locală în ParsedAnalysis / RejectedAnalysis.
"""

from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from src.engine.analysis_types import AnalysisContext, ParsedAnalysis, RejectedAnalysis


class LLMAnalysisClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 60.0,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._http_client = http_client
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=self._timeout_s)
        return self._http_client

    def request_analysis(
        self,
        context: AnalysisContext,
        timeout_s: float | None = None,
    ) -> ParsedAnalysis | RejectedAnalysis:
        timeout = timeout_s if timeout_s is not None else self._timeout_s
        url = f"{self._base_url}/analyze"
        payload = context.model_dump(mode="json")
        try:
            response = self._client().post(url, json=payload, timeout=timeout)
            response.raise_for_status()
        except httpx.TimeoutException:
            return RejectedAnalysis(reason="timeout", raw_output="")
        except httpx.HTTPError as exc:
            return RejectedAnalysis(reason="model_error", raw_output=str(exc))

        raw_text = response.text
        try:
            data = response.json()
        except json.JSONDecodeError:
            return RejectedAnalysis(reason="schema_invalid", raw_output=raw_text)

        if not isinstance(data, dict):
            return RejectedAnalysis(reason="schema_invalid", raw_output=raw_text)

        if "reason" in data:
            try:
                return RejectedAnalysis.model_validate(data)
            except ValidationError:
                return RejectedAnalysis(reason="schema_invalid", raw_output=raw_text)

        try:
            return ParsedAnalysis.model_validate(data)
        except ValidationError:
            return RejectedAnalysis(reason="schema_invalid", raw_output=raw_text)
