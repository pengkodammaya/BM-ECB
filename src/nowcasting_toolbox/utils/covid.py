"""COVID-19 data correction modes (replicates common_NaN_Covid_correct.m).

Modes:
    0 = no correction
    1 = add dummy observations for June 2020 and Sept 2020 quarters
    2 = set observations from Feb 2020 to Sep 2020 (inclusive) to NaN
    3 = outlier correction using median absolute deviation
    4 = add dummy observations for March 2020 and June 2020 quarters

Usage:
    from nowcasting_toolbox.utils.covid import correct_covid
    X_corrected = correct_covid(X, datet, mode=2)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def correct_covid(
    X: FloatArray,
    datet: FloatArray,
    mode: int = 0,
    threshold: float = 5.0,
) -> FloatArray:
    """Apply COVID correction to data matrix.

    Parameters
    ----------
    X : (T, N) data matrix. NaN indicates missing values.
    datet : (T, 2) year-month for each row.
    mode : int
        0 = none, 1 = dummies (Jun+Sep 2020), 2 = NaN block (Feb-Sep 2020),
        3 = outlier correction, 4 = dummies (Mar+Jun 2020).
    threshold : float
        Used only in mode 3: number of MADs for outlier detection.

    Returns
    -------
    X_corrected : (T, N) array. For dummy modes (1, 4), the dummy column is
                   NOT appended — dummies are handled by the BEQ separately.
    """
    if mode == 0:
        return X.copy()

    elif mode == 2:
        return _covid_nan_block(X, datet)

    elif mode == 3:
        return _covid_outlier_correction(X, threshold)

    elif mode in (1, 4):
        # Dummy modes don't modify X — dummies must be passed to BEQ
        # The data remains unchanged; dummies are separate
        return X.copy()

    else:
        raise ValueError(f"Unknown COVID correction mode: {mode}")


def get_covid_dummies(
    datet: FloatArray,
    mode: int = 1,
) -> FloatArray:
    """Get COVID dummy variables for quarterly regression.

    Parameters
    ----------
    datet : (T, 2) year-month
    mode : int
        1 = dummies for (2020, 6) and (2020, 9)
        4 = dummies for (2020, 3) and (2020, 6)

    Returns
    -------
    dummies : (Tq, n_dummies) where Tq = number of quarter-end rows
    """
    if mode not in (1, 4):
        return np.array([]).reshape(0, 0)

    if mode == 1:
        covid_months = [(2020, 6), (2020, 9)]
    else:  # mode == 4
        covid_months = [(2020, 3), (2020, 6)]

    q_end_mask = datet[:, 1] % 3 == 0
    q_end_datet = datet[q_end_mask]
    Tq = len(q_end_datet)

    dummies = np.zeros((Tq, len(covid_months)))
    for j, (y, m) in enumerate(covid_months):
        for t in range(Tq):
            if q_end_datet[t, 0] == y and q_end_datet[t, 1] == m:
                dummies[t, j] = 1.0
                break

    return dummies


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _covid_nan_block(X: FloatArray, datet: FloatArray) -> FloatArray:
    """Set Feb 2020 through Sep 2020 observations to NaN."""
    X_out = X.copy()
    start_set = False
    for t in range(len(datet)):
        y, m = int(datet[t, 0]), int(datet[t, 1])
        if y == 2020 and m == 2:
            start_set = True
        if start_set and (y > 2020 or (y == 2020 and m > 9)):
            break
        if start_set:
            X_out[t, :] = np.nan
    return X_out


def _covid_outlier_correction(X: FloatArray, threshold: float) -> FloatArray:
    """Replace outliers with NaN using median absolute deviation."""
    T, N = X.shape
    X_out = X.copy()

    for j in range(N):
        col = X[:, j]
        valid = ~np.isnan(col)
        if np.sum(valid) < 5:
            continue

        median = np.nanmedian(col)
        mad = np.nanmedian(np.abs(col - median)) * 1.4826  # scale approx to std

        if mad < 1e-12:
            continue

        z_score = np.abs(col - median) / mad
        outliers = z_score > threshold
        X_out[outliers, j] = np.nan

    return X_out
