"""Izolare control plane: fără src.llm, fără proxy /propose, bind loopback."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.control import server as control_server

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


def _iter_py_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _module_name_for(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT)
    return ".".join(relative.with_suffix("").parts)


def _collect_imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    file_module = _module_name_for(path)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                parent_parts = file_module.split(".")[: -node.level]
                if node.module:
                    parent_parts.extend(node.module.split("."))
                base = ".".join(parent_parts)
            else:
                base = node.module or ""
            if base:
                imported.add(base)
            for alias in node.names:
                if alias.name == "*":
                    continue
                imported.add(f"{base}.{alias.name}" if base else alias.name)
    return imported


def _matches_prefix(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def test_control_has_no_imports_from_llm() -> None:
    offenders: list[str] = []
    for path in _iter_py_files(SRC_ROOT / "control"):
        imported = _collect_imported_modules(path)
        hits = [
            name
            for name in sorted(imported)
            if _matches_prefix(name, "src.llm")
        ]
        for hit in hits:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {hit}")
    assert offenders == []


def test_llm_has_no_imports_from_control() -> None:
    offenders: list[str] = []
    for path in _iter_py_files(SRC_ROOT / "llm"):
        imported = _collect_imported_modules(path)
        hits = [
            name
            for name in sorted(imported)
            if _matches_prefix(name, "src.control")
        ]
        for hit in hits:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {hit}")
    assert offenders == []


def test_control_server_source_has_no_propose_route() -> None:
    text = (SRC_ROOT / "control" / "server.py").read_text(encoding="utf-8")
    assert '@app.post("/propose")' not in text
    assert "generate_proposal" not in text


def test_main_refuses_wildcard_host() -> None:
    with (
        patch.dict(os.environ, {"CONTROL_SERVER_HOST": "0.0.0.0"}, clear=False),
        patch.object(control_server, "_load_dotenv_control", lambda: None),
        patch.object(control_server.uvicorn, "run") as mock_run,
    ):
        with pytest.raises(ValueError, match="loopback"):
            control_server.main()
        mock_run.assert_not_called()
