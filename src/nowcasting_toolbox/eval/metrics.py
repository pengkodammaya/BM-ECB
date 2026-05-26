"""Model evaluation metrics: MAE, FDA, RMSE."""

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

    correct = np.sign(act_change) == np.sign(pred_change)
    # Also count zero-change as correct if both are zero
    both_zero = (act_change == 0) & (pred_change == 0)
    return float(np.mean(correct | both_zero))
