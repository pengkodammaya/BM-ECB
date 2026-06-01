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
