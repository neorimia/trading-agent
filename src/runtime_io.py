"""Atomic / exclusive text writes for runtime files shared across processes."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4


def write_text_atomic(path: Path, text: str) -> None:
    """Write via a same-directory temp file then os.replace (atomic on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def write_text_exclusive(path: Path, text: str) -> None:
    """Create path only if it does not exist (O_EXCL). Raises FileExistsError."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
