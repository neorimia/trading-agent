"""HTTP replay cache: one execution per key under concurrent waiters."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from src.control.replay_cache import ReplayCache, run_idempotent


def test_run_idempotent_replays_success_for_waiters() -> None:
    cache = ReplayCache()
    calls = {"n": 0}

    def action() -> dict:
        calls["n"] += 1
        time.sleep(0.05)
        return {"ok": True, "n": calls["n"]}

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run_idempotent, cache, "same", action)
        second = pool.submit(run_idempotent, cache, "same", action)
        bodies = {first.result()["n"], second.result()["n"]}
    assert calls["n"] == 1
    assert bodies == {1}


def test_run_idempotent_does_not_cache_failures() -> None:
    cache = ReplayCache()
    calls = {"n": 0}

    def boom() -> dict:
        calls["n"] += 1
        raise RuntimeError("nope")

    try:
        run_idempotent(cache, "k", boom)
    except RuntimeError:
        pass
    try:
        run_idempotent(cache, "k", boom)
    except RuntimeError:
        pass
    assert calls["n"] == 2
