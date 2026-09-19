"""Verificare statică a izolării discovery <-> risk/execution (design-asset-discovery-research.md §1).

Mirror pe tests/adversarial/test_research_process_isolation.py. `src.data` (venue_registry, pentru
`has_execution_venue`) rămâne permis — doar risk/execution sunt interzise.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

FORBIDDEN_FROM_DISCOVERY = ("src.risk", "src.execution")


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


def _forbidden_hits(imported: set[str], prefixes: tuple[str, ...]) -> list[str]:
    return [name for name in sorted(imported) if any(_matches_prefix(name, prefix) for prefix in prefixes)]


def test_discovery_has_no_imports_from_risk_or_execution() -> None:
    offenders: list[str] = []
    for path in _iter_py_files(SRC_ROOT / "discovery"):
        imported = _collect_imported_modules(path)
        hits = _forbidden_hits(imported, FORBIDDEN_FROM_DISCOVERY)
        for hit in hits:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {hit}")
    assert offenders == []


def test_discovery_scripts_have_no_imports_from_risk_or_execution() -> None:
    offenders: list[str] = []
    for path in _iter_py_files(REPO_ROOT / "scripts" / "discovery"):
        imported = _collect_imported_modules(path)
        hits = _forbidden_hits(imported, FORBIDDEN_FROM_DISCOVERY)
        for hit in hits:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {hit}")
    assert offenders == []
