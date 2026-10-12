"""Paired comparisons between two Runs over their shared case ids. numpy only, no scipy."""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np


def _shared(
    correct_a: Mapping[str, bool], correct_b: Mapping[str, bool]
) -> tuple[np.ndarray, np.ndarray]:
    ids = sorted(set(correct_a) & set(correct_b))
    if not ids:
        raise ValueError("the two runs share no case ids")
    a = np.array([float(correct_a[case_id]) for case_id in ids])
    b = np.array([float(correct_b[case_id]) for case_id in ids])
    return a, b


def paired_bootstrap_diff(
    correct_a: Mapping[str, bool],
    correct_b: Mapping[str, bool],
    n_boot: int = 2000,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Accuracy difference a - b with a 95% percentile bootstrap interval over shared ids."""
    a, b = _shared(correct_a, correct_b)
    delta = a - b
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(delta), size=(n_boot, len(delta)))
    means = delta[samples].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(delta.mean()), float(low), float(high)


def mcnemar(correct_a: Mapping[str, bool], correct_b: Mapping[str, bool]) -> tuple[int, int, float]:
    """Exact McNemar test: (b, c, p) where b = a right and b wrong, c = the reverse.

    The two-sided p-value is twice the binomial lower tail of min(b, c) out of b + c at
    one half, capped at 1.
    """
    a, b = _shared(correct_a, correct_b)
    only_a = int(np.sum((a == 1.0) & (b == 0.0)))
    only_b = int(np.sum((a == 0.0) & (b == 1.0)))
    discordant = only_a + only_b
    if discordant == 0:
        return only_a, only_b, 1.0
    tail = sum(math.comb(discordant, k) for k in range(min(only_a, only_b) + 1))
    return only_a, only_b, min(1.0, 2.0 * (tail / 2**discordant))
