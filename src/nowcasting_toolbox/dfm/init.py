"""Initial conditions for DFM EM algorithm (PCA-based).

Replicates DFM_InitCond.m from Banbura & Modugno (2014).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

# Mariano-Murasawa quarterly constraint matrix
R_MAT = np.array([
    [2, -1,  0,  0,  0],
    [3,  0, -1,  0,  0],
    [2,  0,  0, -1,  0],
    [1,  0,  0,  0, -1],
], dtype=float)


def init_conditions(
    X: FloatArray,
    r: int,
    p: int,
    blocks: FloatArray | None = None,
    nQ: int = 1,
    i_idio: np.ndarray | None = None,
    block_assign: np.ndarray | None = None,
    n_blocks: int = 0,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray, FloatArray, FloatArray]:
    """Compute initial values for A, C, Q, R, Z_0, V_0.

    Parameters
    ----------
    X : (T, N) array
        Standardized data with NaNs for missing values.
    r : int
        Number of factors.
    p : int
        Number of lags in the factor VAR.
    blocks : (N, K) array, optional
        Block assignment matrix (one-hot per column for each block).
    nQ : int
        Number of quarterly variables (last nQ columns of X).
    i_idio : (N,) bool array, optional
        Indicator for variables with AR(1) idiosyncratic component.

    Returns
    -------
    A : (K, K) transition matrix where K = r * p
    C : (N, K) observation matrix
    Q : (K, K) state noise covariance
    R : (N, N) observation noise covariance (diagonal)
    Z_0 : (K,) initial state
    V_0 : (K, K) initial state covariance (solved from Lyapunov)
    """
    T, N = X.shape

    # ---------- Fill NaNs for PCA initialization ----------
    X_filled = _fill_nans_for_pca(X)

    # ---------- PCA for factor loadings ----------
    # Mean-centre (already standardized in caller)
    U, s, Vt = np.linalg.svd(X_filled, full_matrices=False)
    # s is (min(T,N),), Vt is (min(T,N), N)
    F_pca = U[:, :r] * s[:r]  # (T, r) — estimated factors
    C_pca = Vt[:r, :].T       # (N, r) — estimated loadings

    # ---------- Build the full state dimension ----------
    # K = r * p (global factors) + n_blocks * p (block factors) + n_idio
    n_idio = int(np.sum(i_idio)) if i_idio is not None else 0
    n_blocks_active = n_blocks if block_assign is not None and n_blocks > 0 else 0
    K = r * p + n_blocks_active * p + n_idio

    # ---------- Initial A (transition) ----------
    A = np.zeros((K, K))
    Q = np.eye(K) * 0.1

    if p > 0 and T > p:
        # Fit VAR(1) in companion form for global factors
        Y = F_pca[p:]  # (T-p, r)
        X_lag = np.zeros((T - p, r * p))
        for lag in range(p):
            X_lag[:, lag * r : (lag + 1) * r] = F_pca[p - lag - 1 : T - lag - 1]

        try:
            A_coeffs = np.linalg.lstsq(X_lag, Y, rcond=None)[0].T  # (r, r*p)
            A[:r, :r * p] = A_coeffs
            for lag in range(p - 1):
                A[r * (lag + 1) : r * (lag + 2), r * lag : r * (lag + 1)] = np.eye(r)
            resid = Y - X_lag @ A_coeffs.T
            Q[:r, :r] = np.cov(resid.T)
        except np.linalg.LinAlgError:
            pass

        # Block factors: identity transitions (random walk)
        for b in range(n_blocks_active):
            b_start = r * p + b * p
            for lag in range(p - 1):
                A[b_start + r * (lag + 1) : b_start + r * (lag + 2), 
                  b_start + r * lag : b_start + r * (lag + 1)] = np.eye(r)

    # Identity for idio AR(1)
    if n_idio > 0:
        for j in range(n_idio):
            idx = r * p + j
            # Default: modest persistence
            A[idx, idx] = 0.5
            Q[idx, idx] = 0.1

    # ---------- Initial C (observation) ----------
    C = np.zeros((N, K))
    C[:, :r] = C_pca  # loadings for contemporaneous global factors
    
    # Block factor loadings: each block factor loads only on its block's variables
    if n_blocks_active > 0 and block_assign is not None:
        for b in range(n_blocks_active):
            block_mask = (block_assign == b)
            if np.sum(block_mask) > 0:
                b_col = r + b  # contemporaneous block factor column
                C[block_mask, b_col] = C_pca[block_mask, 0] * 0.5  # halved initial loading

    # ---------- Initial R (diagonal) ----------
    fitted = F_pca @ C_pca.T
    resid = X_filled - fitted
    R_diag = np.nanvar(resid, axis=0)
    R_diag[R_diag < 1e-6] = 0.1
    R = np.diag(R_diag)

    # ---------- Initial Z_0, V_0 ----------
    Z_0 = np.zeros(K)
    # Solve Lyapunov: V_0 = A * V_0 * A' + Q
    try:
        from scipy.linalg import solve_discrete_lyapunov
        V_0 = solve_discrete_lyapunov(A, Q)
    except Exception:
        V_0 = np.eye(K)

    return A, C, Q, R, Z_0, V_0


def _fill_nans_for_pca(X: FloatArray) -> FloatArray:
    """Fill NaNs with 0 (mean for centred data) before PCA."""
    X_filled = X.copy()
    X_filled[np.isnan(X_filled)] = 0.0
    return X_filled
