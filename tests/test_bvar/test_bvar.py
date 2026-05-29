"""Tests for BVAR csminwel optimizer and estimation."""

import numpy as np
import pytest
from nowcasting_toolbox.bvar.optimize import csminwel
from nowcasting_toolbox.bvar.prior import make_dummy_observations, minnesota_posterior
from nowcasting_toolbox.bvar.bbvar import block_bvar
from nowcasting_toolbox.config import BVARParams


def test_csminwel_quadratic():
    """csminwel should find minimum of a simple quadratic."""
    def f(x):
        return np.sum((x - np.array([3.0, -2.0])) ** 2)

    x0 = np.array([0.0, 0.0])
    x_opt, f_opt, g_opt, H, itct = csminwel(f, x0, crit=1e-8, nit=100)

    assert np.allclose(x_opt, [3.0, -2.0], atol=1e-4)
    assert f_opt < 1e-6
    assert itct < 50


def test_csminwel_quadratic_multidim():
    """csminwel on a 5D quadratic."""
    def f(x):
        return np.sum((x - np.ones(5))**2)

    x0 = np.zeros(5)
    x_opt, f_opt, g_opt, H, itct = csminwel(f, x0, crit=1e-10, nit=100)

    assert f_opt < 1e-6
    assert np.allclose(x_opt, np.ones(5), atol=1e-3)


def test_csminwel_with_gradient():
    """csminwel should work with analytical gradient."""
    def f(x):
        return np.sum(x**2)

    def grad(x):
        return 2 * x

    x0 = np.array([5.0, 5.0, 5.0])
    x_opt, f_opt, g_opt, H, itct = csminwel(f, x0, grad_func=grad, crit=1e-10, nit=200)

    assert np.allclose(x_opt, [0, 0, 0], atol=1e-6)


def test_minnesota_dummy_dimensions():
    """Dummy observations should have the right shape."""
    rng = np.random.default_rng(42)
    Y = rng.normal(0, 1, (100, 5))
    p = 4

    Y_d, X_d = make_dummy_observations(Y, p)

    assert Y_d.shape[1] == 5
    assert X_d.shape[1] == 5 * p
    assert Y_d.shape[0] == X_d.shape[0]


def test_minnesota_posterior():
    """Posterior mean should exist for valid data."""
    rng = np.random.default_rng(42)
    Y = rng.normal(0, 1, (150, 4))
    p = 2

    B_post, Sigma_post = minnesota_posterior(Y, p)

    assert B_post.shape == (4, 4 * p)
    assert Sigma_post.shape == (4, 4)
    assert np.all(np.diag(Sigma_post) > 0)


def _make_var_data(T=100, N=3, p_true=2, seed=42):
    """Generate synthetic VAR(p) data for testing."""
    rng = np.random.default_rng(seed)
    # True VAR coefficients (stable)
    A_true = np.zeros((N, N * p_true))
    A_true[:, :N] = np.array([
        [0.5, 0.1, 0.0],
        [0.0, 0.4, 0.1],
        [0.1, 0.0, 0.3],
    ])

    # Burn-in
    burn = 50
    Y = np.zeros((T + burn, N))
    Y[:p_true] = rng.normal(0, 1, (p_true, N))

    for t in range(p_true, T + burn):
        x_lag = Y[t - p_true:t].flatten()
        Y[t] = A_true @ x_lag + rng.normal(0, 0.5, N)

    return Y[burn:]


def test_block_bvar_shapes():
    """block_bvar should return smoothed values with correct shape."""
    Y = _make_var_data(T=80, N=3, p_true=2)
    m_series = list(range(2))  # first 2 are monthly
    stationary = list(range(3))

    result = block_bvar(Y, lags=2, m_series=m_series, stationary=stationary,
                       thresh=1e-4, max_iter=5)

    assert "X_sm" in result
    assert result["X_sm"].shape == Y.shape
    assert "B_draws" in result
    assert "Sigma_draws" in result


def test_block_bvar_finite_output():
    """block_bvar output should be finite."""
    Y = _make_var_data(T=80, N=3, p_true=2)
    m_series = list(range(2))
    stationary = list(range(3))

    result = block_bvar(Y, lags=2, m_series=m_series, stationary=stationary,
                       thresh=1e-4, max_iter=5)

    assert np.all(np.isfinite(result["X_sm"]))
    assert np.all(np.isfinite(result["B_draws"]))
    assert np.all(np.isfinite(result["Sigma_draws"]))


def test_block_bvar_with_nans():
    """block_bvar should handle missing data."""
    Y = _make_var_data(T=80, N=3, p_true=2)
    # Inject some NaNs
    Y[10:15, 1] = np.nan
    Y[30:35, 0] = np.nan

    m_series = list(range(2))
    stationary = list(range(3))

    result = block_bvar(Y, lags=2, m_series=m_series, stationary=stationary,
                       thresh=1e-4, max_iter=5)

    assert result["X_sm"].shape == Y.shape
    assert np.all(np.isfinite(result["X_sm"]))


def test_block_bvar_gibbs_draws_shape():
    """Gibbs sampler should return draws with correct dimensions."""
    Y = _make_var_data(T=80, N=3, p_true=2)
    m_series = list(range(2))
    stationary = list(range(3))

    result = block_bvar(Y, lags=2, m_series=m_series, stationary=stationary,
                       thresh=1e-4, max_iter=5)

    N = Y.shape[1]
    p = 2
    K = N * p  # lags only (no constant in Gibbs sampler)

    assert result["B_draws"].shape[1:] == (N, K)
    assert result["Sigma_draws"].shape[1:] == (N, N)


def test_bvar_via_api():
    """BVAR class should work via fit() API."""
    from nowcasting_toolbox.bvar import BVAR

    rng = np.random.default_rng(42)
    Y = _make_var_data(T=80, N=3, p_true=2)
    # Add a quarterly column (NaN in non-quarter months)
    T = Y.shape[0]
    Y_qtr = np.full((T, 1), np.nan)
    for t in range(2, T, 3):
        Y_qtr[t] = rng.normal(0, 1)
    X = np.column_stack([Y, Y_qtr])

    datet = np.array([[2020 + (t + 1) // 12, (t % 12) + 1] for t in range(T)], dtype=float)

    model = BVAR(BVARParams(bvar_lags=2, bvar_max_iter=5))
    result = model.fit(X, datet)

    assert result.X_sm.shape == X.shape
    assert np.all(np.isfinite(result.X_sm[~np.isnan(X)]))
