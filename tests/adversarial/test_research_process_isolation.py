"""Verificare statică a izolării research <-> engine/risk/execution (design §1, §6 mirror).

Rulează la fiecare commit din Faza research înainte. Zero excepții.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.research import server as research_server

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

FORBIDDEN_FROM_RESEARCH = ("src.engine", "src.risk", "src.execution")
FORBIDDEN_FROM_RESEARCH_CLIENT = ("src.research",)


def _iter_py_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


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


def _forbidden_hits(imported: set[str], prefixes: tuple[str, ...]) -> list[str]:
    return [
        name
        for name in sorted(imported)
        if any(_matches_prefix(name, prefix) for prefix in prefixes)
    ]


def test_research_has_no_imports_from_engine_risk_execution() -> None:
    offenders: list[str] = []
    for path in _iter_py_files(SRC_ROOT / "research"):
        imported = _collect_imported_modules(path)
        hits = _forbidden_hits(imported, FORBIDDEN_FROM_RESEARCH)
        for hit in hits:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {hit}")
    assert offenders == []


def test_research_client_has_no_imports_from_research() -> None:
    """`src/engine/research_client.py` parlează doar HTTP — niciun import direct din src.research."""
    offenders: list[str] = []
    path = SRC_ROOT / "engine" / "research_client.py"
    imported = _collect_imported_modules(path)
    hits = _forbidden_hits(imported, FORBIDDEN_FROM_RESEARCH_CLIENT)
    for hit in hits:
        offenders.append(f"{path.relative_to(REPO_ROOT)} imports {hit}")
    assert offenders == []


def test_validate_bind_host_rejects_all_non_loopback_variants() -> None:
    for hostile_host in ("0.0.0.0", "::", "192.168.1.1", "example.com", ""):
        with pytest.raises(ValueError, match="loopback"):
            research_server.validate_bind_host(hostile_host)


def test_server_main_refuses_to_start_on_wildcard_host_from_env() -> None:
    """Adversarial: un `.env.research` atacat/corupt cu RESEARCH_SERVER_HOST=0.0.0.0 nu pornește serverul."""
    with (
        patch.dict(os.environ, {"RESEARCH_SERVER_HOST": "0.0.0.0"}, clear=False),
        patch.object(research_server, "_load_dotenv_research", lambda: None),
        patch.object(research_server.uvicorn, "run") as mock_run,
    ):
        with pytest.raises(ValueError, match="loopback"):
            research_server.main()
        mock_run.assert_not_called()
