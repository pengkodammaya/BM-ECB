"""Variable selection: LARS, t-stat, correlation-based ranking (R port)."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def select_variables(
    X: FloatArray | pd.DataFrame,
    y: FloatArray,
    method: str = "lars",
    n_select: int = 20,
) -> pd.DataFrame:
    """Rank variables by predictive power for target y.

    Parameters
    ----------
    X : (T, N) array or DataFrame of candidate regressors.
    y : (T,) target variable.
    method : str
        "lars" — Least Angle Regression (Efron et al. 2004)
        "tstat" — t-statistic from univariate regressions (Bair et al. 2006)
        "correlation" — absolute Pearson correlation (SIS: Fan & Lv 2008)
    n_select : int
        Number of top variables to return.

    Returns
    -------
    pd.DataFrame with columns: rank, variable, score
    """
    if isinstance(X, pd.DataFrame):
        var_names = list(X.columns)
        X_arr = X.to_numpy(dtype=float)
    else:
        X_arr = np.asarray(X, dtype=float)
        var_names = [f"var_{i}" for i in range(X_arr.shape[1])]

    T, N = X_arr.shape
    y_arr = np.asarray(y, dtype=float)

    # Drop NaN rows
    valid = ~np.any(np.isnan(X_arr), axis=1) & ~np.isnan(y_arr)
    X_valid = X_arr[valid]
    y_valid = y_arr[valid]

    if method == "lars":
        scores = _lars_ranking(X_valid, y_valid)
    elif method == "tstat":
        scores = _tstat_ranking(X_valid, y_valid)
    elif method == "correlation":
        scores = _corr_ranking(X_valid, y_valid)
    else:
        raise ValueError(f"Unknown method: {method}")

    # Build ranking
    order = np.argsort(-np.abs(scores))
    result = pd.DataFrame({
        "rank": range(1, N + 1),
        "variable": [var_names[i] for i in order],
        "score": scores[order],
    })

    return result.head(n_select)


def _corr_ranking(X: FloatArray, y: FloatArray) -> FloatArray:
    """Absolute Pearson correlation."""
    N = X.shape[1]
    scores = np.zeros(N)
    for j in range(N):
        mask = ~np.isnan(X[:, j]) & ~np.isnan(y)
        if np.sum(mask) > 1:
            scores[j] = np.corrcoef(X[mask, j], y[mask])[0, 1]
    return scores


def _tstat_ranking(X: FloatArray, y: FloatArray) -> FloatArray:
    """Absolute t-statistic from univariate OLS."""
    from statsmodels.api import OLS, add_constant

    N = X.shape[1]
    scores = np.zeros(N)
    for j in range(N):
        try:
            model = OLS(y, add_constant(X[:, j]), missing="drop").fit()
            scores[j] = abs(model.tvalues.iloc[1]) if len(model.tvalues) > 1 else 0
        except Exception:
            scores[j] = 0
    return scores


def _lars_ranking(X: FloatArray, y: FloatArray) -> FloatArray:
    """LARS-based ranking: order of entry into active set.

    Uses sklearn's Lars to compute the solution path. Variables that enter
    the active set earlier (at higher alpha) are ranked higher.
    """
    from sklearn.linear_model import Lars

    N = X.shape[1]
    try:
        model = Lars(n_nonzero_coefs=min(N, len(y) - 1), fit_intercept=True, normalize=True)
        model.fit(X, y)

        # Use the coefficient path to determine entry order
        # coef_path_ has shape (n_alphas, n_features) or list of arrays
        if hasattr(model, 'coef_path_') and len(model.coef_path_) > 0:
            # coef_path_ is a list of (n_features,) arrays at each alpha step
            # Find the first alpha where each coefficient becomes non-zero
            entry_alpha = np.full(N, np.inf)
            for step_idx, coef in enumerate(model.coef_path_):
                for j in range(N):
                    if abs(coef[j]) > 1e-10 and entry_alpha[j] == np.inf:
                        entry_alpha[j] = step_idx

            # Score: earlier entry = higher score
            scores = np.zeros(N)
            for j in range(N):
                if entry_alpha[j] < np.inf:
                    scores[j] = N - entry_alpha[j]  # higher = entered earlier
        else:
            # Fallback: use absolute coefficient values
            scores = np.abs(model.coef_)
    except Exception:
        # Fallback to correlation-based ranking
        scores = np.array([
            abs(np.corrcoef(X[:, j], y)[0, 1]) if np.std(X[:, j]) > 1e-12 else 0
            for j in range(N)
        ])

    return scores
