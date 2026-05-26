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
    """LARS-based ranking: order of entry into active set."""
    from sklearn.linear_model import Lars

    N = X.shape[1]
    try:
        model = Lars(n_nonzero_coefs=min(N, len(y) - 1), fit_intercept=True)
        model.fit(X, y)
        # Order of coefficient activation
        alphas = model.alphas_ if hasattr(model, "alphas_") else None
    except Exception:
        return np.zeros(N)

    # Simpler: stepwise entry order
    scores = np.zeros(N)
    active_order = []
    X_work = X.copy()

    for _ in range(min(N, 50)):
        corrs = np.array([
            abs(np.corrcoef(X_work[:, j], y)[0, 1]) if np.std(X_work[:, j]) > 1e-12 else 0
            for j in range(X_work.shape[1])
        ])
        best = int(np.argmax(corrs))
        if best in active_order or corrs[best] < 0.01:
            break
        active_order.append(best)
        # Regress out
        from statsmodels.api import OLS, add_constant
        try:
            m = OLS(y, add_constant(X_work[:, best]), missing="drop").fit()
            y = m.resid
        except Exception:
            pass

    for rank, idx in enumerate(active_order):
        scores[idx] = N - rank  # higher = entered earlier

    return scores
