"""KillSwitch — stare externă pe fișier, apelabilă independent de restul aplicației."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.risk.kill_switch import KillSwitch


def test_trigger_creates_parent_dirs_and_file(tmp_path: Path) -> None:
    flag = tmp_path / "control" / "halt.flag"
    switch = KillSwitch(flag)
    assert switch.is_active() is False
    result = switch.trigger("manual halt")
    assert result.triggered is True
    assert result.reason == "manual halt"
    assert flag.is_file()
    assert switch.is_active() is True


def test_reset_clears_flag(tmp_path: Path) -> None:
    switch = KillSwitch(tmp_path / "halt.flag")
    switch.trigger("stop")
    switch.reset()
    assert switch.is_active() is False
    assert not (tmp_path / "halt.flag").exists()


def test_reset_when_inactive_is_noop(tmp_path: Path) -> None:
    switch = KillSwitch(tmp_path / "halt.flag")
    switch.reset()
    assert switch.is_active() is False


def test_trigger_is_idempotent(tmp_path: Path) -> None:
    switch = KillSwitch(tmp_path / "halt.flag")
    first = switch.trigger("first")
    second = switch.trigger("second")
    assert first.triggered is True
    assert second.triggered is True
    assert switch.is_active() is True
    assert second.reason == "second"


def test_empty_reason_rejected(tmp_path: Path) -> None:
    switch = KillSwitch(tmp_path / "halt.flag")
    with pytest.raises(ValueError, match="reason"):
        switch.trigger("   ")
    assert switch.is_active() is False
