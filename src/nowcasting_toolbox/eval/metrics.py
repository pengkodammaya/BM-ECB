"""Model evaluation metrics: MAE, RMSE, FDA, MASE, Bias, CRPS."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def compute_mae(actual: FloatArray, predicted: FloatArray) -> float:
    """Mean Absolute Error."""
    mask = ~np.isnan(actual) & ~np.isnan(predicted)
    if not np.any(mask):
        return np.nan
    return float(np.mean(np.abs(actual[mask] - predicted[mask])))


def compute_rmse(actual: FloatArray, predicted: FloatArray) -> float:
    """Root Mean Squared Error."""
    mask = ~np.isnan(actual) & ~np.isnan(predicted)
    if not np.any(mask):
        return np.nan
    return float(np.sqrt(np.mean((actual[mask] - predicted[mask]) ** 2)))


def compute_fda(actual: FloatArray, predicted: FloatArray) -> float:
    """Forecast Directional Accuracy — fraction of correct sign predictions.

    FDA = fraction of periods where sign(predicted[t] - actual[t-1])
          matches sign(actual[t] - actual[t-1]).

    Ties (zero change) are excluded from the count:
    - If actual change = 0, skip (no direction to predict)
    - If predicted change = 0 but actual change != 0, count as wrong
    """
    mask = ~np.isnan(actual) & ~np.isnan(predicted)
    if np.sum(mask) < 2:
        return np.nan

    act = actual[mask]
    pred = predicted[mask]

    act_change = np.diff(act)
    pred_change = np.diff(pred)

    n = len(act_change)
    if n == 0:
        return np.nan

    # Exclude periods where actual has no change (no direction to predict)
    has_direction = act_change != 0
    if not np.any(has_direction):
        return np.nan

    act_dir = act_change[has_direction]
    pred_dir = pred_change[has_direction]

    correct = np.sign(act_dir) == np.sign(pred_dir)
    return float(np.mean(correct))


def compute_bias(actual: FloatArray, predicted: FloatArray) -> float:
    """Mean Error (Bias) — average signed error.

    Positive bias = model overestimates on average.
    Negative bias = model underestimates on average.
    """
    mask = ~np.isnan(actual) & ~np.isnan(predicted)
    if not np.any(mask):
        return np.nan
    return float(np.mean(predicted[mask] - actual[mask]))


def compute_mase(actual: FloatArray, predicted: FloatArray, seasonal_period: int = 1) -> float:
    """Mean Absolute Scaled Error.

    MASE = MAE / MAE_naive, where MAE_naive is from a naive seasonal forecast.
    - MASE < 1: better than naive
    - MASE = 1: same as naive
    - MASE > 1: worse than naive

    For quarterly GDP: seasonal_period=4 (annual seasonality).
    For monthly data: seasonal_period=12.
    """
    mask = ~np.isnan(actual) & ~np.isnan(predicted)
    if not np.any(mask):
        return np.nan

    act = actual[mask]
    pred = predicted[mask]

    mae_model = np.mean(np.abs(act - pred))

    # Naive seasonal forecast: actual[t - seasonal_period]
    if len(act) <= seasonal_period:
        return np.nan

    naive_errors = np.abs(act[seasonal_period:] - act[:-seasonal_period])
    mae_naive = np.mean(naive_errors)

    if mae_naive < 1e-10:
        return np.nan

    return float(mae_model / mae_naive)


def compute_crps(actual: FloatArray, predicted: FloatArray, 
                 lower: FloatArray | None = None, upper: FloatArray | None = None,
                 n_samples: int = 1000) -> float:
    """Continuous Ranked Probability Score.

    If lower/upper bounds provided, uses empirical distribution.
    Otherwise, assumes normal distribution centered on predicted with
    std estimated from historical errors.

    Lower CRPS = better calibrated forecast.
    """
    mask = ~np.isnan(actual) & ~np.isnan(predicted)
    if not np.any(mask):
        return np.nan

    act = actual[mask]
    pred = predicted[mask]

    if lower is not None and upper is not None:
        # Use provided confidence interval
        lower = lower[mask]
        upper = upper[mask]
        # Estimate std from CI (assuming normal, 80% CI = ±1.28σ)
        std = (upper - lower) / (2 * 1.28)
        std = np.maximum(std, 1e-6)  # avoid zero
    else:
        # Estimate std from residuals
        residuals = pred - act
        std = np.std(residuals)
        if std < 1e-10:
            std = 1e-6
        std = np.full_like(pred, std)

    # Monte Carlo CRPS
    rng = np.random.default_rng(42)
    crps_values = np.zeros(len(act))
    for i in range(len(act)):
        # Generate samples from forecast distribution
        samples = rng.normal(pred[i], std[i], n_samples)
        # CRPS = E|X - y| - 0.5 * E|X - X'|
        term1 = np.mean(np.abs(samples - act[i]))
        term2 = 0.5 * np.mean(np.abs(samples[:, None] - samples[None, :]))
        crps_values[i] = term1 - term2

    return float(np.mean(crps_values))


def compute_coverage(actual: FloatArray, lower: FloatArray, upper: FloatArray) -> float:
    """Coverage of prediction interval.

    Returns fraction of actuals falling within [lower, upper].
    For 80% CI, target coverage = 0.80.
    """
    mask = ~np.isnan(actual) & ~np.isnan(lower) & ~np.isnan(upper)
    if not np.any(mask):
        return np.nan

    act = actual[mask]
    lo = lower[mask]
    hi = upper[mask]

    covered = (act >= lo) & (act <= hi)
    return float(np.mean(covered))
