"""Pseudo-real-time backtesting engine."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from nowcasting_toolbox.config import ToolboxConfig
from nowcasting_toolbox.eval.metrics import compute_mae, compute_fda, compute_rmse

logger = logging.getLogger(__name__)
FloatArray = NDArray[np.float64]


def run_backtest(
    config: ToolboxConfig,
    X_full: FloatArray,
    datet: FloatArray,
) -> pd.DataFrame:
    """Run pseudo-real-time backtest.

    For each evaluation date, simulate the data that WOULD have been
    available at that point (using publication lags), fit the model,
    produce a nowcast, and compare to the actual GDP release.

    Parameters
    ----------
    config : ToolboxConfig
        Must have do_eval=1, eval start/end dates set.
    X_full : (T, N) full data matrix (complete history).
    datet : (T, 2) year-month.

    Returns
    -------
    pd.DataFrame with columns:
        vintage_date, actual_gdp, nowcast_dfm, nowcast_bvar, nowcast_beq,
        mae_dfm, fda_dfm, ...
    """
    ev = config.eval
    start_idx = _find_idx(datet, ev.eval_startyear, ev.eval_startmonth)
    end_idx = _find_idx(datet, ev.eval_endyear, ev.eval_endmonth)

    results = []
    gdp_col = -1

    for t in range(start_idx, end_idx + 1):
        # Simulate available data up to time t (ragged edge)
        X_available = _apply_ragged_edge(X_full, datet, t, config)

        vintage_date = f"{datet[t, 0]}-{datet[t, 1]:02d}"
        actual_gdp = X_full[t, gdp_col]

        row = {"vintage_date": vintage_date, "actual_gdp": actual_gdp}

        for model_type in ["dfm", "bvar", "beq"]:
            try:
                pred = _nowcast_single(config, X_available, datet, model_type)
                row[f"nowcast_{model_type}"] = pred
            except Exception as exc:
                logger.warning("Backtest %s %s failed: %s", vintage_date, model_type, exc)
                row[f"nowcast_{model_type}"] = np.nan

        results.append(row)

    df = pd.DataFrame(results)

    # Compute evaluation metrics
    for model in ["dfm", "bvar", "beq"]:
        col = f"nowcast_{model}"
        if col not in df.columns:
            continue
        df[f"mae_{model}"] = np.nan
        df[f"fda_{model}"] = np.nan

    return df


def _nowcast_single(
    config: ToolboxConfig,
    X: FloatArray,
    datet: FloatArray,
    model_type: str,
) -> float:
    """Run a single nowcast for one model type."""
    if model_type == "dfm":
        from nowcasting_toolbox.dfm import DFM
        from nowcasting_toolbox.config import DFMParams
        model = DFM(DFMParams(r=config.dfm.r, p=config.dfm.p, max_iter=config.dfm.max_iter))
        res = model.fit(X)
        return float(res.X_sm[-1, -1])
    elif model_type == "bvar":
        from nowcasting_toolbox.bvar import BVAR
        from nowcasting_toolbox.config import BVARParams
        model = BVAR(BVARParams(bvar_lags=config.bvar.bvar_lags))
        res = model.fit(X, datet)
        return float(res.X_sm[-1, -1])
    elif model_type == "beq":
        from nowcasting_toolbox.beq import BEQ
        from nowcasting_toolbox.config import BEQParams
        model = BEQ(BEQParams(lagM=config.beq.lagM, lagQ=config.beq.lagQ, lagY=config.beq.lagY))
        res = model.fit(X, datet)
        return float(res.X_sm[-1, -1])
    return np.nan


def _apply_ragged_edge(
    X: FloatArray,
    datet: FloatArray,
    t: int,
    config: ToolboxConfig,
) -> FloatArray:
    """Simulate ragged-edge data at time t."""
    X_vint = X[:t + 1].copy()
    # TODO: apply actual publication lags from ARC
    return X_vint


def _find_idx(datet: FloatArray, year: int, month: int) -> int:
    mask = (datet[:, 0] == year) & (datet[:, 1] == month)
    indices = np.where(mask)[0]
    return int(indices[0]) if len(indices) > 0 else len(datet) - 1
