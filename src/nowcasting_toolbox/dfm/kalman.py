"""Custom Kalman filter and smoother for DFM state-space models.

State-space representation (Banbura & Modugno, 2014):

    y(t) = C * Z(t) + e(t),   e(t) ~ N(0, R)
    Z(t) = A * Z(t-1) + v(t), v(t) ~ N(0, Q)

where:
    y  : (N, 1) observation vector at time t (may contain NaN)
    Z  : (K, 1) latent state vector
    C  : (N, K) observation/loading matrix
    A  : (K, K) state transition matrix
    R  : (N, N) observation noise covariance (diagonal in toolbox)
    Q  : (K, K) state noise covariance

The filter handles arbitrary NaN patterns by selecting only observed
rows of y and corresponding rows of C/R for each time step.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def kalman_filter_smoother(
    y: FloatArray,
    A: FloatArray,
    C: FloatArray,
    Q: FloatArray,
    R: FloatArray,
    Z_0: FloatArray,
    V_0: FloatArray,
    max_cov: float = 1e10,
) -> tuple[FloatArray, FloatArray]:
    """Run the Kalman filter and RTS smoother on data with missing values.

    Parameters
    ----------
    y : (N, T) array
        Observation matrix. Columns are time, rows are variables.
        NaN indicates missing observation.
    A : (K, K) array
        State transition matrix.
    C : (N, K) array
        Observation matrix (maps states→observations).
    Q : (K, K) array
        State noise covariance.
    R : (N, N) array
        Observation noise covariance (typically diagonal).
    Z_0 : (K,) array
        Initial state mean.
    V_0 : (K, K) array
        Initial state covariance.
    max_cov : float
        Maximum covariance diagonal value to prevent overflow.

    Returns
    -------
    Z_smooth : (T, K) array
        Smoothed state estimates (one row per time step).
    V_smooth : (T, K, K) array
        Smoothed state covariance at each time step.
    """
    N, T = y.shape
    K = A.shape[0]

    A = np.atleast_2d(A)
    C = np.atleast_2d(C)
    Q = np.atleast_2d(Q)
    R = np.atleast_2d(R)
    Z_0 = np.atleast_1d(Z_0).astype(float)
    V_0 = np.atleast_2d(V_0).astype(float)

    # Clip initial conditions to prevent overflow
    Z_0 = np.clip(Z_0, -1e6, 1e6)
    V_diag = np.diag(V_0).copy()
    V_diag = np.clip(V_diag, 0, max_cov)
    V_0 = np.diag(V_diag) + (V_0 - np.diag(np.diag(V_0)))

    # ---------- Forward pass (filter) ----------
    Z_pred = np.zeros((T, K))
    V_pred = np.zeros((T, K, K))
    Z_filt = np.zeros((T, K))
    V_filt = np.zeros((T, K, K))

    Z_prev = Z_0.copy()
    V_prev = V_0.copy()

    for t in range(T):
        # Prediction
        Z_t_pred = A @ Z_prev
        V_t_pred = A @ V_prev @ A.T + Q

        # Clip to prevent overflow
        Z_t_pred = np.clip(Z_t_pred, -1e6, 1e6)
        V_diag = np.diag(V_t_pred).copy()
        V_diag = np.clip(V_diag, 0, max_cov)
        V_t_pred = np.diag(V_diag) + (V_t_pred - np.diag(np.diag(V_t_pred)))

        Z_pred[t] = Z_t_pred
        V_pred[t] = V_t_pred

        # Select non-NaN observations at time t
        y_t = y[:, t]
        observed = ~np.isnan(y_t)
        n_obs = np.sum(observed)

        if n_obs == 0:
            # No observations — just predict
            Z_filt[t] = Z_t_pred
            V_filt[t] = V_t_pred
        else:
            y_obs = y_t[observed]
            C_obs = C[observed, :]
            R_obs = R[np.ix_(observed, observed)]

            # Innovation covariance
            S = C_obs @ V_t_pred @ C_obs.T + R_obs

            # Kalman gain
            try:
                S_inv = np.linalg.inv(S)
            except np.linalg.LinAlgError:
                S_inv = np.linalg.pinv(S)

            K_gain = V_t_pred @ C_obs.T @ S_inv

            # Update
            innovation = y_obs - C_obs @ Z_t_pred
            Z_t_filt = Z_t_pred + K_gain @ innovation
            V_t_filt = V_t_pred - K_gain @ C_obs @ V_t_pred

            Z_filt[t] = Z_t_filt
            V_filt[t] = V_t_filt

        Z_prev = Z_filt[t]
        V_prev = V_filt[t]

    # ---------- Backward pass (RTS smoother) ----------
    Z_smooth = np.zeros((T, K))
    V_smooth = np.zeros((T, K, K))

    Z_smooth[-1] = Z_filt[-1]
    V_smooth[-1] = V_filt[-1]

    for t in range(T - 2, -1, -1):
        # Smoother gain
        V_pred_next = V_pred[t + 1]
        try:
            V_pred_inv = np.linalg.inv(V_pred_next)
        except np.linalg.LinAlgError:
            V_pred_inv = np.linalg.pinv(V_pred_next)

        J = V_filt[t] @ A.T @ V_pred_inv

        Z_smooth[t] = Z_filt[t] + J @ (Z_smooth[t + 1] - Z_pred[t + 1])
        V_smooth[t] = V_filt[t] + J @ (V_smooth[t + 1] - V_pred_next) @ J.T

        # Clip to prevent overflow
        Z_smooth[t] = np.clip(Z_smooth[t], -1e6, 1e6)
        V_diag = np.diag(V_smooth[t]).copy()
        V_diag = np.clip(V_diag, 0, max_cov)
        V_smooth[t] = np.diag(V_diag) + (V_smooth[t] - np.diag(np.diag(V_smooth[t])))

    return Z_smooth, V_smooth


# ---------------------------------------------------------------------------
# Convenience: filter only (no smoothing)
# ---------------------------------------------------------------------------


def kalman_filter(
    y: FloatArray,
    A: FloatArray,
    C: FloatArray,
    Q: FloatArray,
    R: FloatArray,
    Z_0: FloatArray,
    V_0: FloatArray,
    max_cov: float = 1e10,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Run only the forward Kalman filter (no smoother).

    Returns
    -------
    Z_filt : (T, K) filtered states
    V_filt : (T, K, K) filtered covariances
    Z_pred : (T, K) predicted states
    V_pred : (T, K, K) predicted covariances
    """
    N, T = y.shape
    K = A.shape[0]

    A = np.atleast_2d(A)
    C = np.atleast_2d(C)
    Q = np.atleast_2d(Q)
    R = np.atleast_2d(R)
    Z_0 = np.atleast_1d(Z_0).astype(float)
    V_0 = np.atleast_2d(V_0).astype(float)

    # Clip initial conditions to prevent overflow
    Z_0 = np.clip(Z_0, -1e6, 1e6)
    V_diag = np.diag(V_0).copy()
    V_diag = np.clip(V_diag, 0, max_cov)
    V_0 = np.diag(V_diag) + (V_0 - np.diag(np.diag(V_0)))

    Z_pred = np.zeros((T, K))
    V_pred = np.zeros((T, K, K))
    Z_filt = np.zeros((T, K))
    V_filt = np.zeros((T, K, K))

    Z_prev = Z_0.copy()
    V_prev = V_0.copy()

    for t in range(T):
        Z_t_pred = A @ Z_prev
        V_t_pred = A @ V_prev @ A.T + Q

        # Clip to prevent overflow
        Z_t_pred = np.clip(Z_t_pred, -1e6, 1e6)
        V_diag = np.diag(V_t_pred).copy()
        V_diag = np.clip(V_diag, 0, max_cov)
        V_t_pred = np.diag(V_diag) + (V_t_pred - np.diag(np.diag(V_t_pred)))

        Z_pred[t] = Z_t_pred
        V_pred[t] = V_t_pred

        y_t = y[:, t]
        observed = ~np.isnan(y_t)
        n_obs = np.sum(observed)

        if n_obs == 0:
            Z_filt[t] = Z_t_pred
            V_filt[t] = V_t_pred
        else:
            y_obs = y_t[observed]
            C_obs = C[observed, :]
            R_obs = R[np.ix_(observed, observed)]

            S = C_obs @ V_t_pred @ C_obs.T + R_obs
            try:
                S_inv = np.linalg.inv(S)
            except np.linalg.LinAlgError:
                S_inv = np.linalg.pinv(S)
            K_gain = V_t_pred @ C_obs.T @ S_inv

            innovation = y_obs - C_obs @ Z_t_pred
            Z_filt[t] = Z_t_pred + K_gain @ innovation
            V_filt[t] = V_t_pred - K_gain @ C_obs @ V_t_pred

        Z_prev = Z_filt[t]
        V_prev = V_filt[t]

    return Z_filt, V_filt, Z_pred, V_pred


