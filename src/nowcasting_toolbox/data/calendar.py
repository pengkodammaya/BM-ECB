"""Calendar / date utilities for mixed-frequency data.

Replicates MATLAB helpers:
- BEQ_GenDates.m  — generate year/month vectors
- BEQ_DateFind.m  — find index of a (year,month) in datet
- BEQ_Add2Date.m  — add N months to a (year,month) pair
- BEQ_mon2qrt.m   — monthly → quarterly aggregation
- BEQ_monOfQ.m    — month position within quarter (1/2/3)
- BEQ_m2q.m       — Mariano-Murasawa monthly→quarterly aggregation
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_dates(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> np.ndarray:
    """Generate a (T, 2) year-month array like BEQ_GenDates.

    Parameters
    ----------
    start_year, start_month : int
        Start date (inclusive).
    end_year, end_month : int
        End date (inclusive).

    Returns
    -------
    datet : np.ndarray of shape (T, 2), columns = [year, month]
    """
    start = pd.Timestamp(start_year, start_month, 1)
    end = pd.Timestamp(end_year, end_month, 1)
    idx = pd.period_range(start, end, freq="M")
    datet = np.column_stack([idx.year.values, idx.month.values])
    return datet


def generate_quarterly_dates(
    start_year: int,
    start_quarter: int,
    end_year: int,
    end_quarter: int,
) -> np.ndarray:
    """Generate (T, 2) year-quarter array.

    Returns (T, 2) with columns [year, quarter] where quarter = 1..4.
    """
    start = pd.Timestamp(start_year, (start_quarter - 1) * 3 + 1, 1)
    end = pd.Timestamp(end_year, (end_quarter - 1) * 3 + 1, 1)
    idx = pd.period_range(start, end, freq="Q")
    datet = np.column_stack([idx.year.values, idx.quarter.values])
    return datet


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def date_find(datet: np.ndarray, year: int, month: int) -> int:
    """Return 0-based index of (year, month) in datet. Returns -1 if not found."""
    mask = (datet[:, 0] == year) & (datet[:, 1] == month)
    indices = np.where(mask)[0]
    return int(indices[0]) if len(indices) > 0 else -1


def date_find_many(datet: np.ndarray, ym: np.ndarray) -> np.ndarray:
    """Return indices for an (N,2) array of (year,month) pairs."""
    result = np.full(len(ym), -1, dtype=int)
    for i, (y, m) in enumerate(ym):
        result[i] = date_find(datet, int(y), int(m))
    return result


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------

def add_months(year: int, month: int, n: int) -> tuple[int, int]:
    """Add N months to (year, month), returning (new_year, new_month)."""
    ts = pd.Timestamp(year, month, 1) + pd.DateOffset(months=n)
    return ts.year, ts.month


# ---------------------------------------------------------------------------
# Frequency conversion
# ---------------------------------------------------------------------------

def month_of_quarter(month: int) -> int:
    """Return position within quarter: 1, 2, or 3."""
    return ((month - 1) % 3) + 1


def month_to_quarter_indices(datet: np.ndarray) -> np.ndarray:
    """Return indices of rows where month is the 3rd of the quarter."""
    return np.where(datet[:, 1] % 3 == 0)[0]


def month_to_quarter(
    X: np.ndarray,
    datet: np.ndarray,
    method: str = "last",
) -> tuple[np.ndarray, np.ndarray]:
    """Aggregate monthly data X (T, N) to quarterly frequency.

    Parameters
    ----------
    X : (T, N) array
    datet : (T, 2) year-month
    method : str
        "last" — take 3rd month value (matches BEQ_select_3rd_month approach)
        "mean" — average of 3 months
        "sum"  — sum of 3 months
        "mariano_murasawa" — Mariano-Murasawa approximation (for growth rates)

    Returns
    -------
    Xq : (Tq, N) quarterly values
    dateQ : (Tq, 2) quarterly year-month (3rd month of each quarter)
    """
    if method == "mariano_murasawa":
        return _mariano_murasawa(X)

    q3_idx = month_to_quarter_indices(datet)
    Tq = len(q3_idx)

    if method == "last":
        Xq = X[q3_idx]
    elif method == "mean":
        Xq = np.zeros((Tq, X.shape[1]))
        for i, idx in enumerate(q3_idx):
            Xq[i] = np.nanmean(X[idx - 2 : idx + 1], axis=0)
    elif method == "sum":
        Xq = np.zeros((Tq, X.shape[1]))
        for i, idx in enumerate(q3_idx):
            Xq[i] = np.nansum(X[idx - 2 : idx + 1], axis=0)
    else:
        raise ValueError(f"Unknown method: {method}")

    dateQ = datet[q3_idx]
    return Xq, dateQ


def _mariano_murasawa(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Apply Mariano-Murasawa (2003) monthly→quarterly approximation.

    For monthly growth rates x_t, the quarterly counterpart is:
        y_t = (1/3)*x_t + (2/3)*x_{t-1} + x_{t-2} + (2/3)*x_{t-3} + (1/3)*x_{t-4}

    (Uses the standard weights: 1, 2, 3, 2, 1 normalised to sum=9 then
    rescaled — this implementation mirrors the toolbox R matrix:
    [2 -1 0 0 0; 3 0 -1 0 0; 2 0 0 -1 0; 1 0 0 0 -1])

    NOTE: This actually returns the constraint matrix R_mat and the
    transformed monthly data; it does NOT reduce to quarterly. The DFM
    handles the quarterly constraint internally via the state-space.
    For the aggregation here we return the weighted rolling sum.

    Parameters
    ----------
    X : (T, N) monthly data

    Returns
    -------
    X_mm : (T, N) Mariano-Murasawa transformed monthly data
    """
    T, N = X.shape
    weights = np.array([1, 2, 3, 2, 1], dtype=float)
    # weights /= weights.sum()  # optional normalisation
    X_mm = np.full((T, N), np.nan)
    for t in range(4, T):
        window = X[t - 4 : t + 1][::-1]  # latest first
        if window.shape[0] == 5:
            X_mm[t] = np.nansum(window * weights[:, None], axis=0)
    return X_mm


# ---------------------------------------------------------------------------
# Ragged-edge helpers
# ---------------------------------------------------------------------------

def last_observed_date(X: np.ndarray, datet: np.ndarray) -> tuple[int, int]:
    """Find the latest row where at least one column is non-NaN."""
    observed = ~np.all(np.isnan(X), axis=1)
    idx = np.where(observed)[0][-1]
    return int(datet[idx, 0]), int(datet[idx, 1])


def publication_lag_vector(
    X: np.ndarray,
    datet: np.ndarray,
) -> np.ndarray:
    """Estimate publication delay (in months) for each column.

    Returns an array of length N where each entry is the number of
    trailing NaNs beyond the latest observation period.
    """
    N = X.shape[1]
    lags = np.zeros(N, dtype=int)
    for j in range(N):
        col = X[:, j]
        last_valid = np.where(~np.isnan(col))[0]
        if len(last_valid) == 0:
            lags[j] = len(col)
        else:
            lags[j] = len(col) - 1 - int(last_valid[-1])
    return lags
