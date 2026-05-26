"""BEQ estimation entry point — mirrors BEQ_estimate.m."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from nowcasting_toolbox.config import BEQParams
from nowcasting_toolbox.beq.interpolate import extrapolate_bvar
from nowcasting_toolbox.beq.combinations import generate_combinations
from nowcasting_toolbox.beq.forecast import bridge_forecast
from nowcasting_toolbox.data.calendar import month_to_quarter_indices

logger = logging.getLogger(__name__)
FloatArray = NDArray[np.float64]


@dataclass
class BEQResult:
    """Container for BEQ results."""
    Y_fcst: FloatArray               # (Tq,) median forecast
    Y_fcst_indiv: FloatArray          # (Tq, n_specs) individual forecasts
    X_sm: FloatArray                  # (T, N) data with interpolated target
    beq_combinations: FloatArray      # (n_specs, 4) specifications
    coeffs: FloatArray                # (n_specs, n_coeffs) coefficients
    contrib: FloatArray               # (Tq, n_vars, n_specs) contributions
    contrib_names: list[str] = field(default_factory=list)
    Date_fcst: Optional[FloatArray] = None


class BEQ:
    """Bridge Equations estimator.

    Parameters
    ----------
    params : BEQParams
    verbose : bool
    """

    def __init__(
        self,
        params: Optional[BEQParams] = None,
        verbose: bool = False,
    ) -> None:
        self.params = params or BEQParams()
        self.verbose = verbose
        self.result_: Optional[BEQResult] = None

    def fit(
        self,
        X: FloatArray,
        datet: FloatArray,
        nameseries: list[str] | None = None,
    ) -> BEQResult:
        """Estimate the BEQ ensemble.

        Parameters
        ----------
        X : (T, N) array — monthly vars first, quarterly target last.
        datet : (T, 2) year-month.
        nameseries : list[str], optional.

        Returns
        -------
        BEQResult
        """
        p = self.params
        nM = max(X.shape[1] - 1, 1)
        nQ = 1

        # Separate monthly and quarterly
        Xm_raw = X[:, :nM]
        Xq_raw = X[:, nM:nM + nQ]  # target
        Y = Xq_raw[datet[:, 1] % 3 == 0, -1]
        dateQ = datet[datet[:, 1] % 3 == 0]

        if len(Y) == 0:
            self.result_ = BEQResult(
                Y_fcst=np.array([]),
                Y_fcst_indiv=np.array([]),
                X_sm=X,
                beq_combinations=np.array([]),
                coeffs=np.array([]),
                contrib=np.array([]),
            )
            return self.result_

        # Generate bridge equation specs
        spec_types = [int(p.type)] if int(p.type) < 904 else [901, 902, 903]
        specs = generate_combinations(nM, nQ, spec_types)
        n_specs = len(specs)

        Y_fcst_indiv = np.full((len(Y), n_specs), np.nan)

        for i in range(n_specs):
            spec = specs[i]
            interp_type = int(spec[0])
            m1 = int(spec[1]) if not np.isnan(spec[1]) else None
            m2 = int(spec[2]) if not np.isnan(spec[2]) else None

            # Select monthly regressors
            sel_m = [idx for idx in [m1, m2] if idx is not None]
            if not sel_m:
                continue

            Xm_sel = Xm_raw[:, sel_m]

            # Interpolate
            Xm_interp = extrapolate_bvar(Xm_sel, method=interp_type)

            # Forecast
            Y_fcst_i, _, _, _ = bridge_forecast(
                Xm_interp, datet, None, Y, dateQ,
                lagM=p.lagM, lagQ=p.lagQ, lagY=p.lagY,
            )
            Y_fcst_indiv[:, i] = Y_fcst_i

        # Median combination
        Y_fcst = np.nanmedian(Y_fcst_indiv, axis=1)

        # Build X_sm
        X_sm = X.copy()
        for ii in range(len(Y)):
            t = np.where((datet[:, 0] == dateQ[ii, 0]) & (datet[:, 1] == dateQ[ii, 1]))[0]
            if len(t) > 0:
                X_sm[t[0], -1] = Y_fcst[ii]

        self.result_ = BEQResult(
            Y_fcst=Y_fcst,
            Y_fcst_indiv=Y_fcst_indiv,
            X_sm=X_sm,
            beq_combinations=specs,
            coeffs=np.array([]),
            contrib=np.array([]),
            Date_fcst=dateQ,
        )
        return self.result_

    @property
    def result(self) -> BEQResult:
        if self.result_ is None:
            raise RuntimeError("BEQ not yet fitted. Call .fit(X, datet) first.")
        return self.result_
