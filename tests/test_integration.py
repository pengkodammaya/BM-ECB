"""Integration tests for the nowcasting pipeline.

Tests the full workflow: data loading → transformation → model fitting → ensemble.
Uses synthetic data to avoid API dependencies.
"""
import numpy as np
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock


def _make_synthetic_data(T=48, n_monthly=8, seed=42):
    """Create synthetic mixed-frequency data for integration testing."""
    rng = np.random.default_rng(seed)

    # Monthly indicators
    X_monthly = rng.normal(0, 1, (T, n_monthly))

    # Quarterly GDP (observed at quarter-end months: 3, 6, 9, 12)
    X_qtr = np.full(T, np.nan)
    for t in range(2, T, 3):
        # GDP = weighted sum of monthly indicators + noise
        weights = rng.normal(0, 0.3, n_monthly)
        X_qtr[t] = np.sum(X_monthly[t] * weights) + rng.normal(0, 0.5)

    X = np.column_stack([X_monthly, X_qtr])
    return X


def _make_datet(T=48, start_year=2020, start_month=1):
    """Create date array for testing."""
    dates = []
    year, month = start_year, start_month
    for _ in range(T):
        dates.append([year, month])
        month += 1
        if month > 12:
            month = 1
            year += 1
    return np.array(dates)


class TestDFMIntegration:
    """Integration tests for DFM model."""

    def test_dfm_fit_and_predict(self):
        """DFM fits synthetic data and produces predictions."""
        from nowcasting_toolbox.dfm import DFM
        from nowcasting_toolbox.config import DFMParams

        X = _make_synthetic_data()
        dfm = DFM(DFMParams(r=2, p=2, max_iter=20, thresh=1e-4, idio=1))
        result = dfm.fit(X)

        assert result is not None
        assert result.X_sm is not None
        assert result.X_sm.shape == X.shape
        # Smoothed values should be finite where we have data
        assert np.any(np.isfinite(result.X_sm))

    def test_dfm_with_all_nan_column(self):
        """DFM handles all-NaN column gracefully."""
        from nowcasting_toolbox.dfm import DFM
        from nowcasting_toolbox.config import DFMParams

        X = _make_synthetic_data()
        X[:, 0] = np.nan  # All NaN column

        dfm = DFM(DFMParams(r=2, p=2, max_iter=20, thresh=1e-4, idio=1))
        result = dfm.fit(X)

        assert result is not None
        assert result.X_sm.shape == X.shape

    def test_dfm_different_configs(self):
        """DFM works with different factor/lag configurations."""
        from nowcasting_toolbox.dfm import DFM
        from nowcasting_toolbox.config import DFMParams

        X = _make_synthetic_data(T=36)

        for r, p in [(1, 1), (2, 2), (3, 1)]:
            dfm = DFM(DFMParams(r=r, p=p, max_iter=10, thresh=1e-3, idio=1))
            result = dfm.fit(X)
            assert result is not None


class TestBVARIntegration:
    """Integration tests for BVAR model."""

    def test_bvar_fit_basic(self):
        """BVAR fits synthetic data."""
        from nowcasting_toolbox.bvar import BVAR
        from nowcasting_toolbox.config import BVARParams

        X = _make_synthetic_data(T=36)
        datet = _make_datet(T=36)

        bvar = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-3, bvar_max_iter=5, bvar_n_draws=10))
        result = bvar.fit(X, datet)

        assert result is not None
        assert result.X_sm is not None
        assert result.X_sm.shape == X.shape

    def test_bvar_without_datet(self):
        """BVAR works without datet (no quarter-block restructuring)."""
        from nowcasting_toolbox.bvar import BVAR
        from nowcasting_toolbox.config import BVARParams

        X = _make_synthetic_data(T=36)

        bvar = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-3, bvar_max_iter=5, bvar_n_draws=10))
        result = bvar.fit(X)

        assert result is not None
        assert result.X_sm.shape == X.shape


