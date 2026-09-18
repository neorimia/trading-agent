"""Operator CLI — scrie decision.json pentru un correlation_id în așteptare."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve or reject a paper/live order intent")
    parser.add_argument("correlation_id")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--reject", action="store_true")
    parser.add_argument("--reason", default="manual")
    parser.add_argument(
        "--dir",
        default=str(REPO_ROOT / "runtime" / "paper" / "control" / "approvals"),
    )
    args = parser.parse_args()
    if args.approve == args.reject:
        raise SystemExit("specify exactly one of --approve or --reject")
    path = Path(args.dir) / f"{args.correlation_id}.decision.json"
    payload = {
        "approved": bool(args.approve),
        "decided_by": "human",
        "reason": args.reason,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
