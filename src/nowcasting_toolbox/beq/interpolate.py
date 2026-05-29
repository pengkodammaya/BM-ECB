"""BVAR-based interpolation for bridge equations (3 modes).

Replicates BEQ_Run_extrapolation_BVAR.m — takes ragged-edge monthly
data and fills missing values at the tail using a small BVAR.

Three modes (matching Par.type 901-903):
- 901: BVAR on all variables
- 902: BVAR only on selected variables
- 903: Univariate BVAR (one series at a time)

WARNING: Line 126 uses np.interp which interpolates between past AND future
values. This causes data leakage in pseudo-real-time backtesting. For
backtesting, consider using forward-fill before calling this function.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def extrapolate_bvar(
    X: FloatArray,
    lags: int = 6,
    lambda_: float = 0.2,
    method: int = 901,
) -> FloatArray:
    """Fill trailing NaN values using a small BVAR.

    Parameters
    ----------
    X : (T, N) array
        Data with trailing NaN (ragged edge).
    lags : int
        Number of VAR lags for interpolation.
    lambda_ : float
        Shrinkage parameter (Minnesota prior tightness).
    method : int
        901 = multivariate BVAR, 903 = univariate BVAR.

    Returns
    -------
    X_filled : (T, N) with trailing NaN interpolated.
    """
    T, N = X.shape
    if N == 1:
        method = 903  # univariate only option

    X_out = X.copy()

    if method == 903 or N == 1:
        for j in range(N):
            X_out[:, j] = _univariate_ar_extrapolate(X[:, j], lags)
    else:
        X_out = _multivariate_bvar_extrapolate(X, lags, lambda_)

    return X_out


def _univariate_ar_extrapolate(series: FloatArray, lags: int) -> FloatArray:
    """Extrapolate a single series using AR(p)."""
    x = series.copy()
    T = len(x)
    valid = np.where(~np.isnan(x))[0]
    if len(valid) < lags + 2:
        return x

    last_valid = valid[-1]
    if last_valid == T - 1:
        return x  # no extrapolation needed

    # Fit AR(p) on valid data
    y = x[lags:last_valid + 1]
    X_lag = np.zeros((len(y), lags))
    for lag in range(lags):
        X_lag[:, lag] = x[lags - lag - 1 : last_valid - lag]

    valid_rows = ~np.any(np.isnan(X_lag), axis=1) & ~np.isnan(y)
    if np.sum(valid_rows) < lags + 1:
        return x

    try:
        coeffs = np.linalg.lstsq(X_lag[valid_rows], y[valid_rows], rcond=None)[0]
    except np.linalg.LinAlgError:
        return x

    # Forecast missing values
    for t in range(last_valid + 1, T):
        recent = x[t - lags : t][::-1]  # latest lags first
        if np.any(np.isnan(recent)):
            break
        x[t] = np.dot(recent, coeffs)

    return x


def _multivariate_bvar_extrapolate(
    X: FloatArray,
    lags: int,
    lambda_: float,
) -> FloatArray:
    """Extrapolate using a multivariate BVAR with Minnesota prior.

    Falls back to forward-fill if BVAR fails (e.g., too few observations).
    """
    from nowcasting_toolbox.bvar.prior import minnesota_posterior

    T, N = X.shape
    X_out = X.copy()

    # Find last row with all observations
    fully_observed = ~np.any(np.isnan(X), axis=1)
    if not np.any(fully_observed):
        # No complete rows — fall back to forward-fill
        return _forward_fill(X)

    last_full = np.where(fully_observed)[0][-1]
    if last_full >= T - 1:
        return X_out

    # Fit VAR on complete data up to last_full
    Y = X[:last_full + 1].copy()
    Y_filled = Y.copy()
    # Fill any remaining interior NaN with FORWARD-FILL (not np.interp to avoid data leakage)
    for j in range(N):
        col = Y_filled[:, j]
        last_valid = np.nan
        for t in range(len(col)):
            if not np.isnan(col[t]):
                last_valid = col[t]
            elif not np.isnan(last_valid):
                Y_filled[t, j] = last_valid

    try:
        B, Sigma = minnesota_posterior(Y_filled, lags, lambda_)
    except Exception:
        # BVAR failed — fall back to forward-fill
        return _forward_fill(X)

    # Forecast iteratively
    for t in range(last_full + 1, T):
        x_lag = np.zeros(N * lags)
        for lag in range(lags):
            lag_row = t - lag - 1
            if lag_row >= 0 and lag_row < T:
                x_lag[lag * N : (lag + 1) * N] = X_out[lag_row]

        pred = B @ x_lag
        # Only fill missing values
        for j in range(N):
            if np.isnan(X_out[t, j]):
                X_out[t, j] = pred[j]

    return X_out


def _forward_fill(X: FloatArray) -> FloatArray:
    """Forward-fill NaN values (no future interpolation)."""
    X_filled = X.copy()
    T, N = X.shape
    for j in range(N):
        col = X[:, j]
        last_valid = np.nan
        for t in range(T):
            if not np.isnan(col[t]):
                last_valid = col[t]
            elif not np.isnan(last_valid):
                X_filled[t, j] = last_valid
    return X_filled
