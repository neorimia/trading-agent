"""Atomic and exclusive runtime file writes."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.runtime_io import write_text_atomic, write_text_exclusive


def test_write_text_atomic_replaces_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "last_bar.json"
    write_text_atomic(path, '{"a": 1}')
    write_text_atomic(path, '{"a": 2}')
    assert path.read_text(encoding="utf-8") == '{"a": 2}'
    leftovers = list(tmp_path.glob(".last_bar.json.*.tmp"))
    assert leftovers == []


def test_write_text_exclusive_second_writer_raises(tmp_path: Path) -> None:
    path = tmp_path / "cid.decision.json"
    write_text_exclusive(path, '{"approved": true}')
    with pytest.raises(FileExistsError):
        write_text_exclusive(path, '{"approved": false}')
    assert "true" in path.read_text(encoding="utf-8")
