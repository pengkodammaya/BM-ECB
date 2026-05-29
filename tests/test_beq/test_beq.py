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


def _make_beq_data(T=36, n_monthly=3, seed=42):
    """Create synthetic mixed-frequency data for BEQ testing."""
    rng = np.random.default_rng(seed)

    # Monthly data
    X_monthly = rng.normal(0, 1, (T, n_monthly))

    # Quarterly GDP (observed at quarter-end months)
    X_qtr = np.full(T, np.nan)
    for t in range(2, T, 3):
        # GDP = sum of monthly effects + noise
        X_qtr[t] = np.sum(X_monthly[t]) * 0.3 + rng.normal(0, 0.5)

    X = np.column_stack([X_monthly, X_qtr])
    return X


def _make_datet(T=36, start_year=2020, start_month=1):
    """Create date array for testing."""
    datet = np.zeros((T, 2))
    y, m = start_year, start_month
    for t in range(T):
        datet[t] = [y, m]
        m += 1
        if m > 12:
            m = 1
            y += 1
    return datet


def test_beq_fit_basic():
    """BEQ.fit() should return smoothed values with correct shape."""
    from nowcasting_toolbox.beq import BEQ
    from nowcasting_toolbox.config import BEQParams

    X = _make_beq_data(T=36, n_monthly=3)
    datet = _make_datet(T=36)

    model = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
    result = model.fit(X, datet)

    assert hasattr(result, 'X_sm')
    assert result.X_sm.shape[0] > 0
    assert result.X_sm.shape[1] == X.shape[1]


def test_beq_fit_finite():
    """BEQ.fit() output should be finite where possible."""
    from nowcasting_toolbox.beq import BEQ
    from nowcasting_toolbox.config import BEQParams

    X = _make_beq_data(T=36, n_monthly=3)
    datet = _make_datet(T=36)

    model = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
    result = model.fit(X, datet)

    # Most values should be finite (some NaN is expected for initial observations)
    finite_frac = np.sum(np.isfinite(result.X_sm)) / result.X_sm.size
    assert finite_frac > 0.5


def test_beq_fit_with_nans():
    """BEQ should handle missing data gracefully."""
    from nowcasting_toolbox.beq import BEQ
    from nowcasting_toolbox.config import BEQParams

    X = _make_beq_data(T=36, n_monthly=3)
    datet = _make_datet(T=36)

    # Inject extra NaNs
    X[5:10, 0] = np.nan
    X[15:20, 1] = np.nan

    model = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
    result = model.fit(X, datet)

    assert result.X_sm.shape[0] > 0


def test_beq_fit_different_types():
    """BEQ should work with different interpolation types."""
    from nowcasting_toolbox.beq import BEQ
    from nowcasting_toolbox.config import BEQParams

    X = _make_beq_data(T=36, n_monthly=3)
    datet = _make_datet(T=36)

    for interp_type in [901, 902, 903]:
        model = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=interp_type))
        result = model.fit(X, datet)
        assert result.X_sm.shape[0] > 0


def test_beq_interpolation():
    """BEQ should interpolate monthly values for quarter-end observations."""
    from nowcasting_toolbox.beq.interpolate import extrapolate_bvar

    X = _make_beq_data(T=36, n_monthly=3)

    # This tests the interpolation module directly
    # The function should fill in some missing quarterly values
    result = extrapolate_bvar(X, lags=1)

    assert result.shape == X.shape


def test_beq_interpolation_fallback():
    """BEQ interpolation should fall back to forward-fill when BVAR fails."""
    from nowcasting_toolbox.beq.interpolate import extrapolate_bvar

    # Very few observations — BVAR will fail, should fall back to forward-fill
    T = 36
    X = np.full((T, 2), np.nan)
    X[:5, 0] = np.random.randn(5)
    X[:5, 1] = np.random.randn(5)

    result = extrapolate_bvar(X, method=901)

    # Forward-fill should have filled some values
    assert np.sum(np.isnan(result)) < np.sum(np.isnan(X))


def test_beq_interpolation_single_var():
    """BEQ interpolation should work with single variable."""
    from nowcasting_toolbox.beq.interpolate import extrapolate_bvar

    rng = np.random.default_rng(42)
    T = 36
    X = rng.standard_normal((T, 1))
    X[30:, 0] = np.nan

    result = extrapolate_bvar(X, method=903)

    assert result.shape == X.shape
    assert np.sum(np.isnan(result)) == 0
