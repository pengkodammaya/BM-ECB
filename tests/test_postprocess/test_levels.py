"""Tests for postprocessing (growth-to-level conversion, bootstrap)."""

import numpy as np
import pytest

from nowcasting_toolbox.postprocess.levels import growth_to_level, bootstrap_range


def test_growth_to_level_basic():
    """growth_to_level should convert growth rates to levels."""
    growth_forecast = np.array([0.04, 0.08, 0.06])  # 4%, 8%, 6% annualized
    base_level = 100.0

    levels = growth_to_level(growth_forecast, base_level)

    assert len(levels) == len(growth_forecast)
    # 4% annualized = 1% quarterly -> 100 * 1.01 = 101
    assert levels[0] == pytest.approx(101.0, rel=1e-6)
    assert all(levels > 0)


def test_growth_to_level_zero_growth():
    """Zero growth should return constant levels."""
    growth_forecast = np.array([0.0, 0.0, 0.0])
    base_level = 100.0

    levels = growth_to_level(growth_forecast, base_level)

    np.testing.assert_allclose(levels, 100.0, rtol=1e-6)


def test_growth_to_level_negative_growth():
    """Negative growth should reduce levels."""
    growth_forecast = np.array([-0.04, -0.08])
    base_level = 100.0

    levels = growth_to_level(growth_forecast, base_level)

    assert levels[0] < base_level
    assert levels[1] < levels[0]


def test_bootstrap_range_returns_array():
    """bootstrap_range should return a (T, 2) array."""
    X_sm = np.random.default_rng(42).normal(0, 1, (100, 4))
    result = bootstrap_range(X_sm, n_boot=50, seed=42)

    assert isinstance(result, np.ndarray)
    assert result.shape == (100, 2)


def test_bootstrap_range_has_percentiles():
    """Result should contain lower and upper bounds."""
    rng = np.random.default_rng(42)
    X_sm = rng.normal(0, 1, (100, 4))
    result = bootstrap_range(X_sm, n_boot=100, seed=42)

    # Lower should be less than upper
    assert np.all(result[:, 0] <= result[:, 1])


def test_bootstrap_range_reproducible():
    """Same seed should give same results."""
    rng = np.random.default_rng(42)
    X_sm = rng.normal(0, 1, (100, 4))

    r1 = bootstrap_range(X_sm, n_boot=50, seed=42)
    r2 = bootstrap_range(X_sm, n_boot=50, seed=42)

    np.testing.assert_array_equal(r1, r2)


def test_bootstrap_range_different_seeds():
    """Different seeds should give different results."""
    rng = np.random.default_rng(42)
    X_sm = rng.normal(0, 1, (100, 4))

    r1 = bootstrap_range(X_sm, n_boot=50, seed=42)
    r2 = bootstrap_range(X_sm, n_boot=50, seed=123)

    assert not np.array_equal(r1, r2)
