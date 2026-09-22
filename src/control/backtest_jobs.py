"""Job asincron de backtest — coadă FIFO + worker thread, un job pe rând, fără Postgres.

Persistă status/rezultat ca JSON în `backtests/jobs/<run_id>.json` — auto-conținut, nu
depinde de procesul de control rămas în viață pentru a citi starea unui job. Worker-ul
apelează `run_backtest` existent (nicio cale de execuție nouă) și NU pornește nicio
conexiune de trading live: sursa de bare e `fetch_bars` (același adaptor public folosit
de restul control plane-ului pentru piață), niciodată exchange-ul live de execuție.

Timeout: best-effort. Firul de worker e unic (max_workers=1); dacă un job depășește
`timeout_s`, jobul e marcat `error` cu mesaj explicit, dar Python nu poate forța oprirea
unui thread care rulează cod arbitrar — dacă rularea internă chiar e blocată, jobul
următor va aștepta după ea. Documentat, nu ascuns.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal

from src.data.cache import canonical_dataset_hash
from src.data.sources import Bar
from src.engine.backtest_runner import run_backtest
from src.engine.backtest_store import compute_universe_sha256
from src.engine.cost_models import VenueCostConfig
from src.engine.strategy_registry import RULE_BASED_KINDS

if TYPE_CHECKING:
    from src.engine.backtest_store import PostgresBacktestStore

_LOG = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]

BacktestJobStatus = Literal["queued", "running", "done", "error"]
FetchBarsFn = Callable[[str, datetime, datetime, str], list[Bar]]

DEFAULT_JOB_TIMEOUT_S = 300.0
# kind-uri care NU pot rula prin acest job (au nevoie de infrastructură suplimentară,
# ex. un ProposalClient LLM cu cache — nu se potrivesc modelului sincron bars->semnal).
UNSUPPORTED_JOB_KINDS = frozenset({"llm"})


@dataclass
class BacktestJobRequest:
    strategy_id: str
    strategy_kind: str
    strategy_params: dict[str, Any]
    universe_symbol: str
    timeframe: str
    start: datetime
    end: datetime
    cost_multiplier: int = 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _job_path(jobs_dir: Path, run_id: str) -> Path:
    return jobs_dir / f"{run_id}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    tmp.replace(path)


class BacktestJobManager:
    """Un singur worker thread; job-urile sunt procesate strict secvențial (FIFO)."""

    def __init__(
        self,
        *,
        jobs_dir: Path,
        reports_dir: Path,
        halt_flag: Path,
        fetch_bars: FetchBarsFn,
        timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
        start_worker: bool = True,
        store: "PostgresBacktestStore | None" = None,
        universe_path: Path = REPO_ROOT / "config" / "universe.yaml",
    ) -> None:
        self._jobs_dir = jobs_dir
        self._reports_dir = reports_dir
        self._halt_flag = halt_flag
        self._fetch_bars = fetch_bars
        self._timeout_s = timeout_s
        # None = files-only (BACKTEST_STORE_BACKEND=files, the default/rollback
        # target) — JSON job/report writes below are unconditional either way.
        self._store = store
        self._universe_path = universe_path
        self._queue: queue.Queue[str] = queue.Queue()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backtest-run")
        self._worker: threading.Thread | None = None
        if start_worker:
            self._worker = threading.Thread(
                target=self._run_forever, name="backtest-job-queue", daemon=True
            )
            self._worker.start()

    def submit(self, request: BacktestJobRequest) -> str:
        if request.strategy_kind in UNSUPPORTED_JOB_KINDS:
            raise ValueError(
                f"strategy kind {request.strategy_kind!r} cannot run via the async backtest "
                "job (needs a dedicated proposal client) — run it via the local CLI/scripts"
            )
        if request.strategy_kind not in RULE_BASED_KINDS and request.strategy_kind != "baseline":
            raise ValueError(f"unknown strategy kind for backtest job: {request.strategy_kind!r}")
        if request.end <= request.start:
            raise ValueError("end must be after start")
        run_id = uuid.uuid4().hex
        record: dict[str, Any] = {
            "run_id": run_id,
            "strategy_id": request.strategy_id,
            "status": "queued",
            "created_at": _now().isoformat(),
            "started_at": None,
            "finished_at": None,
            "error": None,
            "request": {
                "strategy_kind": request.strategy_kind,
                "strategy_params": request.strategy_params,
                "universe_symbol": request.universe_symbol,
                "timeframe": request.timeframe,
                "start": request.start.isoformat(),
                "end": request.end.isoformat(),
                "cost_multiplier": request.cost_multiplier,
            },
            "metrics": None,
        }
        _write_json(_job_path(self._jobs_dir, run_id), record)
        self._queue.put(run_id)
        return run_id

    def get(self, run_id: str) -> dict[str, Any] | None:
        path = _job_path(self._jobs_dir, run_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def list_for_strategy(self, strategy_id: str) -> list[dict[str, Any]]:
        if not self._jobs_dir.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in self._jobs_dir.glob("*.json"):
            if path.suffix == ".tmp":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("strategy_id") == strategy_id:
                rows.append(data)
        rows.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return rows

    def process_one(self, timeout_s: float | None = None) -> str | None:
        """Consumă un job din coadă sincron — folosit de teste ca să nu depindă de thread
        timing. Returnează `run_id`-ul procesat sau `None` dacă coada era goală."""
        try:
            run_id = self._queue.get(timeout=timeout_s if timeout_s is not None else 0.01)
        except queue.Empty:
            return None
        self._process(run_id)
        return run_id

    def _run_forever(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                self._process(run_id)
            except Exception:  # noqa: BLE001 — worker-ul nu trebuie să moară niciodată
                _LOG.exception("backtest job %s crashed the worker loop", run_id)

    def _process(self, run_id: str) -> None:
        path = _job_path(self._jobs_dir, run_id)
        record = self.get(run_id)
        if record is None:
            return
        record["status"] = "running"
        record["started_at"] = _now().isoformat()
        _write_json(path, record)

        req = record["request"]
        try:
            future = self._executor.submit(
                self._execute, req, run_id, record["strategy_id"]
            )
            result = future.result(timeout=self._timeout_s)
            record["status"] = "done"
            record["metrics"] = result
        except FutureTimeoutError:
            record["status"] = "error"
            record["error"] = (
                f"timeout after {self._timeout_s}s (best-effort: the underlying run may "
                "still be executing on the worker thread)"
            )
        except Exception as exc:  # noqa: BLE001 — raportat în job, nu prăbușește worker-ul
            record["status"] = "error"
            record["error"] = str(exc)
        record["finished_at"] = _now().isoformat()
        _write_json(path, record)
        if record["status"] == "done":
            _write_json(
                self._reports_dir / f"{run_id}.json", {**record, "report_kind": "backtest_job"}
            )

    def _execute(self, req: dict[str, Any], run_id: str, strategy_id: str) -> dict[str, Any]:
        start = datetime.fromisoformat(req["start"])
        end = datetime.fromisoformat(req["end"])
        bars = self._fetch_bars(req["universe_symbol"], start, end, req["timeframe"])
        if not bars:
            raise ValueError("no bars returned for requested range — cannot backtest")
        dataset_hash = canonical_dataset_hash(bars)
        halt_flag = self._halt_flag.parent / f"backtest-job-{run_id}.flag"
        halt_flag.parent.mkdir(parents=True, exist_ok=True)

        # Postgres row created here, not in submit() — dataset_hash (NOT NULL) is
        # only known once bars are fetched (src/engine/backtest_store.py module
        # docstring "Deviation from the Phase 6 plan text"). None when the store is
        # disabled (files backend) or the strategy has no active strategy_version.
        backtest_run_id = None
        if self._store is not None:
            strategy_version_id = self._store.resolve_active_strategy_version_id(strategy_id)
            if strategy_version_id is not None:
                backtest_run_id = self._store.insert_run(
                    strategy_version_id=strategy_version_id,
                    instrument=req["universe_symbol"],
                    timeframe=req["timeframe"],
                    period_start=start,
                    period_end=end,
                    dataset_hash=dataset_hash,
                    universe_sha256=compute_universe_sha256(self._universe_path),
                    status="running",
                    report_path=str(self._reports_dir / f"{run_id}.json"),
                )

        try:
            metrics = run_backtest(
                bars,
                universe_symbol=req["universe_symbol"],
                timeframe=req["timeframe"],
                strategy_kind=req["strategy_kind"],
                costs=VenueCostConfig.for_multiplier(req["cost_multiplier"]),
                dataset_hash=dataset_hash,
                halt_flag=halt_flag,
                strategy_params=req.get("strategy_params") or None,
            )
        except Exception:
            if backtest_run_id is not None:
                self._store.update_run_status(backtest_run_id, status="failed")
            raise

        if backtest_run_id is not None:
            records = metrics.extra.get("closed_trade_records", [])
            self._store.insert_trades(backtest_run_id, req["universe_symbol"], records)
            self._store.update_run_status(
                backtest_run_id,
                status="completed",
                metrics={"comparable": metrics.comparable()},
            )

        return {"comparable": metrics.comparable(), "extra": metrics.extra}
