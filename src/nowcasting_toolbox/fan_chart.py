"""Fan chart computation using BVAR posterior draws and DFM Kalman variance."""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from typing import Optional

FloatArray = NDArray[np.float64]


def bvar_fan_chart(
    B_draws: FloatArray,
    Sigma_draws: FloatArray,
    X_last: FloatArray,
    n_forecast: int = 1,
    lags: int = 2,
    target_idx: int = -1,
    sigma_y: float = 1.0,
    mu_y: float = 0.0,
    percentiles: list[float] = [10, 25, 50, 75, 90],
) -> dict:
    """Generate fan chart from BVAR posterior draws.

    Parameters
    ----------
    B_draws : (n_draws, N, N*p) posterior coefficient draws
    Sigma_draws : (n_draws, N, N) posterior covariance draws
    X_last : (N*p,) last observation vector (lagged values)
    n_forecast : number of steps ahead
    lags : number of VAR lags
    target_idx : index of target variable
    sigma_y, mu_y : de-standardization parameters
    percentiles : percentiles to compute

    Returns
    -------
    dict with 'percentiles' (dict of percentile -> value) and 'draws' (raw forecast draws)
    """
    n_draws = B_draws.shape[0]
    N = B_draws.shape[1]

    # Generate forecasts from each posterior draw
    forecasts = np.zeros((n_draws, n_forecast))

    for d in range(n_draws):
        B = B_draws[d]  # (N, N*p)
        x = X_last.copy()  # (N*p,)

        for h in range(n_forecast):
            # One-step ahead forecast: x_{t+1} = B @ x_t
            x_new = B @ x

            # Add shock from posterior covariance
            if h < n_forecast - 1:
                try:
                    L = np.linalg.cholesky(Sigma_draws[d])
                    shock = L @ np.random.randn(N)
                    x_new = x_new + shock
                except np.linalg.LinAlgError:
                    pass  # non-positive-definite, skip shock

            forecasts[d, h] = x_new[target_idx]
            x = np.roll(x, N)
            x[:N] = x_new

    # De-standardize
    forecasts_pct = forecasts * sigma_y + mu_y

    # Compute percentiles
    pct_values = {}
    for p in percentiles:
        pct_values[p] = np.percentile(forecasts_pct, p, axis=0)

    return {
        "percentiles": pct_values,
        "draws": forecasts_pct,
        "mean": np.mean(forecasts_pct, axis=0),
        "std": np.std(forecasts_pct, axis=0),
    }


def dfm_fan_chart(
    X_sm: FloatArray,
    V_smooth: FloatArray,
    C: FloatArray,
    R: FloatArray,
    target_idx: int = -1,
    sigma_y: float = 1.0,
    mu_y: float = 0.0,
    percentiles: list[float] = [10, 25, 50, 75, 90],
) -> dict:
    """Generate fan chart from DFM Kalman smoother variance.

    Parameters
    ----------
    X_sm : (T, N) smoothed observations
    V_smooth : (T, K, K) smoothed state covariances
    C : (N, K) observation matrix
    R : (N, N) observation noise
    target_idx : index of target variable
    sigma_y, mu_y : de-standardization parameters
    percentiles : percentiles to compute

    Returns
    -------
    dict with 'percentiles' and 'std' for each time step
    """
    T, N = X_sm.shape

    # Compute observation-level variance: Var(X) = C @ V @ C.T + R
    obs_var = np.zeros((T, N))
    for t in range(T):
        Vt = V_smooth[t]
        Ct = C if C.ndim == 2 else C[t]
        var_diag = np.diag(Ct @ Vt @ Ct.T) + np.diag(R) if R.ndim == 2 else np.diag(Ct @ Vt @ Ct.T) + R
        obs_var[t, :] = var_diag

    # Target variable
    target_mean = X_sm[:, target_idx] * sigma_y + mu_y
    target_std = np.sqrt(obs_var[:, target_idx]) * abs(sigma_y)

    # Compute percentiles (assuming normality)
    from scipy.stats import norm
    pct_values = {}
    for p in percentiles:
        z = norm.ppf(p / 100)
        pct_values[p] = target_mean + z * target_std

    return {
        "percentiles": pct_values,
        "mean": target_mean,
        "std": target_std,
    }
