"""Outlier detection (replicates common_outliers.m)."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def detect_outliers(
    X: FloatArray,
    threshold: float = 5.0,
    replace: bool = True,
) -> FloatArray:
    """Detect and optionally replace outliers using median absolute deviation.

    Parameters
    ----------
    X : (T, N) array.
    threshold : float
        Number of MADs above which a point is flagged.
    replace : bool
        If True, replace outliers with NaN.

    Returns
    -------
    X_clean : (T, N) array with outliers optionally replaced.
    """
    T, N = X.shape
    X_out = X.copy()

    for j in range(N):
        col = X[:, j]
        valid = ~np.isnan(col)
        if np.sum(valid) < 5:
            continue

        median = np.nanmedian(col)
        mad = np.nanmedian(np.abs(col - median)) * 1.4826  # scale to ~std

        if mad < 1e-12:
            continue

        z_score = np.abs(col - median) / mad
        outliers = z_score > threshold

        if replace:
            X_out[outliers, j] = np.nan

    return X_out
