"""DFM estimation entry point — mirrors DFM_estimate.m.

Usage:
    from nowcasting_toolbox.dfm import DFM
    dfm = DFM(Params(...))
    Res = dfm.fit(X)         # X is (T, N) with NaNs for missing values
    predictions = Res.X_sm   # smoothed complete dataset
    factors = Res.F          # estimated factors
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np
from numpy.typing import NDArray

from nowcasting_toolbox.config import DFMParams
from nowcasting_toolbox.dfm.init import init_conditions
from nowcasting_toolbox.dfm.em import em_step
from nowcasting_toolbox.dfm.kalman import kalman_filter_smoother

logger = logging.getLogger(__name__)
FloatArray = NDArray[np.float64]


@dataclass
class DFMResult:
    """Container for DFM estimation results matching MATLAB Res struct."""

    X_sm: FloatArray                          # (T, N) smoothed complete dataset
    F: FloatArray                              # (T, K) smoothed states (factors)
    C: FloatArray                              # (N, K) observation/loading matrix
    R: FloatArray                              # (N, N) observation noise cov (diag)
    A: FloatArray                              # (K, K) state transition matrix
    Q: FloatArray                              # (K, K) state noise covariance
    Mx: FloatArray                             # (N,) series means (pre-standardization)
    Wx: FloatArray                             # (N,) series std devs
    Z_0: FloatArray                            # (K,) initial state
    V_0: FloatArray                            # (K, K) initial state covariance
    r: int                                     # number of factors
    p: int                                     # number of lags
    L: float = 0.0                             # final log-likelihood
    V_smooth: Optional[FloatArray] = None       # (T, K, K) smoothed state covariances
    groups: Optional[list[str]] = None          # group labels per variable
    series: Optional[list[str]] = None          # short names per variable
    name_descriptor: Optional[list[str]] = None  # full names per variable


class DFM:
    """Dynamic Factor Model estimator.

    Parameters
    ----------
    params : DFMParams
        Model hyperparameters (r, p, idio, thresh, max_iter, block_factors).
    verbose : bool
        Print EM iteration progress.

    Examples
    --------
    >>> from nowcasting_toolbox.config import DFMParams
    >>> params = DFMParams(r=3, p=2, max_iter=50)
    >>> dfm = DFM(params)
    >>> result = dfm.fit(X)  # X is (T, N) with possible NaNs
    """

    def __init__(
        self,
        params: Optional[DFMParams] = None,
        verbose: bool = False,
    ) -> None:
        self.params = params or DFMParams()
        self.verbose = verbose
        self.result_: Optional[DFMResult] = None
        self._groups: Optional[list[str]] = None

    def set_groups(self, groups: list[str]) -> "DFM":
        """Set variable group labels for block factor identification."""
        self._groups = groups
        return self

    def fit(self, X: FloatArray) -> DFMResult:
        """Estimate the DFM on data X.

        Parameters
        ----------
        X : (T, N) array
            Input data. NaN indicates missing values.
            The toolbox convention places quarterly variables (including
            the target GDP) in the last ``nQ`` columns.

        Returns
        -------
        DFMResult
        """
        p = min(self.params.p, 5)  # toolbox limits p to 5
        r = self.params.r
        thresh = self.params.thresh
        max_iter = self.params.max_iter
        idio_ar1 = bool(self.params.idio)
        block_factors = bool(self.params.block_factors)

        T, N = X.shape
        nQ = 1  # Default: treat last column as quarterly target
        nM = N - nQ

        if nM < r:
            logger.warning("r=%d exceeds nM=%d, reducing r to %d", r, nM, nM)
            r = max(nM, 1)

        # Build block factor assignment from group labels
        block_map: dict[str, int] = {}
        block_assign = np.zeros(N, dtype=int)
        if block_factors and hasattr(self, '_groups') and self._groups:
            group_list = self._groups
            for j in range(N):
                grp = group_list[j] if j < len(group_list) else f"grp_{j}"
                if grp not in block_map:
                    block_map[grp] = len(block_map)
                block_assign[j] = block_map[grp]
            n_blocks = len(block_map)
        else:
            n_blocks = 1  # single block = no block factors
            block_assign = np.zeros(N, dtype=int)

        # ---------- Standardization ----------
        Mx = np.nanmean(X, axis=0)
        Wx = np.nanstd(X, axis=0)
        Wx[Wx < 1e-12] = 1.0
        # Handle fully-NaN columns: set mean=0, std=1 (no contribution)
        nan_cols = np.all(np.isnan(X), axis=0)
        Mx[nan_cols] = 0.0
        Wx[nan_cols] = 1.0
        xNaN = (X - Mx) / Wx

        # ---------- Prepare for estimation ----------
        y = xNaN.T  # (N, T)

        # AR(1) idiosyncratic: monthly only (not quarterly)
        i_idio = np.zeros(N, dtype=bool)
        if idio_ar1:
            i_idio[:nM] = True

        n_idio = int(np.sum(i_idio))
        K = r * p + n_idio

        # ---------- Initial conditions ----------
        A, C, Q, R, Z_0, V_0 = init_conditions(
            xNaN, r, p, blocks=None, nQ=nQ, i_idio=i_idio,
            block_assign=block_assign if block_factors else None,
            n_blocks=n_blocks if block_factors else 0,
        )

        # ---------- EM loop ----------
        previous_loglik = -np.inf
        converged = False
        loglik_history: list[float] = []

        for iteration in range(max_iter):
            C, R, A, Q, Z_0, V_0, loglik = em_step(
                y, A, C, Q, R, Z_0, V_0, r, p, nQ, i_idio, block_assign if block_factors else None
            )
            loglik_history.append(loglik)

            if self.verbose and iteration % 10 == 0:
                logger.info("EM iteration %d, loglik=%.4f", iteration, loglik)

            if iteration > 2:
                change = abs(loglik - previous_loglik) / (abs(previous_loglik) + 1e-10)
                if change < thresh:
                    converged = True
                    if self.verbose:
                        logger.info("EM converged at iteration %d", iteration)
                    break

            previous_loglik = loglik

        # ---------- Final Kalman smoother run ----------
        Z_smooth, V_smooth = kalman_filter_smoother(y, A, C, Q, R, Z_0, V_0)
        X_sm_std = Z_smooth @ C.T
        X_sm = X_sm_std * Wx + Mx

        self.result_ = DFMResult(
            X_sm=X_sm,
            F=Z_smooth,
            V_smooth=V_smooth,
            C=C,
            R=R,
            A=A,
            Q=Q,
            Mx=Mx,
            Wx=Wx,
            Z_0=Z_0,
            V_0=V_0,
            r=r,
            p=p,
            L=loglik_history[-1] if loglik_history else 0.0,
        )
        return self.result_

    @property
    def result(self) -> DFMResult:
        """Return the fitted result (raises if not fitted)."""
        if self.result_ is None:
            raise RuntimeError("DFM not yet fitted. Call .fit(X) first.")
        return self.result_
