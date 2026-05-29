"""Post-processing: growth-to-level conversion and confidence bands."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def growth_to_level(
    growth_forecast: FloatArray,
    base_level: float,
    annualized: bool = True,
) -> FloatArray:
    """Convert quarterly growth forecasts to GDP levels.

    Parameters
    ----------
    growth_forecast : (T,) array
        Growth rates (e.g., QoQ annualized % as decimals: 0.052 = 5.2%).
    base_level : float
        Last known GDP level in MYR billions.
    annualized : bool
        If True, growth is annualized; convert to quarterly: (1+g)^(1/4) - 1.

    Returns
    -------
    levels : (T,) array
        GDP levels compounded from base.
    """
    T = len(growth_forecast)
    levels = np.full(T, np.nan)
    levels[0] = base_level * (1 + growth_forecast[0] / 4)  # annualised → quarterly

    for t in range(1, T):
        levels[t] = levels[t - 1] * (1 + growth_forecast[t] / 4)

    return levels


def compute_confidence_bands(
    Z_smooth: FloatArray,
    V_smooth: FloatArray,
    C: FloatArray,
    gdp_col: int = -1,
    alpha: float = 0.32,  # ~1 std (68% band)
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Extract GDP nowcast with model-implied confidence bands.

    Parameters
    ----------
    Z_smooth : (T, K) smoothed states
    V_smooth : (T, K, K) smoothed state covariances
    C : (N, K) observation matrix
    gdp_col : int
        Column index for GDP in C (default -1 = last).
    alpha : float
        Significance level for band width.

    Returns
    -------
    central : (T,) central estimate
    lower : (T,) lower band
    upper : (T,) upper band
    """
    T = Z_smooth.shape[0]
    c = C[gdp_col, :]

    central = Z_smooth @ c
    std = np.zeros(T)
    for t in range(T):
        std[t] = np.sqrt(c @ V_smooth[t] @ c + 1e-10)

    from scipy.stats import norm
    z = norm.ppf(1 - alpha / 2)

    lower = central - z * std
    upper = central + z * std

    return central, lower, upper


def bootstrap_range(
    X_sm: FloatArray,
    n_boot: int = 200,
    seed: int = 42,
) -> FloatArray:
    """Parametric bootstrap range estimation (mirrors common_range.m).

    Resamples residuals from the smoothed state series to generate
    confidence bands, preserving temporal structure.

    Parameters
    ----------
    X_sm : (T, N) smoothed data matrix
    n_boot : number of bootstrap draws
    seed : random seed

    Returns
    -------
    (T, 2) array with [lower, upper] bounds for GDP column (16th/84th percentiles)
    """
    rng = np.random.default_rng(seed)
    T, N = X_sm.shape
    gdp = X_sm[:, -1]

    # Estimate residuals (first differences of smoothed series)
    resid = np.diff(gdp, prepend=gdp[0])
    resid_centered = resid - np.mean(resid)

    # Parametric bootstrap: resample residuals and reconstruct paths
    boot_samples = np.zeros((n_boot, T))
    for b in range(n_boot):
        # Resample residuals with replacement
        idx = rng.choice(len(resid_centered), size=T, replace=True)
        boot_resid = resid_centered[idx]
        # Reconstruct path from initial value
        boot_samples[b] = gdp[0] + np.cumsum(boot_resid)

    lower = np.percentile(boot_samples, 16, axis=0)
    upper = np.percentile(boot_samples, 84, axis=0)

    return np.column_stack([lower, upper])
