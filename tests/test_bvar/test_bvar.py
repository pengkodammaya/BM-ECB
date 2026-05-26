"""Tests for BVAR csminwel optimizer and estimation."""

import numpy as np
import pytest
from nowcasting_toolbox.bvar.optimize import csminwel
from nowcasting_toolbox.bvar.prior import make_dummy_observations, minnesota_posterior


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
