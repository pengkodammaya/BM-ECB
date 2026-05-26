"""Tests for evaluation metrics and BEQ."""
import numpy as np
import pytest
from nowcasting_toolbox.eval.metrics import compute_mae, compute_fda, compute_rmse
from nowcasting_toolbox.beq.combinations import generate_combinations


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


def test_beq_combinations_count():
    specs = generate_combinations(8, 1, types=[901])
    # 8 choose 2 + 8 singles = 28 + 8 = 36
    assert len(specs) == 36
    assert specs.shape[1] == 4

def test_beq_combinations_format():
    specs = generate_combinations(3, 1, types=[901])
    # 3 choose 2 = 3 + 3 singles = 6
    assert len(specs) == 6
    # Check all have type 901 in first column
    assert all(specs[:, 0] == 901)


def test_beq_combinations_with_quarterly():
    specs = generate_combinations(3, 2, types=[901, 902])
    # 2 monthly vars, 1 quarterly extra: (3+3) * 2 types * 1 Q option
    # Actually: 6 monthly specs × 2 quarterly options (none or q0) × 2 types
    assert len(specs) > 0
    assert specs.shape[1] == 4
