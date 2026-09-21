"""Start the local operator stack: PostgreSQL (when configured), LLM, research, control, console, then paper via API.

Does not source all .env files into the parent. Does not set LIVE_TRADING_ENABLED.
Paper and the broker monitor sidecar are started by POST /v1/agent/start, not by this process.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.db.pool import database_ready  # noqa: E402
from src.execution.key_policy import (  # noqa: E402
    KRAKEN_TRADING_KEYS,
    LIVE_TRADING_FLAG,
    _TRUTHY,
)
from src.llm.server import _ENGINE_BROKER_KEYS  # noqa: E402

LLM_URL = "http://127.0.0.1:8765"
RESEARCH_URL = "http://127.0.0.1:8766"
CONTROL_URL = "http://127.0.0.1:8767"
CONSOLE_URL = "http://127.0.0.1:4200"
OLLAMA_URL = "http://127.0.0.1:11434"

_REQUIRED_ENV_FILES = (".env.llm", ".env.control", ".env.engine")
_WAIT_TIMEOUT_S = 45.0
_DEFAULT_POSTGRES_URL = (
    "postgresql://research_writer:local-dev-only@127.0.0.1:5432/trading_research"
)


def isolated_service_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """Copy environ for LLM/research children: no broker keys, no live flag."""
    env = dict(os.environ if source is None else source)
    for key in _ENGINE_BROKER_KEYS:
        env.pop(key, None)
    for key in KRAKEN_TRADING_KEYS:
        env.pop(key, None)
    return env


def read_dotenv_value(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    prefix = f"{key}="
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or not line.startswith(prefix):
            continue
        value = line[len(prefix) :].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value
    return ""


def assert_port_free(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        if sock.connect_ex((host, port)) == 0:
            raise SystemExit(f"port {host}:{port} is already in use")


def wait_http(
    url: str,
    *,
    timeout_s: float = _WAIT_TIMEOUT_S,
    headers: dict[str, str] | None = None,
) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=1.5, headers=headers)
            if response.status_code < 500:
                return
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise SystemExit(f"timeout waiting for {url}: {last_error}")


def ping_optional(url: str) -> bool:
    try:
        response = httpx.get(url, timeout=1.5)
    except httpx.HTTPError:
        return False
    return response.status_code < 500


def _control_headers(root: Path, *, mutate: bool = False) -> dict[str, str]:
    headers: dict[str, str] = {}
    token = read_dotenv_value(root / ".env.control", "CONTROL_OPERATOR_TOKEN").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if mutate:
        headers["Idempotency-Key"] = str(uuid4())
    return headers


def _require_env_files(root: Path) -> None:
    missing = [name for name in _REQUIRED_ENV_FILES if not (root / name).is_file()]
    if missing:
        examples = ", ".join(f"cp {name}.example {name}" for name in missing)
        raise SystemExit(f"missing {', '.join(missing)}; run: {examples}")


def live_flag_enabled(root: Path, environ: dict[str, str] | None = None) -> bool:
    """Match control-plane dotenv: process env wins, else .env.engine."""
    env = os.environ if environ is None else environ
    if LIVE_TRADING_FLAG in env:
        raw = env[LIVE_TRADING_FLAG]
    else:
        raw = read_dotenv_value(root / ".env.engine", LIVE_TRADING_FLAG)
    return raw.strip().lower() in _TRUTHY


def assert_paper_start_allowed(root: Path, environ: dict[str, str] | None = None) -> None:
    if live_flag_enabled(root, environ):
        raise SystemExit(
            f"{LIVE_TRADING_FLAG} is true; paper start is blocked on purpose. "
            f"Set {LIVE_TRADING_FLAG}=false in .env.engine (live start is not available)."
        )


def postgres_backend_enabled(root: Path) -> bool:
    """True when research, control, or market data is configured to use PostgreSQL."""
    for env_name, key in (
        (".env.research", "RESEARCH_STORE_BACKEND"),
        (".env.control", "RESEARCH_STORE_BACKEND"),
        (".env.engine", "MARKET_DATA_STORE_BACKEND"),
    ):
        backend = read_dotenv_value(root / env_name, key).strip().lower()
        if backend == "postgres":
            return True
    return False


def postgres_database_urls(root: Path) -> list[str]:
    """Application-role URLs used to verify PostgreSQL readiness before HTTP services."""
    urls: list[str] = []
    for env_name, key in (
        (".env.research", "RESEARCH_DATABASE_URL"),
        (".env.control", "CONTROL_DATABASE_URL"),
        (".env.engine", "MARKET_DATA_DATABASE_URL"),
    ):
        value = read_dotenv_value(root / env_name, key).strip()
        if value and value not in urls:
            urls.append(value)
    if not urls and postgres_backend_enabled(root):
        urls.append(_DEFAULT_POSTGRES_URL)
    return urls


def postgres_any_ready(urls: list[str]) -> bool:
    return any(database_ready(url) for url in urls)


def _postgres_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def _wait_postgres(urls: list[str], *, timeout_s: float = _WAIT_TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if postgres_any_ready(urls):
            return
        time.sleep(0.5)
    raise SystemExit(
        "timeout waiting for PostgreSQL; check RESEARCH_DATABASE_URL / CONTROL_DATABASE_URL "
        "and that trading_research exists (see deploy/RUNBOOK.md §4)"
    )


def _brew_postgres_formula() -> str | None:
    brew = shutil.which("brew")
    if brew is None:
        return None
    for formula in ("postgresql@18", "postgresql@17", "postgresql@16", "postgresql"):
        completed = subprocess.run(
            [brew, "list", formula],
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            return formula
    return None


def _start_postgres_brew() -> bool:
    formula = _brew_postgres_formula()
    if formula is None:
        return False
    brew = shutil.which("brew")
    if brew is None:
        return False
    print(f"starting PostgreSQL via brew services ({formula})…")
    completed = subprocess.run(
        [brew, "services", "start", formula],
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _start_postgres_docker(root: Path) -> bool:
    docker = shutil.which("docker")
    compose_file = root / "compose.postgres.yml"
    if docker is None or not compose_file.is_file():
        return False
    if _postgres_port_open("127.0.0.1", 5432):
        return False
    print("starting PostgreSQL via docker compose (compose.postgres.yml)…")
    completed = subprocess.run(
        [
            docker,
            "compose",
            "-f",
            str(compose_file),
            "-p",
            "trading-agent",
            "up",
            "-d",
        ],
        cwd=str(root),
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def ensure_postgres(root: Path, *, timeout_s: float = _WAIT_TIMEOUT_S) -> None:
    """Start PostgreSQL when configured and wait until an application URL answers."""
    if not postgres_backend_enabled(root):
        return
    urls = postgres_database_urls(root)
    if not urls:
        raise SystemExit(
            "RESEARCH_STORE_BACKEND=postgres but no RESEARCH_DATABASE_URL or "
            "CONTROL_DATABASE_URL is set"
        )
    if postgres_any_ready(urls):
        host = urlsplit(urls[0]).hostname or "127.0.0.1"
        port = urlsplit(urls[0]).port or 5432
        print(f"postgres ready ({host}:{port})")
        return

    started = _start_postgres_brew()
    if not started:
        started = _start_postgres_docker(root)
    if not started and _postgres_port_open("127.0.0.1", 5432):
        raise SystemExit(
            "PostgreSQL port 127.0.0.1:5432 is in use but configured database URLs "
            "are not reachable; check credentials, database name, and role grants "
            "(deploy/postgres/create_roles.sql)"
        )
    if not started:
        raise SystemExit(
            "PostgreSQL is required (RESEARCH_STORE_BACKEND=postgres) but could not be "
            "started; install Homebrew postgresql@18 or run "
            "docker compose -f compose.postgres.yml up -d"
        )

    _wait_postgres(urls, timeout_s=timeout_s)
    host = urlsplit(urls[0]).hostname or "127.0.0.1"
    port = urlsplit(urls[0]).port or 5432
    print(f"postgres ready ({host}:{port})")


def _ensure_console_deps(root: Path) -> None:
    console = root / "apps" / "console"
    if (console / "node_modules").is_dir():
        return
    print("npm install (apps/console)…")
    completed = subprocess.run(
        ["npm", "install"],
        cwd=str(console),
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit("npm install failed")


def _spawn(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
) -> subprocess.Popen[bytes]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("ab")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print(f"{name} pid {process.pid} → {log_path}")
    return process


def _terminate(process: subprocess.Popen[bytes], name: str) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
        print(f"{name} killed after SIGTERM timeout")


def _stop_paper(root: Path) -> None:
    url = f"{CONTROL_URL}/v1/agent/stop"
    try:
        response = httpx.post(url, headers=_control_headers(root, mutate=True), timeout=10.0)
    except httpx.HTTPError as exc:
        print(f"agent/stop failed: {exc}")
        return
    if response.status_code >= 400:
        print(f"agent/stop HTTP {response.status_code}: {response.text[:200]}")
        return
    print("paper + monitor stop requested")


def _start_paper(root: Path) -> None:
    url = f"{CONTROL_URL}/v1/agent/start"
    response = httpx.post(url, headers=_control_headers(root, mutate=True), timeout=15.0)
    if response.status_code >= 400:
        hint = ""
        if response.status_code == 403 and "live start" in response.text:
            hint = (
                f" Set {LIVE_TRADING_FLAG}=false in .env.engine "
                "(live start is not available)."
            )
        raise SystemExit(
            f"agent/start HTTP {response.status_code}: {response.text[:300]}{hint}"
        )
    print(f"paper stream started: {response.text.strip()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start local trading-agent stack (dry-run)")
    parser.add_argument("--no-paper", action="store_true", help="do not POST /v1/agent/start")
    parser.add_argument("--no-console", action="store_true", help="skip Angular ng serve")
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="do not start or wait for PostgreSQL (assume it is already running)",
    )
    args = parser.parse_args(argv)

    root = REPO_ROOT
    os.chdir(root)
    _require_env_files(root)
    if not args.no_paper:
        assert_paper_start_allowed(root)

    if not ping_optional(OLLAMA_URL):
        print("warning: Ollama is not reachable at 127.0.0.1:11434; LLM proposals will fail")

    python = sys.executable
    logs = root / "runtime" / "logs"
    isolated = isolated_service_env()
    parent_env = dict(os.environ)

    children: list[tuple[str, subprocess.Popen[bytes]]] = []
    paper_started = False
    stopping = False

    def request_stop(*_args: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        if not args.no_db:
            ensure_postgres(root)

        assert_port_free("127.0.0.1", 8765)
        children.append(
            (
                "llm",
                _spawn(
                    "llm",
                    [python, "-m", "src.llm.server"],
                    cwd=root,
                    env=isolated,
                    log_path=logs / "llm.log",
                ),
            )
        )
        wait_http(LLM_URL)

        research_env = root / ".env.research"
        if research_env.is_file():
            assert_port_free("127.0.0.1", 8766)
            children.append(
                (
                    "research",
                    _spawn(
                        "research",
                        [python, "-m", "src.research.server"],
                        cwd=root,
                        env=isolated,
                        log_path=logs / "research.log",
                    ),
                )
            )
            research_ready_url = (
                f"{RESEARCH_URL}/ready"
                if postgres_backend_enabled(root)
                else RESEARCH_URL
            )
            wait_http(research_ready_url)
        else:
            print("warning: .env.research missing; research stays down")

        assert_port_free("127.0.0.1", 8767)
        children.append(
            (
                "control",
                _spawn(
                    "control",
                    [python, "-m", "src.control.server"],
                    cwd=root,
                    env=parent_env,
                    log_path=logs / "control.log",
                ),
            )
        )
        wait_http(f"{CONTROL_URL}/v1/health", headers=_control_headers(root))

        if not args.no_console:
            _ensure_console_deps(root)
            assert_port_free("127.0.0.1", 4200)
            children.append(
                (
                    "console",
                    _spawn(
                        "console",
                        ["npm", "start"],
                        cwd=root / "apps" / "console",
                        env=parent_env,
                        log_path=logs / "console.log",
                    ),
                )
            )
            wait_http(CONSOLE_URL, timeout_s=90.0)

        if not args.no_paper:
            _start_paper(root)
            paper_started = True

        print("stack ready")
        print(f"  console  {CONSOLE_URL}/")
        print(f"  control  {CONTROL_URL}/v1/health")
        print(f"  llm      {LLM_URL}")
        if research_env.is_file():
            print(f"  research {RESEARCH_URL}")
        if postgres_backend_enabled(root):
            print(f"  postgres {postgres_database_urls(root)[0]}")
        if paper_started:
            print("  paper    started via /v1/agent/start (ApprovalGate still required)")
        print("Ctrl-C stops paper/monitor then the HTTP processes")

        while not stopping:
            for name, process in children:
                code = process.poll()
                if code is not None:
                    raise SystemExit(f"{name} exited with code {code}")
            time.sleep(0.5)
    finally:
        if paper_started:
            _stop_paper(root)
        for name, process in reversed(children):
            _terminate(process, name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
