"""Bridge equation specifications generator.

Replicates the combinatorial logic in BEQ_estimate.m:
- All single-monthly-regressor specifications
- All pairs of monthly regressors (n choose 2)
- Optionally each with quarterly regressors
- Multiplied by interpolation types (901/902/903)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def generate_combinations(
    nM: int,
    nQ: int = 1,
    types: list[int] | None = None,
) -> FloatArray:
    """Generate all bridge equation specifications.

    Parameters
    ----------
    nM : int
        Number of monthly variables.
    nQ : int
        Number of quarterly variables (including target at end).
        nQ-1 quarterly regressors are available.
    types : list[int], optional
        Interpolation types to include. Default [901, 902, 903].

    Returns
    -------
    specs : (n_specs, 4) array
        Columns: [interpolation_type, monthly_1, monthly_2, quarterly]
        NaN = not used.
    """
    if types is None:
        types = [901, 902, 903]

    # Monthly combinations: 1-var and 2-var
    pairs = list(_combinations(nM, 2))  # n choose 2
    singles = [(j, np.nan) for j in range(nM)]  # univariate

    monthly_specs = pairs + singles

    # Add quarterly regressors
    nQ_regressors = max(nQ - 1, 0)
    all_specs = []

    for m1, m2 in monthly_specs:
        # Without quarterly regressor
        all_specs.append([np.nan, m1, m2, np.nan])
        # With each quarterly regressor
        for q in range(nQ_regressors):
            all_specs.append([np.nan, m1, m2, float(q)])

    # Multiply by interpolation types
    result = []
    for t in types:
        for spec in all_specs:
            result.append([float(t)] + spec[1:])

    return np.array(result)


def _combinations(n: int, k: int):
    """Generate all combinations of k elements from range(n)."""
    from itertools import combinations
    return list(combinations(range(n), k))
