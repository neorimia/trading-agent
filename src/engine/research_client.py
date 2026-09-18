"""Client HTTP către procesul research — zero import din src.research.

Fail-open spre None la orice eroare de transport, status neașteptat sau JSON invalid —
indisponibilitatea research-ului nu oprește niciodată bucla `on_bar` (Regula absolută
research #4, design-research-financiar.md §4: "fail-open spre None, nu spre excepție").
"""

from __future__ import annotations

from datetime import datetime

import httpx


class ResearchClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 10.0,
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

    def get_context(
        self,
        instrument: str,
        as_of: datetime,
        *,
        max_documents: int = 5,
        timeout_s: float | None = None,
    ) -> str | None:
        timeout = timeout_s if timeout_s is not None else self._timeout_s
        url = f"{self._base_url}/context"
        params = {
            "instrument": instrument,
            "as_of": as_of.isoformat(),
            "max_documents": max_documents,
        }
        try:
            response = self._client().get(url, params=params, timeout=timeout)
        except httpx.HTTPError:
            return None

        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        context = data.get("external_context")
        if not isinstance(context, str):
            return None
        return context
