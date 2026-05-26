"""Stationarity transformations for economic time series.

Replicates common_transform_data.m with 5 transformation codes:

    0 = level (no transform, just standardize)
    1 = month-on-month growth rate (dlog)
    2 = first difference
    3 = annualized quarter-on-quarter growth rate (dlog × 4)
    4 = year-on-year growth rate (dlog, lag=12 for monthly, lag=4 for quarterly)

All transforms return NaN for the leading rows where lags are unavailable.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional

import numpy as np
import pandas as pd


class TransformCode(IntEnum):
    LEVEL = 0
    MOM = 1     # dlog(t) - dlog(t-1)
    DIFF = 2    # x(t) - x(t-1)
    QOQ_ANN = 3  # (dlog(t) - dlog(t-1)) × 4  (or × periodicity)
    YOY = 4     # dlog(t) - dlog(t-lag)


def transform_series(
    x: np.ndarray,
    code: int | TransformCode,
    freq: str = "monthly",
) -> np.ndarray:
    """Apply a single transformation code to a 1-D series.

    Parameters
    ----------
    x : 1-D array
        Input levels.
    code : int
        Transformation code 0-4.
    freq : str
        "monthly" or "quarterly". Affects YOY lag length (12 vs 4)
        and QOQ_ANN scaling (1 vs 4).

    Returns
    -------
    y : 1-D array, same length as x, with leading NaN.
    """
    code = TransformCode(code)
    y = x.astype(float).copy()

    if code == TransformCode.LEVEL:
        return y

    lag = 1

    if code == TransformCode.YOY:
        lag = 12 if freq == "monthly" else 4

    if code in (TransformCode.MOM, TransformCode.QOQ_ANN, TransformCode.YOY):
        # dlog = log(x_t) - log(x_{t-lag})
        log_x = np.log(np.maximum(y, 1e-12))
        y = np.full_like(y, np.nan)
        y[lag:] = log_x[lag:] - log_x[:-lag]
    elif code == TransformCode.DIFF:
        y = np.full_like(y, np.nan)
        y[lag:] = x[lag:] - x[:-lag]

    if code == TransformCode.QOQ_ANN:
        scale = 1 if freq == "quarterly" else 3  # monthly→quarterly uses ×3 approx
        y *= scale

    return y


def transform_dataframe(
    df: pd.DataFrame,
    code_map: dict[str, int],
    freq: str = "monthly",
    standardize: bool = True,
) -> pd.DataFrame:
    """Apply transformations to a DataFrame.

    Parameters
    ----------
    df : DataFrame
        Columns are series, index is datetime or integer. Must contain
        values in LEVELS (will be logged internally for growth transforms).
    code_map : dict
        Mapping of column_name -> transform_code (0-4).
    freq : str
        "monthly" or "quarterly".
    standardize : bool
        If True, standardize each column to zero mean, unit variance.

    Returns
    -------
    DataFrame with transformed columns.
    """
    result = df.copy()
    for col, code in code_map.items():
        if col in result.columns:
            result[col] = transform_series(
                result[col].to_numpy(dtype=float), code, freq
            )

    if standardize:
        result = _standardize(result)

    return result


def transform_matrix(
    X: np.ndarray,
    codes: list[int],
    freq: str = "monthly",
    standardize: bool = True,
) -> np.ndarray:
    """Apply transformations to a (T, N) array.

    Parameters
    ----------
    X : (T, N) array, values in levels.
    codes : list of int, length N.
    freq : "monthly" or "quarterly".
    standardize : bool.

    Returns
    -------
    (T, N) transformed array.
    """
    T, N = X.shape
    if len(codes) != N:
        raise ValueError(f"codes length {len(codes)} != columns {N}")
    result = np.full((T, N), np.nan)
    for j in range(N):
        result[:, j] = transform_series(X[:, j], codes[j], freq)
    if standardize:
        result = _standardize_array(result)
    return result


# --------------------------------------------------------------------------
# Standardization
# --------------------------------------------------------------------------

def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in result.columns:
        col_data = result[col].to_numpy(dtype=float)
        mu = np.nanmean(col_data)
        sigma = np.nanstd(col_data)
        if sigma is not None and sigma > 1e-12:
            result[col] = (col_data - mu) / sigma
    return result


def _standardize_array(X: np.ndarray) -> np.ndarray:
    mu = np.nanmean(X, axis=0)
    sigma = np.nanstd(X, axis=0)
    sigma[sigma < 1e-12] = 1.0
    return (X - mu) / sigma
