"""Bridge equation forecast: OLS estimation + prediction.

Replicates BEQ_forecast.m — runs a single bridge equation,
produces forecasts and contribution decomposition.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def bridge_forecast(
    Xm: FloatArray,
    datet: FloatArray,
    Xq: FloatArray | None,
    Y: FloatArray,
    dateQ: FloatArray,
    lagM: int = 1,
    lagQ: int = 1,
    lagY: int = 1,
    dummies: FloatArray | None = None,
    re_estimate: bool = True,
    coeffs_in: FloatArray | None = None,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Run a single bridge equation forecast.

    Parameters
    ----------
    Xm : (T, nM_sel) array
        Selected monthly regressors (already interpolated).
    datet : (T, 2) year-month.
    Xq : (Tq, nQ_sel) array or None
        Selected quarterly regressors (optional).
    Y : (Tq,) array
        Quarterly target variable.
    dateQ : (Tq, 2) year-quarter months.
    lagM, lagQ, lagY : int
        Lags for monthly, quarterly, endogenous.
    dummies : (Tq, n_dum) array, optional
        Dummy variables.
    re_estimate : bool
        If True, estimate OLS. If False, use coeffs_in.
    coeffs_in : (n_coeffs,) array, optional
        Pre-estimated coefficients.

    Returns
    -------
    Y_fcst : (Tq,) forecast values
    date_fcst : (Tq_out, 2) forecast dates
    contributions : (Tq, n_vars+1) contribution decomposition
    coeffs : (n_coeffs,) estimated coefficients
    """
    Tq = len(Y)
    T = Xm.shape[0]
    nM_sel = Xm.shape[1]
    nQ_sel = Xq.shape[1] if Xq is not None else 0

    # Build regression matrix at quarterly frequency
    idx_q3 = np.where(datet[:, 1] % 3 == 0)[0]

    # Monthly regressors (aggregated to quarterly via 3rd-month value)
    Xm_q = Xm[idx_q3] if len(idx_q3) > 0 else np.zeros((0, nM_sel))

    # Build lagged monthly regressors
    X_regs = []
    var_names = []

    # Monthly contemporaneous + lags
    for lag in range(lagM + 1):
        if lag == 0:
            X_regs.append(Xm_q[lagY: Tq - lagM + lagY or None])
        else:
            X_regs.append(Xm_q[lagY - lag: Tq - lagM + lagY - lag or None])
        var_names.append(f"M_lag{lag}")

    # Quarterly regressors
    if Xq is not None and nQ_sel > 0:
        for lag in range(lagQ + 1):
            start = max(0, lagY - lag)
            end = Tq - lag
            X_regs.append(Xq[start:end])
            var_names.append(f"Q_lag{lag}")

    # Lagged endogenous
    if lagY > 0:
        Y_lag = np.roll(Y, lagY)
        Y_lag[:lagY] = np.nan
        X_regs.append(Y_lag.reshape(-1, 1))
        var_names.append("Y_lag")

    # Dummies
    if dummies is not None:
        X_regs.append(dummies[:len(Y)])
        var_names.append("Dummies")

    # Add constant
    X_regs.append(np.ones((len(Y), 1)))
    var_names.append("Constant")

    # Stack regressors — align lengths properly
    min_rows = min(r.shape[0] for r in X_regs)
    # Trim all regressors to the same length (removes leading obs lost to lags)
    X_regs_aligned = [r[:min_rows] for r in X_regs]

    if min_rows < max(lagM, lagQ, lagY) + 2:
        return np.full(Tq, np.nan), dateQ[:Tq], np.zeros((Tq, len(var_names))), np.zeros(len(var_names))

    X_fit = np.column_stack(X_regs_aligned)
    Y_fit = Y[-min_rows:]  # align Y to the same window

    # OLS estimation. Impute NaN in monthly/quarterly regressors with 0.0 —
    # consistent with the prediction phase below ("missing monthly data = no
    # contribution") — so a few sparse regressors don't discard entire
    # quarters. Previously a row was valid only if ALL regressors were non-NaN,
    # which starved the 27-variable GDP equation of fit rows and yielded an
    # all-NaN forecast. Y_lag is the second-to-last column (Constant is last);
    # leave its NaN intact so rows with an unknown lagged target still drop.
    ylag_col = X_fit.shape[1] - 2 if lagY > 0 else None
    for k in range(X_fit.shape[1]):
        if k == ylag_col:
            continue
        col = X_fit[:, k]
        nan_mask = np.isnan(col)
        if np.any(nan_mask):
            X_fit[:, k] = np.where(nan_mask, 0.0, col)

    valid_rows = ~np.any(np.isnan(X_fit), axis=1) & ~np.isnan(Y_fit)
    if np.sum(valid_rows) < max(lagM, lagQ, lagY) + 2:
        return np.full(Tq, np.nan), dateQ[:Tq], np.zeros((Tq, len(var_names))), np.zeros(len(var_names))

    try:
        coeffs, resid, rank, sv = np.linalg.lstsq(
            X_fit[valid_rows], Y_fit[valid_rows], rcond=None
        )
    except np.linalg.LinAlgError:
        return np.full(Tq, np.nan), dateQ[:Tq], np.zeros((Tq, len(var_names))), np.zeros(len(var_names))

    # Predictions — use X_fit for in-sample, build full X for all quarters
    # For trailing quarters where Y_lag is NaN (GDP not yet released),
    # use the most recent known Y value as proxy (persistence)
    X_pred = X_fit.copy()
    for k, vname in enumerate(var_names):
        if vname == "Y_lag":
            col = X_pred[:, k].copy()
            nan_mask = np.isnan(col)
            if np.any(nan_mask):
                # Fill trailing NaN with last valid value of Y (not Y_lag)
                valid_y = np.where(~np.isnan(Y_fit))[0]
                if len(valid_y) > 0:
                    last_valid_y_val = Y_fit[valid_y[-1]]
                    col[nan_mask] = last_valid_y_val
            X_pred[:, k] = col
        else:
            # For non-Y_lag columns, set NaN to 0 (missing monthly data = no contribution)
            col = X_pred[:, k].copy()
            col[np.isnan(col)] = 0.0
            X_pred[:, k] = col

    Y_fcst_fit = X_pred @ coeffs  # (min_rows,) forecasts

    # Pad to full Tq length: prepend NaN for leading rows lost to lags
    Y_fcst = np.full(Tq, np.nan)
    Y_fcst[-min_rows:] = Y_fcst_fit

    # Contribution decomposition
    contributions = np.zeros((Tq, len(var_names)))
    for k in range(len(var_names)):
        contrib_fit = X_pred[:, k] * coeffs[k]
        contributions[-min_rows:, k] = contrib_fit

    return Y_fcst, dateQ[:Tq], contributions, coeffs
