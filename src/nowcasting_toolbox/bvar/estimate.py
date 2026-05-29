"""BVAR estimation entry point — mirrors BVAR_estimate.m.

Usage:
    from nowcasting_toolbox.bvar import BVAR
    bvar = BVAR(Params(...))
    Res = bvar.fit(X, datet)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from nowcasting_toolbox.config import BVARParams
from nowcasting_toolbox.bvar.bbvar import block_bvar

logger = logging.getLogger(__name__)
FloatArray = NDArray[np.float64]


@dataclass
class BVARResult:
    """Container for BVAR estimation results."""
    X_sm: FloatArray
    B: Optional[FloatArray] = None        # (N, N*p) coefficient matrix
    Sigma: Optional[FloatArray] = None    # (N, N) residual covariance
    B_draws: Optional[FloatArray] = None  # (n_draws, N, N*p) posterior draws
    Sigma_draws: Optional[FloatArray] = None  # (n_draws, N, N) posterior draws
    lambda_opt: float = 0.2
    theta_opt: float = 1.0
    miu_opt: float = 1.0
    alpha_opt: float = 2.0
    X_sm_init: Optional[FloatArray] = None  # raw BVAR output before reshaping


class BVAR:
    """Bayesian Vector Autoregression estimator.

    Parameters
    ----------
    params : BVARParams
        Hyperparameters (lags, convergence threshold, max iterations).
    verbose : bool
        Print progress.

    Examples
    --------
    >>> from nowcasting_toolbox.config import BVARParams
    >>> params = BVARParams(bvar_lags=5)
    >>> bvar = BVAR(params)
    >>> result = bvar.fit(X, datet)
    """

    def __init__(
        self,
        params: Optional[BVARParams] = None,
        verbose: bool = False,
    ) -> None:
        self.params = params or BVARParams()
        self.verbose = verbose
        self.result_: Optional[BVARResult] = None

    def fit(
        self,
        X: FloatArray,
        datet: FloatArray | None = None,
    ) -> BVARResult:
        """Estimate the BVAR on mixed-frequency data.

        Parameters
        ----------
        X : (T, N) array.
            Mixed-frequency data where:
            - Monthly variables come first (nM columns)
            - Quarterly target comes last
            Missing values indicated by NaN.
        datet : (T, 2) array, optional
            Year-month for each row. Used for output dimension matching.

        Returns
        -------
        BVARResult
        """
        lags = self.params.bvar_lags
        thresh = self.params.bvar_thresh
        max_iter = self.params.bvar_max_iter

        T, N = X.shape

        # ---------- Fill and reshape for block-BVAR ----------
        X_filled = _fill_leading_nan(X)

        # Monthly variables (block-structured for mixed-frequency)
        nM = N - 1  # last column = quarterly target
        mSeries = list(range(nM))
        stationary = list(range(N))  # assume all stationary for now

        # ---------- Run block-BVAR ----------
        try:
            result = block_bvar(
                X_filled,
                lags,
                mSeries,
                stationary,
                thresh=thresh,
                max_iter=max_iter,
                n_draws=self.params.bvar_n_draws,
                burn_in=self.params.bvar_burn_in,
            )
        except Exception as exc:
            logger.error("BVAR estimation failed: %s", exc)
            self.result_ = BVARResult(X_sm=X_filled)
            return self.result_

        X_sm = result["X_sm"]

        # Match dimensions to input
        if X_sm.shape[0] > T:
            X_sm = X_sm[:T, :]
        elif X_sm.shape[0] < T:
            pad = np.full((T - X_sm.shape[0], N), np.nan)
            X_sm = np.vstack([pad, X_sm])

        self.result_ = BVARResult(
            X_sm=X_sm,
            B=result.get("B"),
            Sigma=result.get("Sigma"),
            B_draws=result.get("B_draws"),
            Sigma_draws=result.get("Sigma_draws"),
            lambda_opt=float(result.get("lambda", 0.2)),
            theta_opt=float(result.get("theta", 1.0)),
            miu_opt=float(result.get("miu", 1.0)),
            alpha_opt=float(result.get("alpha", 2.0)),
        )
        return self.result_

    @property
    def result(self) -> BVARResult:
        if self.result_ is None:
            raise RuntimeError("BVAR not yet fitted. Call .fit(X) first.")
        return self.result_


def _fill_leading_nan(X: FloatArray) -> FloatArray:
    """Fill NaN at the start of series with linear interpolation."""
    X_out = X.copy()
    T, N = X.shape
    for j in range(N):
        col = X_out[:, j]
        valid = np.where(~np.isnan(col))[0]
        if len(valid) == 0:
            continue
        first = valid[0]
        if first > 0:
            # Forward-fill from first valid value
            X_out[:first, j] = col[first]
    return X_out
