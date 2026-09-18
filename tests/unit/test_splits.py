"""Walk-forward și split cronologic — holdout neatins de ferestre."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.data.sources import Bar
from src.engine.splits import chronological_split, walk_forward_folds


def _bars(n: int) -> list[Bar]:
    return [
        Bar(
            instrument="ETHUSD",
            timestamp=datetime(2024, 11, 1, tzinfo=timezone.utc).replace(day=min(30, (i % 30) + 1)),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal(100 + i),
            volume=Decimal("1"),
        )
        for i in range(n)
    ]


def test_chronological_split_60_20_20() -> None:
    bars = _bars(10)
    split = chronological_split(bars)
    assert len(split.train) == 6
    assert len(split.validation) == 2
    assert len(split.holdout) == 2
    assert split.train[-1].timestamp < split.validation[0].timestamp
    assert split.validation[-1].timestamp < split.holdout[0].timestamp


def test_holdout_not_in_walk_forward() -> None:
    bars = _bars(20)
    split = chronological_split(bars)
    tv = split.train + split.validation
    folds = walk_forward_folds(tv, n_folds=3)
    holdout_ts = {bar.timestamp for bar in split.holdout}
    for fold in folds:
        seen = {bar.timestamp for bar in fold.train + fold.out_of_sample}
        assert holdout_ts.isdisjoint(seen)
        assert fold.train[-1].timestamp < fold.out_of_sample[0].timestamp


def test_expanding_train() -> None:
    bars = _bars(16)
    folds = walk_forward_folds(bars, n_folds=3)
    assert len(folds[0].train) < len(folds[1].train) <= len(folds[2].train)


def test_split_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        chronological_split([])
