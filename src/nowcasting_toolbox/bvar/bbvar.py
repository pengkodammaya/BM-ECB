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
    datet: FloatArray | None = None,
    lambda0: float = 0.2,
    theta0: float = 1.0,
    miu0: float = 1.0,
    alpha0: float = 2.0,
    thresh: float = 1e-6,
    max_iter: int = 200,
    n_draws: int = 100,
    burn_in: int = 30,
) -> dict:
    """Estimate the block-BVAR with hyperparameter optimization.

    Parameters
    ----------
    X : (T, N) array
        Mixed-frequency data. Monthly variables first, quarterly target last.
    lags : int
        Number of lags.
    m_series : list[int]
        Indices of monthly variables.
    stationary : list[int]
        Indices of stationary variables.
    datet : (T, 2) array, optional
        Year-month for each row. If provided, restructures data into
        quarter-block format (matching MATLAB BVAR_bbvar behavior).
    lambda0, theta0, miu0, alpha0 : float
        Initial hyperparameter values.
    thresh : float
        Convergence threshold.
    max_iter : int
        Maximum optimization iterations.
    n_draws : int
        Number of Gibbs sampler draws.
    burn_in : int
        Gibbs sampler burn-in period.

    Returns
    -------
    dict with keys: X_sm, B, Sigma, phi, lambda_, theta, miu, alpha
    """
    T, N = X.shape
    nM = len(m_series)
    nQ = N - nM  # quarterly variables

    # ---------- Fill missing data ----------
    # If datet provided, restructure into quarter-block format
    X_filled = _fill_data(X, datet)

    # For quarter-block mode, the filled data has different dimensions
    # month1 | month2 | month3 (with quarterly in month3)
    if datet is not None:
        # X_filled is now (T_q, 3*nM + nQ)
        # Fill remaining NaN with spline interpolation (like MATLAB BVAR_remNaNs_spline)
        X_filled = _spline_fill_block(X_filled)
        T_q = len(X_filled)
        N_block = X_filled.shape[1]
        # Update m_series for block format: monthly vars are in first 2*nM columns
        m_series_block = list(range(2 * nM))
        stationary_block = list(range(N_block))
    else:
        T_q = T
        N_block = N
        m_series_block = m_series
        stationary_block = stationary

    # ---------- Optimize hyperparameters ----------
    def obj_func(phi: FloatArray) -> float:
        """Negative log marginal likelihood for hyperparams phi = [lambda, theta, miu, alpha]."""
        # Clamp phi to avoid overflow in exp
        phi_clamped = np.clip(phi, -10.0, 10.0)
        lam, th, mu, al = np.exp(phi_clamped)  # enforce positivity
        try:
            ml = _log_ml(X_filled, lags, lam, th, mu, al, m_series_block, stationary_block)
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
        m_series_block, stationary_block, n_draws=n_draws, burn_in=burn_in,
    )

    # ---------- Generate smoothed data ----------
    X_sm_block = _kalman_smooth(X_filled, B, Sigma, lags, nM, nQ)

    # If quarter-block mode, restructure back to monthly format
    if datet is not None:
        X_sm = _restructure_from_quarter_blocks(X_sm_block, nM, nQ, T)
    else:
        X_sm = X_sm_block

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
# Data filling and quarter-block restructuring
# ---------------------------------------------------------------------------


def _fill_data(X: FloatArray, datet: FloatArray | None = None) -> FloatArray:
    """Prepare data for BVAR estimation.

    If datet is provided, restructures data into quarter-block format:
    - Month 1 of each quarter in columns 0:nM
    - Month 2 of each quarter in columns nM:2*nM
    - Month 3 of each quarter in columns 2*nM:end

    This matches the MATLAB BVAR_filldata + BVAR_bbvar behavior.

    If datet is None, falls back to forward-fill (legacy behavior).
    """
    if datet is not None:
        return _restructure_quarter_blocks(X, datet)
    else:
        return _forward_fill(X)


def _forward_fill(X: FloatArray) -> FloatArray:
    """Forward-fill for missing values (no future interpolation).

    Only uses past/present data to fill NaN, preventing data leakage
    in pseudo-real-time backtesting.
    """
    X_filled = X.copy()
    T, N = X.shape
    for j in range(N):
        col = X[:, j]
        # Forward-fill only (no interpolation with future values)
        last_valid = np.nan
        for t in range(T):
            if not np.isnan(col[t]):
                last_valid = col[t]
            elif not np.isnan(last_valid):
                X_filled[t, j] = last_valid
    return X_filled


