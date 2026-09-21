"""Validated database configuration shared by service processes."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    min_pool_size: int = 1
    max_pool_size: int = 5
    timeout_s: float = 5.0

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"postgresql", "postgres"}:
            raise ValueError("database URL must use postgresql:// or postgres://")
        if not parsed.hostname:
            raise ValueError("database URL must include a hostname")
        if self.min_pool_size < 0:
            raise ValueError("min_pool_size must be non-negative")
        if self.max_pool_size < max(1, self.min_pool_size):
            raise ValueError("max_pool_size must be >= min_pool_size and at least 1")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")


def require_database_url(value: str | None, *, variable: str) -> str:
    url = (value or "").strip()
    if not url:
        raise ValueError(f"{variable} is required when the PostgreSQL backend is selected")
    DatabaseSettings(url=url)
    return url
