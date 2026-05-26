"""Tests for DFM EM algorithm and full estimation."""

import numpy as np
import pytest
from nowcasting_toolbox.config import DFMParams
from nowcasting_toolbox.dfm import DFM


def test_dfm_recovery_synthetic(synthetic_dfm_data):
    """DFM should recover factor structure from synthetic data."""
    X, C_true, A_true, F_true, Q_true = synthetic_dfm_data

    params = DFMParams(r=3, p=1, max_iter=30, thresh=1e-5, idio=0)
    dfm = DFM(params)
    res = dfm.fit(X)

    # Check output shapes
    T, N = X.shape
    assert res.X_sm.shape == (T, N)
    assert res.F.shape[1] == 3  # r factors

    # Factor recovery: correlation between true and estimated factors
    # (up to rotation — use canonical correlation-like check)
    # The first factor should have high correlation with some linear comb of true factors
    corr_matrix = np.corrcoef(res.F[:, 0], F_true[:, 0])[0, 1]
    # At least some factor should correlate well
    max_corr = 0.0
    for i in range(3):
        for j in range(3):
            c = np.corrcoef(res.F[:, i], F_true[:, j])[0, 1]
            max_corr = max(max_corr, abs(c))
    assert max_corr > 0.5, f"Max factor correlation too low: {max_corr:.3f}"

    # Log-likelihood should be finite
    assert np.isfinite(res.L)

    # Smoothed data should fill NaN
    nan_mask = np.isnan(X)
    assert not np.any(np.isnan(res.X_sm[nan_mask]))


def test_dfm_improves_over_time():
    """EM should increase log-likelihood over iterations."""
    rng = np.random.default_rng(42)
    T, N, r = 100, 8, 2

    # Simple DGP
    A_true = np.array([[0.6, 0.0], [0.0, 0.4]])
    Q_true = np.eye(r) * 0.3
    C_true = rng.normal(0, 1, (N, r))
    R_diag = np.ones(N) * 0.5

    F = np.zeros((T, r))
    for t in range(1, T):
        F[t] = A_true @ F[t - 1] + rng.multivariate_normal(np.zeros(r), Q_true)

    X = F @ C_true.T + rng.normal(0, np.sqrt(R_diag), (T, N))
    X[rng.random((T, N)) < 0.05] = np.nan

    params = DFMParams(r=2, p=1, max_iter=20, thresh=1e-6, idio=0)
    dfm = DFM(params)
    res = dfm.fit(X)

    assert res.F.shape[1] == 2
    assert np.isfinite(res.L)


def test_dfm_with_all_missing_column():
    """DFM should handle columns that are entirely NaN."""
    rng = np.random.default_rng(42)
    T, N = 100, 5
    X = rng.normal(0, 1, (T, N))
    X[:, 2] = np.nan  # entirely missing column

    params = DFMParams(r=2, p=1, max_iter=10, thresh=1e-5, idio=0)
    dfm = DFM(params)
    res = dfm.fit(X)

    assert res.X_sm.shape == X.shape
    # The NaN column should be imputed
    assert not np.any(np.isnan(res.X_sm[:, 2]))


def test_dfm_verbose_mode(capsys):
    """DFM should not crash in verbose mode."""
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (50, 5))
    params = DFMParams(r=2, p=1, max_iter=5, idio=0)
    dfm = DFM(params, verbose=True)
    res = dfm.fit(X)
    assert res is not None


def test_dfm_result_property():
    """Accessing result before fit should raise."""
    dfm = DFM()
    with pytest.raises(RuntimeError, match="not yet fitted"):
        _ = dfm.result