class TestBEQIntegration:
    """Integration tests for BEQ model."""

    def test_beq_fit_basic(self):
        """BEQ fits synthetic data."""
        from nowcasting_toolbox.beq import BEQ
        from nowcasting_toolbox.config import BEQParams

        X = _make_synthetic_data(T=36)
        datet = _make_datet(T=36)
        names = [f"x{i}" for i in range(8)] + ["gdp"]

        beq = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
        result = beq.fit(X, datet, names)

        assert result is not None
        assert result.X_sm is not None
        assert result.X_sm.shape == X.shape


class TestEnsembleIntegration:
    """Integration tests for ensemble combination."""

    def test_ensemble_with_all_models(self):
        """Ensemble combines predictions from all models."""
        from nowcasting_toolbox.ensemble import Ensemble

        ens = Ensemble(method="median")
        result = ens.predict({"dfm": 5.0, "bvar": 3.0, "beq": 4.0})

        assert result.prediction == 4.0
        assert len(result.weights) == 3

    def test_ensemble_with_missing_model(self):
        """Ensemble handles missing model predictions."""
        from nowcasting_toolbox.ensemble import Ensemble

        ens = Ensemble(method="median")
        result = ens.predict({"dfm": 5.0, "bvar": None, "beq": 4.0})

        assert result.prediction == 4.5  # median of 4.0, 5.0

    def test_ensemble_direction_vote(self):
        """Direction vote ensemble picks majority direction."""
        from nowcasting_toolbox.ensemble import Ensemble

        ens = Ensemble(method="direction_vote")
        result = ens.predict({"dfm": 5.0, "bvar": 3.0, "beq": -1.0})

        # 2 positive, 1 negative -> average positive
        assert result.prediction > 0
        assert result.prediction == 4.0


class TestMetricsIntegration:
    """Integration tests for evaluation metrics."""

    def test_compute_all_metrics(self):
        """All metrics compute without error."""
        from nowcasting_toolbox.eval.metrics import (
            compute_mae, compute_rmse, compute_fda,
            compute_bias, compute_mase, compute_crps, compute_coverage,
        )

        actual = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        pred = np.array([1.1, 2.2, 2.8, 4.1, 4.9])
        lower = pred - 0.5
        upper = pred + 0.5

        assert compute_mae(actual, pred) >= 0
        assert compute_rmse(actual, pred) >= 0
        assert 0 <= compute_fda(actual, pred) <= 1
        assert isinstance(compute_bias(actual, pred), float)
        assert compute_mase(actual, pred, seasonal_period=2) >= 0
        assert compute_crps(actual, lower, upper) >= 0
        assert 0 <= compute_coverage(actual, lower, upper) <= 1


class TestTransformsIntegration:
    """Integration tests for data transformations."""

    def test_all_transform_codes(self):
        """All transform codes produce valid output."""
        from nowcasting_toolbox.data.transforms import transform_series

        x = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0,
                       106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0])

        for code in range(5):
            result = transform_series(x, code, "monthly")
            assert len(result) == len(x)
            # Should have at least some finite values
            assert np.any(np.isfinite(result))

    def test_transform_preserves_length(self):
        """Transforms preserve array length."""
        from nowcasting_toolbox.data.transforms import transform_series

        x = np.random.default_rng(42).normal(100, 10, 50)

        for code in range(5):
            result = transform_series(x, code, "monthly")
            assert len(result) == len(x)


class TestVariableSelectionIntegration:
    """Integration tests for variable selection."""

    def test_all_methods_work(self):
        """All selection methods produce valid rankings."""
        from nowcasting_toolbox.selection.variable_selection import select_variables

        rng = np.random.default_rng(42)
        X = rng.normal(0, 1, (50, 10))
        y = X[:, 0] * 2 + X[:, 1] * 0.5 + rng.normal(0, 0.5, 50)

        for method in ["correlation", "tstat", "lars"]:
            result = select_variables(X, y, method=method, n_select=5)
            assert len(result) == 5
            assert "variable" in result.columns
            assert "score" in result.columns
            # First ranked variable should have highest absolute score
            assert abs(result.iloc[0]["score"]) >= abs(result.iloc[-1]["score"])
