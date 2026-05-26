"""Missing data handling utilities (NaN imputation, leading/trailing trimming)."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def handle_nans(
    X: FloatArray,
    method: str = "remove_trailing",
    **kwargs,
) -> FloatArray:
    """Handle NaN values in data matrix.

    Parameters
    ----------
    X : (T, N) array.
    method : str
        "remove_trailing" — trim leading/trailing NaN rows.
        "interpolate" — linear interpolation across time.
        "spline" — cubic spline interpolation.

    Returns
    -------
    X_clean : (T_out, N) array.
    """
    if method == "remove_trailing":
        return _remove_trailing_nans(X)
    elif method == "interpolate":
        return _interpolate_nans(X)
    elif method == "spline":
        return _spline_nans(X)
    else:
        raise ValueError(f"Unknown NaN handling method: {method}")


def _remove_trailing_nans(X: FloatArray) -> FloatArray:
    """Remove rows at start and end where ALL columns are NaN."""
    valid_rows = ~np.all(np.isnan(X), axis=1)
    if not np.any(valid_rows):
        return X[:0]
    first = np.where(valid_rows)[0][0]
    last = np.where(valid_rows)[0][-1]
    return X[first : last + 1].copy()


def _interpolate_nans(X: FloatArray) -> FloatArray:
    """Linear interpolation for interior NaN values."""
    T, N = X.shape
    X_out = X.copy()
    indices = np.arange(T)
    for j in range(N):
        col = X_out[:, j]
        nan_mask = np.isnan(col)
        if not np.any(nan_mask):
            continue
        valid = ~nan_mask
        if np.sum(valid) < 2:
            continue
        X_out[nan_mask, j] = np.interp(indices[nan_mask], indices[valid], col[valid])
    return X_out


def _spline_nans(X: FloatArray) -> FloatArray:
    """Cubic spline interpolation for NaN values."""
    from scipy.interpolate import CubicSpline

    T, N = X.shape
    X_out = X.copy()
    indices = np.arange(T)
    for j in range(N):
        col = X_out[:, j]
        nan_mask = np.isnan(col)
        if not np.any(nan_mask):
            continue
        valid = ~nan_mask
        if np.sum(valid) < 4:
            # Fall back to linear
            X_out[nan_mask, j] = np.interp(indices[nan_mask], indices[valid], col[valid])
            continue
        try:
            cs = CubicSpline(indices[valid], col[valid])
            X_out[nan_mask, j] = cs(indices[nan_mask])
        except Exception:
            X_out[nan_mask, j] = np.interp(indices[nan_mask], indices[valid], col[valid])
    return X_out
