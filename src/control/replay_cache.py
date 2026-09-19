"""In-process HTTP idempotency: one execution per key, concurrent waiters replay."""

from __future__ import annotations

import threading
from collections.abc import Callable


class ReplayCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._done: dict[str, tuple[int, dict]] = {}
        self._inflight: dict[str, threading.Event] = {}

    def begin(self, key: str) -> dict | None:
        """Claim key, replay a stored success, or wait for an in-flight caller."""
        while True:
            with self._lock:
                cached = self._done.get(key)
                if cached is not None:
                    return {"status": cached[0], "body": cached[1], "replay": True}
                waiter = self._inflight.get(key)
                if waiter is None:
                    event = threading.Event()
                    self._inflight[key] = event
                    return None
            waiter.wait()

    def commit(self, key: str, status: int, body: dict) -> None:
        with self._lock:
            self._done[key] = (status, body)
            event = self._inflight.pop(key, None)
        if event is not None:
            event.set()

    def abort(self, key: str) -> None:
        with self._lock:
            event = self._inflight.pop(key, None)
        if event is not None:
            event.set()


def run_idempotent(cache: ReplayCache, key: str, action: Callable[[], dict]) -> dict:
    replay = cache.begin(key)
    if replay is not None:
        return replay["body"]
    try:
        body = action()
    except Exception:
        cache.abort(key)
        raise
    cache.commit(key, 200, body)
    return body
