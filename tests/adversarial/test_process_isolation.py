"""Verificare statică a izolării engine ↔ llm (design §6).

Rulează la fiecare commit din Faza 2 înainte. Zero excepții, inclusiv schema.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

FORBIDDEN_FROM_LLM = ("src.risk", "src.execution", "src.engine")
BROKER_PACKAGES = ("ib_insync", "krakenex", "ccxt")
NAUTILUS_ADAPTERS_PREFIX = "nautilus_trader.adapters"
FORBIDDEN_FROM_ENGINE_SIDE = ("src.llm",)
SENSITIVE_TOKENS = ("BROKER", "API_KEY", "SECRET")


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
    hits = [
        name
        for name in sorted(imported)
        if any(_matches_prefix(name, prefix) for prefix in prefixes)
    ]
    return hits


def _env_keys(path: Path) -> list[str]:
    keys: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.append(key)
    return keys


def test_llm_has_no_imports_from_risk_execution_engine() -> None:
    """Pașii 1–2 din design §6."""
    offenders: list[str] = []
    for path in _iter_py_files(SRC_ROOT / "llm"):
        imported = _collect_imported_modules(path)
        hits = _forbidden_hits(imported, FORBIDDEN_FROM_LLM)
        for hit in hits:
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {hit}")
    assert offenders == []


def test_llm_has_no_known_broker_client_imports() -> None:
    """Pasul 3 din design §6."""
    offenders: list[str] = []
    for path in _iter_py_files(SRC_ROOT / "llm"):
        imported = _collect_imported_modules(path)
        for name in sorted(imported):
            if any(_matches_prefix(name, pkg) for pkg in BROKER_PACKAGES):
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports {name}")
            if _matches_prefix(name, NAUTILUS_ADAPTERS_PREFIX):
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports {name}")
    assert offenders == []


def test_engine_risk_execution_have_no_imports_from_llm() -> None:
    """Pașii 4–5 din design §6 — zero excepții, inclusiv src.llm.schema."""
    offenders: list[str] = []
    for folder in ("risk", "execution", "engine", "monitor", "audit"):
        for path in _iter_py_files(SRC_ROOT / folder):
            imported = _collect_imported_modules(path)
            hits = _forbidden_hits(imported, FORBIDDEN_FROM_ENGINE_SIDE)
            for hit in hits:
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports {hit}")
    assert offenders == []


def test_env_llm_example_has_no_engine_broker_keys() -> None:
    """Pasul 6 din design §6."""
    engine_keys = _env_keys(REPO_ROOT / ".env.engine.example")
    llm_keys = _env_keys(REPO_ROOT / ".env.llm.example")
    llm_text = (REPO_ROOT / ".env.llm.example").read_text(encoding="utf-8")

    sensitive_engine_keys = [
        key
        for key in engine_keys
        if any(token in key.upper() for token in SENSITIVE_TOKENS)
    ]
    assert sensitive_engine_keys, "expected broker keys in .env.engine.example"

    leaked = [key for key in sensitive_engine_keys if key in llm_keys or key in llm_text]
    llm_sensitive = [
        key for key in llm_keys if any(token in key.upper() for token in SENSITIVE_TOKENS)
    ]
    assert leaked == []
    assert llm_sensitive == []
