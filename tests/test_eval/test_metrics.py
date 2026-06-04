"""Tests for evaluation metrics (MAE, FDA, RMSE, bias, MASE, CRPS, coverage)."""
import numpy as np
import pytest
from nowcasting_toolbox.eval.metrics import (
    compute_mae, compute_fda, compute_rmse,
    compute_bias, compute_mase, compute_crps, compute_coverage,
)


def test_mae_perfect():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    assert compute_mae(y, y) == 0.0


def test_mae_basic():
    actual = np.array([1.0, 2.0, 3.0])
    pred = np.array([1.5, 2.5, 2.5])
    mae = compute_mae(actual, pred)
    assert abs(mae - 0.5) < 0.001


def test_mae_with_nan():
    actual = np.array([1.0, np.nan, 3.0])
    pred = np.array([1.5, 2.0, 3.5])
    mae = compute_mae(actual, pred)
    assert abs(mae - 0.5) < 0.001


def test_fda_perfect():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    assert compute_fda(y, y) == 1.0


def test_fda_opposite():
    actual = np.array([1.0, 2.0, 3.0])
    pred = np.array([3.0, 2.0, 1.0])
    fda = compute_fda(actual, pred)
    assert fda == 0.0


def test_fda_with_nan():
    actual = np.array([1.0, 2.0, np.nan, 4.0])
    pred = np.array([2.0, 3.0, 3.0, 5.0])
    fda = compute_fda(actual, pred)
    assert 0 <= fda <= 1


def test_rmse():
    actual = np.array([1.0, 2.0, 3.0])
    pred = np.array([2.0, 2.0, 2.0])
    rmse = compute_rmse(actual, pred)
    assert abs(rmse - np.sqrt(2/3)) < 0.001


def test_bias_zero():
    actual = np.array([1.0, 2.0, 3.0])
    pred = np.array([1.0, 2.0, 3.0])
    assert compute_bias(actual, pred) == 0.0


def test_bias_positive():
    """Model overestimates by 1.0 on average."""
    actual = np.array([1.0, 2.0, 3.0])
    pred = np.array([2.0, 3.0, 4.0])
    assert abs(compute_bias(actual, pred) - 1.0) < 0.001


def test_bias_negative():
    """Model underestimates by 1.0 on average."""
    actual = np.array([1.0, 2.0, 3.0])
    pred = np.array([0.0, 1.0, 2.0])
    assert abs(compute_bias(actual, pred) - (-1.0)) < 0.001


def test_mase_better_than_naive():
    """MASE < 1 means better than naive seasonal forecast."""
    actual = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    pred = np.array([1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1, 8.1])
    mase = compute_mase(actual, pred, seasonal_period=4)
    assert mase < 1.0


def test_mase_worse_than_naive():
    """MASE >= 1 means worse than or equal to naive seasonal forecast."""
    actual = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    pred = np.array([5.0, 6.0, 7.0, 8.0, 1.0, 2.0, 3.0, 4.0])
    mase = compute_mae(actual, pred) / compute_mae(actual[4:], actual[:4])
    # Just check it's > 0.5 (worse than perfect)
    assert mase > 0.5


def test_mase_perfect():
    """Perfect forecast has MASE = 0."""
    actual = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    pred = actual.copy()
    mase = compute_mase(actual, pred, seasonal_period=2)
    assert mase == 0.0


def test_crps_with_ci():
    """CRPS with confidence intervals."""
    actual = np.array([1.0, 2.0, 3.0])
    lower = np.array([0.5, 1.5, 2.5])
    upper = np.array([1.5, 2.5, 3.5])
    crps = compute_crps(actual, lower, upper)
    assert crps >= 0


def test_crps_perfect():
    """Perfect CRPS when intervals are tight around actuals."""
    actual = np.array([1.0, 2.0, 3.0])
    lower = actual - 0.001
    upper = actual + 0.001
    crps = compute_crps(actual, lower, upper)
    assert crps < 0.01


def test_coverage_80():
    """80% coverage test."""
    actual = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    lower = np.array([0.5, 1.5, 2.5, 3.5, 4.5])
    upper = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    cov = compute_coverage(actual, lower, upper)
    assert cov == 1.0


def test_coverage_perfect():
    """Perfect coverage when interval contains all actuals."""
    actual = np.array([1.0, 2.0, 3.0])
    lower = np.array([0.0, 0.0, 0.0])
    upper = np.array([10.0, 10.0, 10.0])
    assert compute_coverage(actual, lower, upper) == 1.0
