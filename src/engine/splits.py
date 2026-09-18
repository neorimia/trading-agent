"""Separare cronologică train/validation/holdout + ferestre walk-forward expanding."""

from __future__ import annotations

from dataclasses import dataclass

from src.data.sources import Bar


@dataclass(frozen=True)
class ChronologicalSplit:
    train: list[Bar]
    validation: list[Bar]
    holdout: list[Bar]


@dataclass(frozen=True)
class WalkForwardFold:
    index: int
    train: list[Bar]
    out_of_sample: list[Bar]


def chronological_split(
    bars: list[Bar],
    *,
    train_frac: float = 0.6,
    validation_frac: float = 0.2,
) -> ChronologicalSplit:
    if not bars:
        raise ValueError("cannot split an empty bar series")
    if train_frac <= 0 or validation_frac <= 0 or train_frac + validation_frac >= 1:
        raise ValueError("train_frac and validation_frac must be positive and sum to < 1")
    n = len(bars)
    train_end = max(1, int(n * train_frac))
    validation_end = max(train_end + 1, int(n * (train_frac + validation_frac)))
    if validation_end >= n:
        validation_end = n - 1
    if validation_end <= train_end:
        raise ValueError("not enough bars for train/validation/holdout")
    return ChronologicalSplit(
        train=bars[:train_end],
        validation=bars[train_end:validation_end],
        holdout=bars[validation_end:],
    )


def walk_forward_folds(train_and_validation: list[Bar], n_folds: int = 3) -> list[WalkForwardFold]:
    """Expanding window: fold i antrenează pe prefixul 0..i, evaluează pe chunk-ul i+1.

    Holdout-ul NU intră aici — apelantul trece doar train+validation.
    """
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    n = len(train_and_validation)
    chunk = n // (n_folds + 1)
    if chunk < 1:
        raise ValueError("not enough bars for the requested walk-forward folds")
    folds: list[WalkForwardFold] = []
    for index in range(n_folds):
        train_end = chunk * (index + 1)
        oos_end = n if index == n_folds - 1 else chunk * (index + 2)
        oos = train_and_validation[train_end:oos_end]
        if not oos:
            break
        folds.append(
            WalkForwardFold(
                index=index,
                train=train_and_validation[:train_end],
                out_of_sample=oos,
            )
        )
    return folds
