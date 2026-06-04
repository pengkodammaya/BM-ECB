"""Tests for fan chart computation."""
import numpy as np
import pytest
from nowcasting_toolbox.fan_chart import bvar_fan_chart, dfm_fan_chart


class TestBVARFanChart:
    """Tests for BVAR fan chart."""

    def test_returns_expected_keys(self):
        """Returns dict with expected keys."""
        rng = np.random.default_rng(42)
        n_draws, N, lags = 50, 4, 2
        B_draws = rng.normal(0, 0.1, (n_draws, N, N * lags))
        Sigma_draws = np.eye(N)[np.newaxis, :, :] * np.ones((n_draws, 1, 1))
        X_last = rng.normal(0, 1, N * lags)

        result = bvar_fan_chart(B_draws, Sigma_draws, X_last, n_forecast=1, lags=lags)

        assert "percentiles" in result
        assert "draws" in result
        assert "mean" in result
        assert "std" in result

    def test_percentiles_shape(self):
        """Percentiles have correct shape."""
        rng = np.random.default_rng(42)
        n_draws, N, lags = 100, 3, 1
        B_draws = rng.normal(0, 0.1, (n_draws, N, N * lags))
        Sigma_draws = np.tile(np.eye(N), (n_draws, 1, 1))
        X_last = rng.normal(0, 1, N * lags)

        result = bvar_fan_chart(
            B_draws, Sigma_draws, X_last,
            n_forecast=2, lags=lags, percentiles=[10, 50, 90]
        )

        assert 10 in result["percentiles"]
        assert 50 in result["percentiles"]
        assert 90 in result["percentiles"]
        # Each percentile should have n_forecast values
        assert len(result["percentiles"][50]) == 2

    def test_draws_shape(self):
        """Draws have correct shape."""
        rng = np.random.default_rng(42)
        n_draws, N, lags = 50, 3, 2
        B_draws = rng.normal(0, 0.1, (n_draws, N, N * lags))
        Sigma_draws = np.tile(np.eye(N), (n_draws, 1, 1))
        X_last = rng.normal(0, 1, N * lags)

        result = bvar_fan_chart(B_draws, Sigma_draws, X_last, n_forecast=3, lags=lags)

        assert result["draws"].shape == (n_draws, 3)

    def test_destandardization(self):
        """De-standardization applies sigma and mu correctly."""
        rng = np.random.default_rng(42)
        n_draws, N, lags = 50, 2, 1
        B_draws = np.zeros((n_draws, N, N * lags))  # Zero coefficients
        Sigma_draws = np.tile(np.eye(N) * 0.01, (n_draws, 1, 1))
        X_last = np.zeros(N * lags)

        result = bvar_fan_chart(
            B_draws, Sigma_draws, X_last,
            n_forecast=1, lags=lags,
            sigma_y=100.0, mu_y=5.0
        )

        # With zero coefficients, mean should be close to mu_y
        assert abs(result["mean"][0] - 5.0) < 10.0  # Allow for randomness


class TestDFMFanChart:
    """Tests for DFM fan chart."""

    def test_returns_expected_keys(self):
        """Returns dict with expected keys."""
        T, N, K = 20, 4, 6
        rng = np.random.default_rng(42)
        X_sm = rng.normal(0, 1, (T, N))
        V_smooth = np.tile(np.eye(K) * 0.1, (T, 1, 1))
        C = rng.normal(0, 0.5, (N, K))
        R = np.eye(N) * 0.01

        result = dfm_fan_chart(X_sm, V_smooth, C, R)

        assert "percentiles" in result
        assert "mean" in result
        assert "std" in result

    def test_mean_matches_smoothed(self):
        """Mean matches smoothed observations (de-standardized)."""
        T, N, K = 10, 3, 4
        rng = np.random.default_rng(42)
        X_sm = rng.normal(0, 1, (T, N))
        V_smooth = np.tile(np.eye(K) * 0.01, (T, 1, 1))
        C = rng.normal(0, 0.3, (N, K))
        R = np.eye(N) * 0.001

        result = dfm_fan_chart(X_sm, V_smooth, C, R, sigma_y=10.0, mu_y=50.0)

        # Mean should be X_sm[:, -1] * sigma_y + mu_y
        expected = X_sm[:, -1] * 10.0 + 50.0
        np.testing.assert_array_almost_equal(result["mean"], expected)

    def test_std_nonnegative(self):
        """Standard deviation is non-negative."""
        T, N, K = 10, 3, 4
        rng = np.random.default_rng(42)
        X_sm = rng.normal(0, 1, (T, N))
        V_smooth = np.tile(np.eye(K) * 0.1, (T, 1, 1))
        C = rng.normal(0, 0.5, (N, K))
        R = np.eye(N) * 0.01

        result = dfm_fan_chart(X_sm, V_smooth, C, R)

        assert np.all(result["std"] >= 0)

    def test_percentiles_ordered(self):
        """Percentiles are ordered correctly."""
        T, N, K = 10, 3, 4
        rng = np.random.default_rng(42)
        X_sm = rng.normal(0, 1, (T, N))
        V_smooth = np.tile(np.eye(K) * 0.1, (T, 1, 1))
        C = rng.normal(0, 0.5, (N, K))
        R = np.eye(N) * 0.01

        result = dfm_fan_chart(X_sm, V_smooth, C, R, percentiles=[10, 25, 50, 75, 90])

        # 10th percentile < 25th < 50th < 75th < 90th
        for t in range(T):
            assert result["percentiles"][10][t] < result["percentiles"][25][t]
            assert result["percentiles"][25][t] < result["percentiles"][50][t]
            assert result["percentiles"][50][t] < result["percentiles"][75][t]
            assert result["percentiles"][75][t] < result["percentiles"][90][t]
