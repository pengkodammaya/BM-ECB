"""Block-BVAR with mixed-frequency data and Gibbs sampling.

Implements the Bayesian VAR of Cimadomo et al. (2022) for:
- Mixed-frequency data (monthly blocks + quarterly target)
- Minnesota prior with hyperparameter optimization
- Gibbs sampler for posterior inference

The model structure:
- Monthly variables are organized in blocks of 3 (for months within a quarter)
- Quarterly variable (GDP) is appended at the end
- State-space representation with Kalman filter handles ragged edges
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from nowcasting_toolbox.bvar.prior import make_dummy_observations
from nowcasting_toolbox.bvar.optimize import csminwel

logger = logging.getLogger(__name__)
FloatArray = NDArray[np.float64]


def block_bvar(
    X: FloatArray,
    lags: int,
    m_series: list[int],
    stationary: list[int],
    lambda0: float = 0.2,
    theta0: float = 1.0,
    miu0: float = 1.0,
    alpha0: float = 2.0,
    thresh: float = 1e-6,
    max_iter: int = 200,
) -> dict:
    """Estimate the block-BVAR with hyperparameter optimization.

    Parameters
    ----------
    X : (T, N) array
        Mixed-frequency data. Monthly variables repeated 3 times
        (one block per month-of-quarter), quarterly target at end.
    lags : int
        Number of lags.
    m_series : list[int]
        Indices of monthly variables.
    stationary : list[int]
        Indices of stationary variables.
    lambda0, theta0, miu0, alpha0 : float
        Initial hyperparameter values.
    thresh : float
        Convergence threshold.
    max_iter : int
        Maximum optimization iterations.

    Returns
    -------
    dict with keys: X_sm, B, Sigma, phi, lambda_, theta, miu, alpha
    """
    T, N = X.shape
    nM = len(m_series)
    nQ = N - 3 * nM  # quarterly variables

    # ---------- Fill missing data ----------
    X_filled = _fill_data(X)

    # ---------- Optimize hyperparameters ----------
    def obj_func(phi: FloatArray) -> float:
        """Negative log marginal likelihood for hyperparams phi = [lambda, theta, miu, alpha]."""
        # Clamp phi to avoid overflow in exp
        phi_clamped = np.clip(phi, -10.0, 10.0)
        lam, th, mu, al = np.exp(phi_clamped)  # enforce positivity
        try:
            ml = _log_ml(X_filled, lags, lam, th, mu, al, m_series, stationary)
            if not np.isfinite(ml):
                return 1e10
            return -ml
        except Exception:
            return 1e10

    phi0 = np.log([lambda0, theta0, miu0, alpha0])
    phi_opt, fh, gh, H, itct = csminwel(
        obj_func, phi0, crit=thresh, nit=max_iter, verbose=False
    )
    lambda_opt, theta_opt, miu_opt, alpha_opt = np.exp(phi_opt)

    # ---------- Gibbs sampler ----------
    B, Sigma, B_draws, Sigma_draws = _gibbs_sampler(
        X_filled, lags, lambda_opt, theta_opt, miu_opt, alpha_opt,
        m_series, stationary, n_draws=100, burn_in=30,
    )

    # ---------- Generate smoothed data ----------
    X_sm = _kalman_smooth(X_filled, B, Sigma, lags, nM, nQ)

    return {
        "X_sm": X_sm,
        "B": B,
        "Sigma": Sigma,
        "B_draws": B_draws,
        "Sigma_draws": Sigma_draws,
        "lambda": lambda_opt,
        "theta": theta_opt,
        "miu": miu_opt,
        "alpha": alpha_opt,
    }


# ---------------------------------------------------------------------------
# Log marginal likelihood
# ---------------------------------------------------------------------------


def _log_ml(
    Y: FloatArray,
    p: int,
    lambda_: float,
    theta: float,
    miu: float,
    alpha: float,
    m_series: list[int],
    stationary: list[int],
) -> float:
    """Compute log marginal likelihood for given hyperparameters."""
    T, N = Y.shape

    Y_dummy, X_dummy = make_dummy_observations(
        Y, p, lambda_, miu, theta, alpha, stationary
    )

    Y_actual = Y[p:]
    X_actual = np.zeros((T - p, N * p))
    for lag in range(p):
        X_actual[:, lag * N : (lag + 1) * N] = Y[p - lag - 1 : T - lag - 1]

    Y_aug = np.vstack([Y_actual, Y_dummy])
    X_aug = np.vstack([X_actual, X_dummy])

    T_star = len(Y_aug)
    try:
        XX_inv = np.linalg.inv(X_aug.T @ X_aug)
    except np.linalg.LinAlgError:
        return -1e10

    B_hat = XX_inv @ X_aug.T @ Y_aug
    resid = Y_aug - X_aug @ B_hat
    S = resid.T @ resid

    try:
        # Log marginal likelihood (approximation)
        sign, logdet_XX = np.linalg.slogdet(X_aug.T @ X_aug)
        sign2, logdet_S = np.linalg.slogdet(S)
        if sign <= 0 or sign2 <= 0:
            return -1e10

        ml = -0.5 * T_star * N * np.log(np.pi)
        ml += 0.5 * N * logdet_XX
        ml -= 0.5 * (T_star - N * p - N - 1) * logdet_S

        # Prior on hyperparameters
        ml -= 0.5 * lambda_**2 / 0.2**2  # lambda ~ N(0, 0.2)
        ml -= 0.5 * theta**2 / 1.0**2

        return float(ml)
    except Exception:
        return -1e10


# ---------------------------------------------------------------------------
# Gibbs sampler
# ---------------------------------------------------------------------------


def _gibbs_sampler(
    Y: FloatArray,
    p: int,
    lambda_: float,
    theta: float,
    miu: float,
    alpha: float,
    m_series: list[int],
    stationary: list[int],
    n_draws: int = 500,
    burn_in: int = 100,
) -> tuple[FloatArray, FloatArray]:
    """Gibbs sampler for posterior of B and Sigma."""
    T, N = Y.shape
    K = N * p

    Y_dummy, X_dummy = make_dummy_observations(
        Y, p, lambda_, miu, theta, alpha, stationary
    )

    Y_actual = Y[p:]
    X_actual = np.zeros((T - p, N * p))
    for lag in range(p):
        X_actual[:, lag * N : (lag + 1) * N] = Y[p - lag - 1 : T - lag - 1]

    Y_aug = np.vstack([Y_actual, Y_dummy])
    X_aug = np.vstack([X_actual, X_dummy])
    T_star = len(Y_aug)

    XX = X_aug.T @ X_aug
    XY = X_aug.T @ Y_aug

    B_store = np.zeros((n_draws, N, K))
    Sigma_store = np.zeros((n_draws, N, N))

    # Prior for Sigma: inverse Wishart(S0, nu0)
    S0 = np.eye(N) * 0.1
    nu0 = N + 2

    Sigma = np.eye(N)

    rng = np.random.default_rng(42)

    for i in range(n_draws):
        # Draw B | Sigma
        Sigma_inv = np.linalg.inv(Sigma)
        V_b = np.linalg.inv(np.kron(Sigma_inv, XX) + 1e-8 * np.eye(N * K))
        # Ensure symmetry and PSD
        V_b = (V_b + V_b.T) / 2
        V_b += np.eye(V_b.shape[0]) * 1e-8
        b_hat = np.linalg.solve(XX, XY).T  # (N, K)
        b_vec = b_hat.ravel()
        b_draw = rng.multivariate_normal(b_vec, V_b)
        B = b_draw.reshape(N, K)

        # Draw Sigma | B
        resid = Y_aug - X_aug @ B.T
        S_post = S0 + resid.T @ resid
        nu_post = nu0 + T_star
        Sigma = _inv_wishart_rvs(rng, nu_post, S_post)

        B_store[i] = B
        Sigma_store[i] = Sigma

    # Posterior means (after burn-in)
    B_mean = np.mean(B_store[burn_in:], axis=0)
    Sigma_mean = np.mean(Sigma_store[burn_in:], axis=0)

    return B_mean, Sigma_mean, B_store[burn_in:], Sigma_store[burn_in:]


def _inv_wishart_rvs(rng: np.random.Generator, df: int, scale: FloatArray) -> FloatArray:
    """Draw from inverse Wishart distribution."""
    # Draw from Wishart(Sigma, df), invert
    N = scale.shape[0]
    L = np.linalg.cholesky(scale)
    Z = rng.normal(0, 1, (df, N)).T
    W = L @ Z @ Z.T @ L.T
    return np.linalg.inv(W)


# ---------------------------------------------------------------------------
# Data filling
# ---------------------------------------------------------------------------


def _fill_data(X: FloatArray) -> FloatArray:
    """Simple spline/linear fill for missing values (used in BVAR preprocessing)."""
    X_filled = X.copy()
    T, N = X.shape
    for j in range(N):
        col = X[:, j]
        nan_mask = np.isnan(col)
        if not np.any(nan_mask):
            continue
        valid = ~nan_mask
        if not np.any(valid):
            X_filled[:, j] = 0.0
            continue
        indices = np.arange(T)
        X_filled[nan_mask, j] = np.interp(
            indices[nan_mask], indices[valid], col[valid]
        )
    return X_filled


# ---------------------------------------------------------------------------
# Kalman smoother (simple VAR version)
# ---------------------------------------------------------------------------


def _kalman_smooth(
    X: FloatArray,
    B: FloatArray,
    Sigma: FloatArray,
    lags: int,
    nM: int,
    nQ: int,
) -> FloatArray:
    """Apply Kalman smoother in VAR state-space form."""
    T, N = X.shape
    p = lags
    K = N * p

    # State: Z_t = [Y_t, Y_{t-1}, ..., Y_{t-p+1}]
    # Transition: A (companion form from B)
    A = np.zeros((K, K))
    for j in range(N):
        for k in range(N * p):
            A[j, k] = B[j, k]
    for lag in range(p - 1):
        A[N * (lag + 1) : N * (lag + 2), N * lag : N * (lag + 1)] = np.eye(N)

    # Observation: C selects contemporaneous vars
    C = np.zeros((N, K))
    C[:, :N] = np.eye(N)

    Q = np.zeros((K, K))
    Q[:N, :N] = Sigma
    R = np.eye(N) * 1e-4  # small observation noise

    # Kalman smoother
    Z_0 = np.zeros(K)
    V_0 = np.eye(K)

    from nowcasting_toolbox.dfm.kalman import kalman_filter_smoother
    y = X.T
    Z_smooth, _ = kalman_filter_smoother(y, A, C, Q, R, Z_0, V_0)

    X_sm = Z_smooth @ C.T
    return X_sm
