"""Tests for DFM Kalman filter/smoother."""

import numpy as np
import pytest
from nowcasting_toolbox.dfm.kalman import kalman_filter_smoother, kalman_filter, kalman_loglikelihood


def test_kalman_known_ar1():
    """KF should recover states of a simple AR(1) process."""
    rng = np.random.default_rng(42)
    T = 200

    # True state: AR(1) with phi=0.8
    phi = 0.8
    sigma_v = 0.5
    A = np.array([[phi]])
    Q = np.array([[sigma_v**2]])
    C = np.array([[1.0]])
    R = np.array([[0.3]])

    z_true = np.zeros(T)
    eps = rng.normal(0, sigma_v, T)
    for t in range(1, T):
        z_true[t] = phi * z_true[t - 1] + eps[t]

    y = z_true + rng.normal(0, np.sqrt(0.3), T)
    y = y.reshape(1, T)

    Z_0 = np.zeros(1)
    V_0 = np.eye(1) * 1.0

    Z_smooth, _ = kalman_filter_smoother(y, A, C, Q, R, Z_0, V_0)

    corr = np.corrcoef(Z_smooth[:, 0], z_true)[0, 1]
    assert corr > 0.8, f"State recovery correlation too low: {corr:.3f}"


def test_kalman_with_nan():
    """KF should handle NaN observations by skipping update."""
    T = 100
    K = 2
    N = 3

    A = np.array([[0.6, 0.0], [0.0, 0.4]])
    Q = np.eye(K) * 0.2
    C = np.array([[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]])
    R = np.eye(N) * 0.5

    rng = np.random.default_rng(42)
    Z = np.zeros((T, K))
    for t in range(1, T):
        Z[t] = A @ Z[t - 1] + rng.multivariate_normal(np.zeros(K), Q)

    y = Z @ C.T + rng.normal(0, np.sqrt(0.5), (T, N))
    y = y.T  # (N, T)

    # Punch some NaNs
    y[0, 10:20] = np.nan
    y[1, 40:60] = np.nan

    Z_0 = np.zeros(K)
    V_0 = np.eye(K)

    Z_smooth, _ = kalman_filter_smoother(y, A, C, Q, R, Z_0, V_0)

    # States should be recovered well despite missing data
    corr0 = np.corrcoef(Z_smooth[:, 0], Z[:, 0])[0, 1]
    corr1 = np.corrcoef(Z_smooth[:, 1], Z[:, 1])[0, 1]
    assert corr0 > 0.55, f"Factor 0 recovery: {corr0:.3f}"
    assert corr1 > 0.40, f"Factor 1 recovery: {corr1:.3f}"


def test_kalman_filter_only():
    """Forward filter should match initial state propagation."""
    A = np.array([[0.5]])
    Q = np.array([[0.1]])
    C = np.array([[1.0]])
    R = np.array([[1.0]])
    y = np.array([[1.0, 2.0, 3.0]])
    Z_0 = np.array([0.0])
    V_0 = np.eye(1)

    Z_filt, V_filt, Z_pred, V_pred = kalman_filter(y, A, C, Q, R, Z_0, V_0)

    assert Z_filt.shape == (3, 1)
    assert Z_pred.shape == (3, 1)
    # Filtered should be between 0 and 3
    assert np.all(Z_filt > 0)
    assert np.all(Z_filt < 4)


def test_all_nan_handling():
    """All-NaN observations should not crash the filter."""
    A = np.array([[0.5, 0.0], [0.0, 0.5]])
    Q = np.eye(2) * 0.1
    C = np.array([[1.0, 0.0]])
    R = np.eye(1) * 0.5
    y = np.full((1, 10), np.nan)
    Z_0 = np.array([1.0, 1.0])
    V_0 = np.eye(2)

    Z_smooth, _ = kalman_filter_smoother(y, A, C, Q, R, Z_0, V_0)
    # With no observations, the smoother should just propagate
    assert Z_smooth.shape == (10, 2)
    assert not np.any(np.isnan(Z_smooth))


def test_loglikelihood_increasing_with_better_model():
    """Better parameters should yield higher log-likelihood."""
    rng = np.random.default_rng(42)
    T = 100
    A_true = np.array([[0.6]])
    Q_true = np.array([[0.3]])
    C_true = np.array([[1.0]])
    R_true = np.array([[0.5]])

    z = np.zeros(T)
    for t in range(1, T):
        z[t] = 0.6 * z[t - 1] + rng.normal(0, np.sqrt(0.3))
    y = (z + rng.normal(0, np.sqrt(0.5), T)).reshape(1, T)

    Z_0 = np.zeros(1)
    V_0 = np.eye(1)

    ll_true = kalman_loglikelihood(y, A_true, C_true, Q_true, R_true, Z_0, V_0)
    # Worse model (noisier)
    R_bad = np.array([[2.0]])
    ll_bad = kalman_loglikelihood(y, A_true, C_true, Q_true, R_bad, Z_0, V_0)

    assert ll_true > ll_bad, f"True model LL={ll_true:.1f} should exceed bad model LL={ll_bad:.1f}"
