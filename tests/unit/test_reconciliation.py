"""Reconciliere local vs broker — mismatch forțează raport unmatched."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from src.execution.broker import BrokerState
from src.execution.reconciliation import LocalPortfolioSnapshot, Reconciliation


def test_matching_states(tmp_path: Path) -> None:
    recon = Reconciliation(tmp_path / "recon.json")
    local = LocalPortfolioSnapshot(positions={"ETHUSD": Decimal("0.1")})
    broker = BrokerState(positions={"ETHUSD": Decimal("0.1")})
    report = recon.reconcile(local, broker)
    assert report.matched is True
    assert recon.last_report() is not None
    assert recon.last_report().matched is True


def test_position_mismatch(tmp_path: Path) -> None:
    recon = Reconciliation(tmp_path / "recon.json")
    local = LocalPortfolioSnapshot(positions={"ETHUSD": Decimal("0.1")})
    broker = BrokerState(positions={"ETHUSD": Decimal("0.2")})
    report = recon.reconcile(local, broker)
    assert report.matched is False
    assert report.mismatches[0].field == "position"


def test_open_order_mismatch(tmp_path: Path) -> None:
    recon = Reconciliation(tmp_path / "recon.json")
    local = LocalPortfolioSnapshot(pending_client_order_ids=["abc"])
    broker = BrokerState(open_client_order_ids=["xyz"])
    report = recon.reconcile(local, broker)
    assert report.matched is False
    assert report.mismatches[0].field == "open_orders"
