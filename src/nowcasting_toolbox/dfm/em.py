"""Single EM iteration for the Dynamic Factor Model.

Replicates DFM_EMstep.m — performs one E-step (Kalman smoother)
followed by one M-step (parameter update).

State-space model:
    y(t) = C * Z(t) + e(t),    e(t) ~ N(0, R)
    Z(t) = A * Z(t-1) + v(t),  v(t) ~ N(0, Q)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from nowcasting_toolbox.dfm.kalman import kalman_filter_smoother

FloatArray = NDArray[np.float64]

# Quarterly constraint matrix (Mariano-Murasawa)
R_MAT = np.array([
    [2, -1,  0,  0,  0],
    [3,  0, -1,  0,  0],
    [2,  0,  0, -1,  0],
    [1,  0,  0,  0, -1],
], dtype=float)


def em_step(
    y: FloatArray,
    A: FloatArray,
    C: FloatArray,
    Q: FloatArray,
    R: FloatArray,
    Z_0: FloatArray,
    V_0: FloatArray,
    r: int,
    p: int,
    nQ: int = 1,
    i_idio: np.ndarray | None = None,
    blocks: FloatArray | None = None,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray, FloatArray, FloatArray, float]:
    """Execute one EM iteration.

    Parameters
    ----------
    y : (N, T) array
        Observation matrix (columns = time, NaN for missing).
    A, C, Q, R, Z_0, V_0
        Current parameter estimates.
    r : int
        Number of factors.
    p : int
        Number of lags.
    nQ : int
        Number of quarterly variables (last nQ columns).
    i_idio : (N,) bool array, optional
        AR(1) idiosyncratic indicators.
    blocks : (N, Kb) array, optional
        Block factor assignments.

    Returns
    -------
    C_new, R_new, A_new, Q_new, Z_0_new, V_0_new, loglik
    """
    N, T = y.shape
    K = A.shape[0]
    if i_idio is None:
        i_idio = np.zeros(N, dtype=bool)

    # ---------- E-step: run Kalman smoother ----------
    Z_smooth, V_smooth = kalman_filter_smoother(y, A, C, Q, R, Z_0, V_0)
    Z_smooth = Z_smooth  # (T, K)
    V_smooth = V_smooth  # (T, K, K)

    # Cross-covariance: E[Z_t * Z_{t-1}']
    V_cross = np.zeros((T, K, K))
    for t in range(1, T):
        # E[Z_t Z_{t-1}' | data] = J_{t-1} * V_smooth[t] + Z_smooth[t] * Z_smooth[t-1]'
        try:
            V_pred_t = A @ V_smooth[t - 1] @ A.T + Q
            V_pred_inv = np.linalg.inv(V_pred_t)
        except np.linalg.LinAlgError:
            V_pred_inv = np.linalg.pinv(A @ V_smooth[t - 1] @ A.T + Q)
        J = V_smooth[t - 1] @ A.T @ V_pred_inv
        V_cross[t] = J @ V_smooth[t] + np.outer(Z_smooth[t], Z_smooth[t - 1])

    # ---------- Sufficient statistics ----------
    S_ZZ = np.zeros((K, K))
    S_ZZ_lag = np.zeros((K, K))
    S_ZY = np.zeros((K, N))
    S_ZZ_cross = np.zeros((K, K))

    for t in range(T):
        S_ZZ += V_smooth[t] + np.outer(Z_smooth[t], Z_smooth[t])
        if t > 0:
            S_ZZ_lag += V_smooth[t - 1] + np.outer(Z_smooth[t - 1], Z_smooth[t - 1])
            S_ZZ_cross += V_cross[t]  # E[Z_t Z_{t-1}']

    # ---------- M-step: update C and R ----------
    C_new = np.zeros_like(C)
    R_diag_new = np.zeros(N)

    for j in range(N):
        # Only use time points where y_j is observed
        observed = ~np.isnan(y[j, :])
        if not np.any(observed):
            C_new[j, :] = C[j, :]
            R_diag_new[j] = R[j, j]
            continue

        # E[Z * Z'] over observed periods
        ZZ_obs = np.zeros((K, K))
        ZY_obs = np.zeros(K)
        for t in np.where(observed)[0]:
            ZZ_obs += V_smooth[t] + np.outer(Z_smooth[t], Z_smooth[t])
            ZY_obs += Z_smooth[t] * y[j, t]

        try:
            ZZ_inv = np.linalg.inv(ZZ_obs)
        except np.linalg.LinAlgError:
            ZZ_inv = np.linalg.pinv(ZZ_obs)

        C_new[j, :] = ZZ_inv @ ZY_obs

        # R update (residual variance)
        resid_var = 0.0
        n_obs_j = np.sum(observed)
        for t in np.where(observed)[0]:
            pred = C_new[j, :] @ Z_smooth[t]
            resid_var += (y[j, t] - pred) ** 2 + C_new[j, :] @ V_smooth[t] @ C_new[j, :].T
        R_diag_new[j] = max(resid_var / n_obs_j, 1e-8)

    R_new = np.diag(R_diag_new)

    # Block factor loading constraints
    if blocks is not None and blocks.ndim == 1:
        # blocks is a 1-D assignment array: zero out cross-block loadings
        n_blocks = int(np.max(blocks)) + 1
        for b in range(n_blocks):
            b_col = r + b  # contemporaneous block factor column
            if b_col >= C_new.shape[1]:
                continue
            for j in range(N):
                if blocks[j] != b:
                    C_new[j, b_col] = 0.0

    # ---------- M-step: update A and Q ----------
    try:
        ZZ_lag_inv = np.linalg.inv(S_ZZ_lag)
    except np.linalg.LinAlgError:
        ZZ_lag_inv = np.linalg.pinv(S_ZZ_lag)

    A_new = S_ZZ_cross @ ZZ_lag_inv

    # Q = (1/T) * [S_ZZ - A_new * S_ZZ_cross']
    Q_new = (S_ZZ - A_new @ S_ZZ_cross.T) / T
    # Ensure symmetry and PSD
    Q_new = (Q_new + Q_new.T) / 2
    eigvals = np.linalg.eigvalsh(Q_new)
    if np.any(eigvals < 0):
        Q_new += np.eye(K) * (abs(eigvals.min()) + 1e-8)

    # ---------- Keep companion form structure ----------
    if p > 1:
        for lag in range(p - 1):
            row_start = r * (lag + 1)
            col_start = r * lag
            A_new[row_start : row_start + r, col_start : col_start + r] = np.eye(r)
        # Zero out non-companion entries in those rows
        A_new[r:, :] = 0
        for lag in range(p - 1):
            row_start = r * (lag + 1)
            col_start = r * lag
            A_new[row_start : row_start + r, col_start : col_start + r] = np.eye(r)

    # ---------- Initial conditions ----------
    Z_0_new = Z_smooth[0]
    V_0_new = V_smooth[0]

    # ---------- Compute log-likelihood ----------
    loglik = _compute_loglik(y, A_new, C_new, Q_new, R_new, Z_0_new, V_0_new)

    return C_new, R_new, A_new, Q_new, Z_0_new, V_0_new, loglik


def _compute_loglik(
    y: FloatArray,
    A: FloatArray,
    C: FloatArray,
    Q: FloatArray,
    R: FloatArray,
    Z_0: FloatArray,
    V_0: FloatArray,
) -> float:
    """Compute log-likelihood of the state-space model."""
    N, T = y.shape
    Z_prev = Z_0.copy()
    V_prev = V_0.copy()
    ll = 0.0

    for t in range(T):
        Z_pred = A @ Z_prev
        V_pred = A @ V_prev @ A.T + Q

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
                ll += -0.5 * logdet - 0.5 * innovation @ S_inv_innov
            except np.linalg.LinAlgError:
                pass

        Z_prev = Z_pred
        V_prev = V_pred

    return float(ll)