# ---------------------------------------------------------------------------
# Log-likelihood computation (used in EM convergence check)
# ---------------------------------------------------------------------------


def kalman_loglikelihood(
    y: FloatArray,
    A: FloatArray,
    C: FloatArray,
    Q: FloatArray,
    R: FloatArray,
    Z_0: FloatArray,
    V_0: FloatArray,
    max_cov: float = 1e10,
) -> float:
    """Compute the log-likelihood of the data under the state-space model."""
    N, T = y.shape

    Z_prev = np.atleast_1d(Z_0).astype(float)
    V_prev = np.atleast_2d(V_0).astype(float)

    # Clip initial conditions to prevent overflow
    Z_prev = np.clip(Z_prev, -1e6, 1e6)
    V_diag = np.diag(V_prev).copy()
    V_diag = np.clip(V_diag, 0, max_cov)
    V_prev = np.diag(V_diag) + (V_prev - np.diag(np.diag(V_prev)))

    loglik = 0.0
    const = -0.5 * N * np.log(2 * np.pi)

    for t in range(T):
        Z_pred = A @ Z_prev
        V_pred = A @ V_prev @ A.T + Q

        # Clip to prevent overflow
        Z_pred = np.clip(Z_pred, -1e6, 1e6)
        V_diag = np.diag(V_pred).copy()
        V_diag = np.clip(V_diag, 0, max_cov)
        V_pred = np.diag(V_diag) + (V_pred - np.diag(np.diag(V_pred)))

        y_t = y[:, t]
        observed = ~np.isnan(y_t)
        n_obs = np.sum(observed)

        if n_obs > 0:
            y_obs = y_t[observed]
            C_obs = C[observed, :]
            R_obs = R[np.ix_(observed, observed)]

            S = C_obs @ V_pred @ C_obs.T + R_obs
            innovation = y_obs - C_obs @ Z_pred

            try:
                S_chol = np.linalg.cholesky(S)
                logdet = 2 * np.sum(np.log(np.diag(S_chol)))
                S_inv_innov = np.linalg.solve(S_chol.T, np.linalg.solve(S_chol, innovation))
                loglik += -0.5 * logdet - 0.5 * innovation @ S_inv_innov
            except np.linalg.LinAlgError:
                pass

        Z_prev = Z_pred
        V_prev = V_pred

    return float(loglik)