def _spline_fill_block(X: FloatArray) -> FloatArray:
    """Fill NaN values with spline interpolation (like MATLAB BVAR_remNaNs_spline).

    This is used for quarter-block data where forward-fill alone may not
    be sufficient. Uses linear interpolation for interior NaN, forward-fill
    for trailing NaN.
    """
    from scipy.interpolate import interp1d

    X_filled = X.copy()
    T, N = X.shape

    for j in range(N):
        col = X[:, j]
        nan_mask = np.isnan(col)
        if not np.any(nan_mask):
            continue

        valid_idx = np.where(~nan_mask)[0]
        if len(valid_idx) < 2:
            # Not enough valid points, forward-fill
            last_valid = np.nan
            for t in range(T):
                if not np.isnan(col[t]):
                    last_valid = col[t]
                elif not np.isnan(last_valid):
                    X_filled[t, j] = last_valid
            continue

        # Linear interpolation for interior NaN
        f = interp1d(valid_idx, col[valid_idx], kind='linear',
                     bounds_error=False, fill_value='extrapolate')
        interior_idx = np.where(nan_mask)[0]
        # Only fill NaN that are between valid points (not trailing)
        max_valid = valid_idx[-1]
        fill_mask = interior_idx < max_valid
        X_filled[interior_idx[fill_mask], j] = f(interior_idx[fill_mask])

        # Forward-fill for trailing NaN (after last valid point)
        last_valid = col[max_valid]
        for t in range(max_valid + 1, T):
            if np.isnan(X_filled[t, j]):
                X_filled[t, j] = last_valid

    return X_filled


def _align_to_quarter_boundary(datet: FloatArray) -> tuple[FloatArray, int, int]:
    """Align date grid to quarter boundaries.

    Returns (aligned_datet, n_pad_start, n_pad_end).
    """
    T = len(datet)

    # Check start: should be month 1 of a quarter
    start_month = int(datet[0, 1])
    if start_month % 3 == 0:
        # Month 3: need to pad 2 months at start
        n_pad_start = 2
    elif start_month % 3 == 2:
        # Month 2: need to pad 1 month at start
        n_pad_start = 1
    else:
        # Month 1: already aligned
        n_pad_start = 0

    # Check end: should be month 3 of a quarter
    end_month = int(datet[-1, 1])
    if end_month % 3 == 1:
        # Month 1: need to pad 2 months at end
        n_pad_end = 2
    elif end_month % 3 == 2:
        # Month 2: need to pad 1 month at end
        n_pad_end = 1
    else:
        # Month 3: already aligned
        n_pad_end = 0

    return datet, n_pad_start, n_pad_end


def _restructure_quarter_blocks(X: FloatArray, datet: FloatArray) -> FloatArray:
    """Restructure monthly data into quarter-block format.

    Input: X (T, N) where N = nM + nQ
    Output: X_block (T_q, 3*nM + nQ) where T_q = T/3

    Each row of output contains:
    - Month 1 values for all monthly variables
    - Month 2 values for all monthly variables
    - Month 3 values for all monthly variables (including quarterly target)

    This matches the MATLAB BVAR_bbvar structure.
    """
    T, N = X.shape

    # Determine nM (monthly) and nQ (quarterly)
    # Quarterly variables are at the end and have NaN in months 1-2
    # For now, assume last column is quarterly target
    nQ = 1
    nM = N - nQ

    # Align to quarter boundaries
    _, n_pad_start, n_pad_end = _align_to_quarter_boundary(datet)

    # Pad with NaN if needed
    if n_pad_start > 0:
        X = np.vstack([np.full((n_pad_start, N), np.nan), X])
    if n_pad_end > 0:
        X = np.vstack([X, np.full((n_pad_end, N), np.nan)])

    T_aligned = len(X)
    T_q = T_aligned // 3  # number of quarters

    # Restructure into quarter blocks
    # MATLAB: month1 = X(1:3:end, mSeries)
    #         month2 = X(2:3:end, mSeries)
    #         month3 = X(3:3:end, :)
    #         xQ = [month1 month2 month3]
    X_block = np.full((T_q, 3 * nM + nQ), np.nan)

    for q in range(T_q):
        idx1 = q * 3
        idx2 = q * 3 + 1
        idx3 = q * 3 + 2

        # Month 1: monthly variables only
        if idx1 < T_aligned:
            X_block[q, :nM] = X[idx1, :nM]

        # Month 2: monthly variables only
        if idx2 < T_aligned:
            X_block[q, nM:2 * nM] = X[idx2, :nM]

        # Month 3: all variables (monthly + quarterly)
        if idx3 < T_aligned:
            X_block[q, 2 * nM:] = X[idx3, :]

    return X_block


def _restructure_from_quarter_blocks(X_block: FloatArray, nM: int, nQ: int, T_original: int) -> FloatArray:
    """Restructure quarter-block data back to monthly format.

    Input: X_block (T_q, 3*nM + nQ)
    Output: X_monthly (T, nM + nQ)

    This is the inverse of _restructure_quarter_blocks.
    """
    T_q = len(X_block)
    N = nM + nQ
    X_monthly = np.full((T_q * 3, N), np.nan)

    for q in range(T_q):
        idx1 = q * 3
        idx2 = q * 3 + 1
        idx3 = q * 3 + 2

        # Month 1: monthly variables only
        X_monthly[idx1, :nM] = X_block[q, :nM]

        # Month 2: monthly variables only
        X_monthly[idx2, :nM] = X_block[q, nM:2 * nM]

        # Month 3: all variables
        X_monthly[idx3, :] = X_block[q, 2 * nM:]

    # Trim to original length
    return X_monthly[:T_original]


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
