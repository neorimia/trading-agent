"""CLI sidecar: Kraken Balance/OpenOrders. Zero AddOrder. Zero LIVE_TRADING_ENABLED."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.execution.key_policy import monitor_child_env  # noqa: E402
from src.execution.kraken_live import build_kraken_live_broker  # noqa: E402
from src.monitor.broker_monitor import (  # noqa: E402
    BrokerMonitorSnapshot,
    run_monitor_loop,
    write_broker_monitor,
)


class _StopFlag:
    def __init__(self) -> None:
        self.stopped = False

    def request(self, *_args: object) -> None:
        self.stopped = True

    def __call__(self) -> bool:
        return self.stopped


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kraken broker monitor (Query-only)")
    parser.add_argument("--runtime-dir", default=str(REPO_ROOT / "runtime" / "paper"))
    parser.add_argument("--poll-interval-s", type=float, default=30.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runtime = Path(args.runtime_dir)
    snapshot_path = runtime / "control" / "broker_monitor.json"
    env = monitor_child_env()
    try:
        broker = build_kraken_live_broker(env, mode="monitor")
    except Exception as exc:
        write_broker_monitor(
            snapshot_path,
            BrokerMonitorSnapshot(status="error", error=str(exc)),
        )
        raise
    flag = _StopFlag()
    signal.signal(signal.SIGTERM, flag.request)
    signal.signal(signal.SIGINT, flag.request)
    try:
        run_monitor_loop(
            broker,
            snapshot_path,
            poll_interval_s=args.poll_interval_s,
            should_stop=flag,
            environ=env,
        )
    finally:
        broker.close()


if __name__ == "__main__":
    main()
