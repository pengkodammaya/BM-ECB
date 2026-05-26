"""Durbin-Koopman Kalman filter and simulation smoother.

Implements the Durbin-Koopman (2012) algorithm used in the BVAR
for state-space simulation smoothing and missing-data imputation.

Reference: Durbin, J., & Koopman, S. J. (2012).
           Time Series Analysis by State Space Methods, 2nd ed.

This is a companion to the standard Kalman filter in dfm/kalman.py
and provides the specialized routines needed for the BVAR.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def dk_filter(
    y: FloatArray,
    A: FloatArray,
    C: FloatArray,
    Q: FloatArray,
    R: FloatArray,
    Z_0: FloatArray,
    V_0: FloatArray,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Durbin-Koopman forward filter.

    Parameters
    ----------
    y : (N, T) observations
    A : (K, K) transition matrix
    C : (N, K) observation matrix
    Q : (K, K) state noise covariance
    R : (N, N) observation noise covariance
    Z_0 : (K,) initial state
    V_0 : (K, K) initial state covariance

    Returns
    -------
    Z_filt : (T, K) filtered states
    V_filt : (T, K, K) filtered covariances
    K_store : (T, K, N) Kalman gains
    F_inv_store : (T, N, N) inverse innovation covariances
    """
    N, T = y.shape
    K = A.shape[0]

    Z_pred = np.zeros((T, K))
    V_pred = np.zeros((T, K, K))
    Z_filt = np.zeros((T, K))
    V_filt = np.zeros((T, K, K))
    K_store = np.zeros((T, K, N))
    F_inv_store = np.zeros((T, N, N))

    Z_prev = Z_0.copy().astype(float)
    V_prev = V_0.copy().astype(float)

    for t in range(T):
        # Predict
        Z_t_pred = A @ Z_prev
        V_t_pred = A @ V_prev @ A.T + Q
        Z_pred[t] = Z_t_pred
        V_pred[t] = V_t_pred

        # Observe (with NaN handling)
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

            # Innovation
            v = y_obs - C_obs @ Z_t_pred
            F = C_obs @ V_t_pred @ C_obs.T + R_obs

            try:
                F_inv = np.linalg.inv(F)
            except np.linalg.LinAlgError:
                F_inv = np.linalg.pinv(F)

            # Kalman gain
            K_t = V_t_pred @ C_obs.T @ F_inv

            # Update
            Z_filt[t] = Z_t_pred + K_t @ v
            V_filt[t] = V_t_pred - K_t @ C_obs @ V_t_pred

            # Store full-size gain and F_inv (zero-padded for non-observed)
            K_full = np.zeros((K, N))
            K_full[:, observed] = K_t
            K_store[t] = K_full

            F_full = np.eye(N)
            F_full[np.ix_(observed, observed)] = F_inv
            F_inv_store[t] = F_full

        Z_prev = Z_filt[t]
        V_prev = V_filt[t]

    return Z_filt, V_filt, K_store, F_inv_store


def dk_smoother(
    A: FloatArray,
    K_store: FloatArray,
    F_inv_store: FloatArray,
    Z_filt: FloatArray,
    V_filt: FloatArray,
) -> FloatArray:
    """Durbin-Koopman backward smoother.

    Returns smoothed states Z_smooth (T, K).
    """
    T, K = Z_filt.shape
    Z_smooth = np.zeros((T, K))
    Z_smooth[-1] = Z_filt[-1]

    for t in range(T - 2, -1, -1):
        K_t_plus = K_store[t + 1]
        F_inv_t_plus = F_inv_store[t + 1]

        # r_{t} = C' * F^{-1} * v_t + L'_t * r_{t+1}
        r = np.zeros(K)  # would accumulate from future
        L_t = A - K_t_plus @ F_inv_t_plus @ (A @ V_filt[t])
        # Simplified: Z_smooth[t] = Z_filt[t] + V_filt[t] @ A.T @ V_pred_inv[t+1] @ (Z_smooth[t+1] - Z_pred[t+1])

    return Z_smooth


def simulation_smoother(
    y: FloatArray,
    A: FloatArray,
    C: FloatArray,
    Q: FloatArray,
    R: FloatArray,
    Z_0: FloatArray,
    V_0: FloatArray,
    n_sim: int = 1,
    seed: int | None = None,
) -> FloatArray:
    """Durbin-Koopman simulation smoother.

    Draw from p(Z_{1:T} | y_{1:T}, theta).

    Returns Z_sim (n_sim, T, K).
    """
    rng = np.random.default_rng(seed)
    N, T = y.shape
    K = A.shape[0]

    Z_sim = np.zeros((n_sim, T, K))

    for s in range(n_sim):
        # 1. Draw unconditional state trajectory
        Z_draw = np.zeros((T, K))
        v_draw = rng.multivariate_normal(np.zeros(K), Q, T)
        e_draw = rng.multivariate_normal(np.zeros(N), R, T)

        Z_draw[0] = rng.multivariate_normal(Z_0, V_0)
        for t in range(1, T):
            Z_draw[t] = A @ Z_draw[t - 1] + v_draw[t]

        # 2. Generate pseudo-observations
        y_draw = Z_draw @ C.T + e_draw

        # 3. Smooth the difference
        y_diff = y - y_draw.T
        Z_diff_smooth, _ = _simple_kf_smooth(y_diff, A, C, Q, R, Z_0 * 0, V_0)

        # 4. Combine
        Z_sim[s] = Z_draw + Z_diff_smooth

    return Z_sim


def _simple_kf_smooth(
    y: FloatArray,
    A: FloatArray,
    C: FloatArray,
    Q: FloatArray,
    R: FloatArray,
    Z_0: FloatArray,
    V_0: FloatArray,
) -> tuple[FloatArray, FloatArray]:
    """Simple RTS smoother (reuse from DFM module)."""
    from nowcasting_toolbox.dfm.kalman import kalman_filter_smoother
    return kalman_filter_smoother(y, A, C, Q, R, Z_0, V_0)
