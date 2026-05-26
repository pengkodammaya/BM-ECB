"""Common test fixtures: synthetic data generators for DFM/BVAR/BEQ."""

from __future__ import annotations

import numpy as np
import pytest


def _ensure_float(arr: np.ndarray) -> np.ndarray:
    return np.asarray(arr, dtype=float)


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_calendar() -> tuple[np.ndarray, np.ndarray]:
    """Generate monthly dates 2010M1 .. 2025M12 and a quarterly mask."""
    years = np.repeat(np.arange(2010, 2026), 12)
    months = np.tile(np.arange(1, 13), 16)
    datet = np.column_stack([years, months])
    is_q3 = (months % 3 == 0)
    return datet, is_q3


# ---------------------------------------------------------------------------
# Synthetic factor model (DFM)
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_dfm_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate data from a known DFM for parameter recovery tests.

    DGP: X_t = C * F_t + e_t,  F_t = A * F_{t-1} + v_t

    Returns
    -------
    X : (T, N) observed data with some NaN holes
    C_true : (N, K) true loadings
    A_true : (K, K) true transition matrix
    F_true : (T, K) true latent factors
    Q_true : (K, K) true state noise covariance
    """
    rng = np.random.default_rng(42)
    T, N, r = 500, 20, 3  # observations, variables, factors

    # Transition matrix (stable VAR(1))
    A_true = np.array([
        [0.6, 0.0, 0.0],
        [0.0, 0.5, 0.0],
        [0.0, 0.0, 0.4],
    ])
    Q_true = np.eye(r) * 0.3

    # Loadings
    C_true = rng.normal(0, 1, (N, r)) * 0.7

    # Idiosyncratic noise
    R_diag = rng.uniform(0.2, 0.8, N)

    # Generate factors
    F = np.zeros((T, r))
    for t in range(1, T):
        F[t] = A_true @ F[t - 1] + rng.multivariate_normal(np.zeros(r), Q_true)

    # Generate observations
    X = F @ C_true.T + rng.normal(0, np.sqrt(R_diag), (T, N))

    # Punch some NaNs (arbitrary missingness ~10%)
    mask = rng.random((T, N)) < 0.1
    X[mask] = np.nan

    return X, C_true, A_true, F, Q_true


# ---------------------------------------------------------------------------
# Synthetic VAR data (BVAR)
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_var_data() -> np.ndarray:
    """Generate data from a small stationary VAR(2).

    Returns (T, N) array.
    """
    rng = np.random.default_rng(42)
    T, N, p = 200, 5, 2

    A1 = np.array([
        [0.3, 0.0, 0.0, 0.0, 0.0],
        [0.1, 0.4, 0.0, 0.0, 0.0],
        [0.0, 0.1, 0.3, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.5, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.4],
    ])
    A2 = np.array([
        [0.1, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.1, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.1, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.1, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.1],
    ])
    Sigma = np.eye(N) * 0.5

    Y = np.zeros((T, N))
    for t in range(p, T):
        Y[t] = A1 @ Y[t - 1] + A2 @ Y[t - 2] + rng.multivariate_normal(np.zeros(N), Sigma)

    return Y


# ---------------------------------------------------------------------------
# Mixed-frequency data (BEQ)
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_mixed_freq_data() -> dict:
    """Generate monthly + quarterly data mimicking the toolbox structure.

    Returns dict with keys: Xm (T, nM), Y (Tq,), Xq (Tq, nQ-1), datet (T,2), dateQ (Tq,2)
    """
    rng = np.random.default_rng(42)
    T_steps = 180  # months (2010–2024)
    nM = 8
    nQ_extra = 2

    years = np.repeat(np.arange(2010, 2025), 12)[:T_steps]
    months = np.tile(np.arange(1, 13), 15)[:T_steps]
    datet = np.column_stack([years, months])

    # True quarterly GDP is a function of monthly indicators
    Xm = rng.normal(0, 1, (T_steps, nM))
    Y_q = np.cumsum(rng.normal(0, 0.5, T_steps // 3))

    # Build quarterly target with ragged-edge
    X_out = np.column_stack([Xm] + [np.tile(Y_q[:, None] + rng.normal(0, 0.2, (len(Y_q), nQ_extra + 1)), (1, 1))])  # simplified
    # Placeholder - proper fixture to be refined in milestone 3

    q3_mask = (months % 3 == 0)
    dateQ = datet[q3_mask]

    return {
        "Xm": Xm,
        "Xq": Xm[q3_mask][:, -nQ_extra:],  # quarterly extras
        "Y": Xm[q3_mask][:, 0],  # quarterly GDP proxy
        "datet": datet,
        "dateQ": dateQ,
    }


# ---------------------------------------------------------------------------
# Missing-data stress test
# ---------------------------------------------------------------------------


@pytest.fixture
def ragged_edge_data() -> np.ndarray:
    """Create data with a ragged edge (tail NaNs) mimicking real-time vintages.

    Returns (T, N) array where each column has a different last-observed row.
    """
    rng = np.random.default_rng(42)
    T, N = 120, 10
    X = rng.normal(0, 1, (T, N))

    # Each column j is missing after row T - j (ragged edge)
    for j in range(N):
        X[(T - j - 1):, j] = np.nan

    return X


# ---------------------------------------------------------------------------
# Publication lag simulation
# ---------------------------------------------------------------------------


@pytest.fixture
def publication_lag_data() -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Generate data with realistic publication delays.

    Returns
    -------
    X : (T, N) data with trailing NaNs
    datet : (T, 2) year/month
    pub_lags : list of publication delays in months for each series
    """
    rng = np.random.default_rng(42)
    T, N = 180, 8
    datet = np.column_stack([
        np.repeat(np.arange(2010, 2025), 12)[:T],
        np.tile(np.arange(1, 13), 15)[:T],
    ])
    X = rng.normal(0, 1, (T, N))

    pub_lags = [0, 1, 1, 2, 3, 5, 8, 15]  # months delay for each series
    for j, lag in enumerate(pub_lags):
        if lag > 0:
            X[(-lag):, j] = np.nan

    return X, datet, pub_lags
