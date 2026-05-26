"""Minnesota prior for Bayesian VAR.

Implements the standard Minnesota (Litterman) prior with:
- lambda (tightness): controls overall prior variance on own-lag coefficients
- miu (sum-of-coefficients): shrinks toward unit root
- theta (co-persistence): shrinks toward cointegration at frequency zero
- alpha (block exogeneity): controls cross-block shrinkage

Reference: Cimadomo, Giannone, Lenza, Monti & Sokol (2022), J. Econometrics.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def make_dummy_observations(
    Y: FloatArray,
    p: int,
    lambda_: float = 0.2,
    miu: float = 1.0,
    theta: float = 1.0,
    alpha: float = 2.0,
    stationary: list[int] | None = None,
    block_exog: FloatArray | None = None,
) -> tuple[FloatArray, FloatArray]:
    """Create dummy observations encoding the Minnesota prior.

    Parameters
    ----------
    Y : (T, N) array
        Data matrix (rows = time, cols = variables).
    p : int
        Number of lags.
    lambda_ : float
        Overall tightness hyperparameter (default 0.2).
    miu : float
        Sum-of-coefficients prior tightness (default 1.0).
    theta : float
        Co-persistence prior tightness (default 1.0).
    alpha : float
        Block exogeneity tightness (default 2.0).
    stationary : list[int], optional
        Indices of stationary variables. Variables not in this list
        are treated as having a unit root (initial observation dummy).
    block_exog : (N, N) array, optional
        Block exogeneity matrix (1 = in same block, 0 = cross-block).

    Returns
    -------
    Y_dummy : (T_dummy, N) dummy observations for dependent variables
    X_dummy : (T_dummy, N * p) dummy observations for lagged regressors
    """
    T, N = Y.shape

    # Clamp hyperparameters to avoid division by zero during optimization
    lambda_ = max(lambda_, 0.001)
    miu = max(miu, 0.001)
    theta = max(theta, 0.001)

    # Standard deviation of each variable (for scaling)
    sigma = np.std(Y, axis=0, ddof=1)
    sigma[sigma < 1e-10] = 1.0
    # Also clamp sigma lower bound (some indicators may have near-zero variance)
    sigma = np.maximum(sigma, 0.01)

    # Mean for initial observation dummy
    y_bar = np.mean(Y, axis=0)

    # ---------- Dummy 1: Own-lag shrinkage (lambda) ----------
    Y_d1 = np.zeros((N * p, N))
    X_d1 = np.zeros((N * p, N * p))

    for j in range(N):
        for lag in range(1, p + 1):
            row = (lag - 1) * N + j
            col = (lag - 1) * N + j
            Y_d1[row, j] = sigma[j] * lag / lambda_
            X_d1[row, col] = sigma[j] * lag / lambda_

    # ---------- Dummy 2: Sum-of-coefficients (miu) ----------
    Y_d2 = np.diag(sigma * y_bar / miu)
    X_d2 = np.zeros((N, N * p))
    for lag in range(p):
        X_d2[:, lag * N : (lag + 1) * N] = np.diag(sigma * y_bar / miu)

    # ---------- Dummy 3: Co-persistence (theta) ----------
    Y_d3 = sigma * y_bar / theta
    X_d3 = np.zeros((1, N * p))
    for lag in range(p):
        X_d3[0, lag * N : (lag + 1) * N] = sigma * y_bar / theta

    # ---------- Assemble dummies ----------
    Y_dummy = np.vstack([Y_d1, Y_d2, Y_d3])
    X_dummy = np.vstack([X_d1, X_d2, X_d3])

    # ---------- Dummy 4: Unit root prior for non-stationary vars ----------
    if stationary is not None:
        non_stat = [i for i in range(N) if i not in stationary]
        if non_stat:
            Y_d4 = np.zeros((len(non_stat), N))
            X_d4 = np.zeros((len(non_stat), N * p))
            for idx, j in enumerate(non_stat):
                Y_d4[idx, j] = y_bar[j]
                for lag in range(p):
                    X_d4[idx, lag * N + j] = y_bar[j]
            Y_dummy = np.vstack([Y_dummy, Y_d4])
            X_dummy = np.vstack([X_dummy, X_d4])

    # ---------- Dummy 5: Block exogeneity (alpha) ----------
    if block_exog is not None:
        # Shrink cross-block coefficients toward zero
        pass  # Extended in bbvar during Gibbs

    return Y_dummy, X_dummy


def minnesota_posterior(
    Y: FloatArray,
    p: int,
    lambda_: float = 0.2,
    miu: float = 1.0,
    theta: float = 1.0,
) -> tuple[FloatArray, FloatArray]:
    """Compute posterior mean of VAR coefficients under Minnesota prior.

    Uses the closed-form Normal-Inverse-Wishart conjugate update
    after augmenting with dummy observations.

    Returns
    -------
    B_post : (N, N * p) posterior mean coefficient matrix
    Sigma_post : (N, N) posterior mean residual covariance
    """
    T, N = Y.shape

    Y_dummy, X_dummy = make_dummy_observations(Y, p, lambda_, miu, theta)

    # Actual data: Y_t = B * X_t + e_t
    # where X_t = [Y_{t-1}, ..., Y_{t-p}] (N * p)
    Y_actual = Y[p:]
    X_actual = np.zeros((T - p, N * p))
    for lag in range(p):
        X_actual[:, lag * N : (lag + 1) * N] = Y[p - lag - 1 : T - lag - 1]

    # Augment with dummies
    Y_aug = np.vstack([Y_actual, Y_dummy])
    X_aug = np.vstack([X_actual, X_dummy])

    # OLS: B_hat = (X'X)^-1 X'Y
    try:
        XX_inv = np.linalg.inv(X_aug.T @ X_aug)
    except np.linalg.LinAlgError:
        XX_inv = np.linalg.pinv(X_aug.T @ X_aug)

    B_hat = XX_inv @ X_aug.T @ Y_aug
    B_post = B_hat.T  # (N, N*p)

    # Residual covariance
    resid = Y_aug - X_aug @ B_hat
    Sigma_post = (resid.T @ resid) / len(Y_aug)

    return B_post, Sigma_post
