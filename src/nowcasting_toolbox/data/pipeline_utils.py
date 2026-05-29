"""Shared data pipeline utilities for loading and transforming Malaysian data.

This module extracts the common data loading pattern used across scripts
and CLI commands to reduce code duplication.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.bnm import fetch_interest_rate_history, fetch_exchange_rate_history
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series

logger = logging.getLogger(__name__)
FloatArray = NDArray[np.float64]

# Default dataset configuration
DEFAULT_DATASETS = {
    "ipi": ("ipi", "index", 0, "industry", {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, "prices", {"division": "overall"}),
    "cpi_core": ("cpi_core", "index", 1, "prices", {"division": "overall"}),
    "ppi": ("ppi", "index", 1, "prices", {"series": "abs"}),
    "u_rate": ("lfs_month", "u_rate", 0, "labour", {}),
    "p_rate": ("lfs_month", "p_rate", 0, "labour", {}),
    "u_rate_youth": ("lfs_month_youth", "u_rate_15_30", 0, "labour", {}),
    "leading": ("economic_indicators", "leading", 1, "leading", {}),
    "coincident": ("economic_indicators", "coincident", 1, "coincident", {}),
    "exports": ("trade_headline", "exports", 1, "external", {"series": "abs"}),
    "imports_capital": ("trade_enduse_bec", "imports", 0, "external", {"bec": "000", "end_use": "capital", "series": "growth_mom"}),
    "imports_consumer": ("trade_enduse_bec", "imports", 0, "external", {"bec": "000", "end_use": "consumption", "series": "growth_mom"}),
    "wrt": ("iowrt", "sales", 1, "services", {"series": "abs"}),
    "wrt_volume": ("iowrt", "volume", 1, "consumption", {"series": "abs"}),
    "gdp": ("gdp_qtr_real_sa", "value", 0, "target", {"series": "abs"}),
}


@dataclass
class PipelineData:
    """Container for loaded and transformed pipeline data."""
    X_raw: FloatArray       # (T, N) raw data matrix
    X_trans: FloatArray     # (T, N) transformed data
    datet: FloatArray       # (T, 2) year-month
    var_names: list[str]    # variable names
    groups: list[str]       # group labels
    mu: FloatArray          # (N,) means for standardization
    sigma: FloatArray       # (N,) std devs for standardization
    filtered: dict          # raw DataFrames by name


def load_pipeline_data(
    datasets: Optional[dict] = None,
    start_year: int = 2018,
    start_month: int = 1,
    ttl_hours: int = 6,
    include_bnm: bool = True,
    verbose: bool = False,
) -> PipelineData:
    """Load and transform Malaysian data for the nowcasting pipeline.

    This is the shared implementation used by daily_update.py, backtest scripts,
    and CLI commands (select-vars, news).

    Parameters
    ----------
    datasets : dict, optional
        Dataset configuration. If None, uses DEFAULT_DATASETS.
    start_year : int
        Start year for the date grid.
    start_month : int
        Start month for the date grid.
    ttl_hours : int
        Cache TTL in hours.
    include_bnm : bool
        Whether to fetch BNM financial data (interbank rate, FX).
    verbose : bool
        Print progress.

    Returns
    -------
    PipelineData
    """
    if datasets is None:
        datasets = DEFAULT_DATASETS

    cache = DataCache(ttl_hours=ttl_hours)
    client = OpenDOSMClient()

    # Separate monthly and target
    MN = [n for n in datasets if n != "gdp"]
    AN = MN + ["gdp"]

    # Fetch OpenDOSM data
    filtered = {}
    for name, (did, col, tcode, group, filters) in datasets.items():
        df = cache.get(did)
        if df is None:
            df = client.fetch(did, limit=20000)
            if df is not None and not df.empty:
                cache.put(did, df)
        if df is None or df.empty:
            if verbose:
                logger.warning("Skipping %s — no data", name)
            continue
        df = df.copy()
        for fc, fv in filters.items():
            if fc in df.columns:
                df = df[df[fc] == fv]
        if col not in df.columns:
            continue
        df = df[["date", col]].dropna().rename(columns={col: name})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates("date")
        filtered[name] = df

    # Convert % growth to decimal
    for var in ["ipi", "imports_capital", "imports_consumer"]:
        if var in filtered:
            filtered[var][var] = filtered[var][var] / 100.0

    # Fetch BNM data
    if include_bnm:
        try:
            ir_df = fetch_interest_rate_history(start_year=start_year, verbose=False)
            if not ir_df.empty:
                ir_df = ir_df.rename(columns={"value": "interbank"})
                filtered["interbank"] = ir_df[["date", "interbank"]]
        except Exception as e:
            if verbose:
                logger.warning("BNM interest rate failed: %s", e)
        try:
            fx_df = fetch_exchange_rate_history(start_year=start_year, currency_code="USD", verbose=False)
            if not fx_df.empty:
                fx_vals = fx_df["value"].values
                fx_growth = np.full(len(fx_vals), np.nan)
                for i in range(1, len(fx_vals)):
                    if fx_vals[i-1] > 0:
                        fx_growth[i] = np.log(fx_vals[i]) - np.log(fx_vals[i-1])
                fx_df["fx_usd"] = fx_growth
                fx_df = fx_df.dropna(subset=["fx_usd"])
                filtered["fx_usd"] = fx_df[["date", "fx_usd"]]
        except Exception as e:
            if verbose:
                logger.warning("BNM FX rate failed: %s", e)

    client.close()

    # Compute GDP QoQ
    if "gdp" not in filtered:
        raise RuntimeError("GDP data not available")

    gdp_df = filtered["gdp"].copy().sort_values("date")
    gv = gdp_df["gdp"].values
    gq = np.full(len(gv), np.nan)
    for i in range(1, len(gv)):
        if gv[i-1] > 0:
            gq[i] = (gv[i] - gv[i-1]) / gv[i-1]
    gdp_df["gdp"] = gq
    gdp_df = gdp_df.dropna(subset=["gdp"])
    filtered["gdp"] = gdp_df

    # Build date grid
    md = [df["date"].min() for df in filtered.values()]
    Mx = [df["date"].max() for df in filtered.values()]
    gd = max(filtered["gdp"]["date"].min(), pd.Timestamp(f"{start_year}-{start_month:02d}-01"))
    ed = max(Mx)
    datet = generate_dates(gd.year, gd.month, ed.year, ed.month)
    T = len(datet)

    # Build data matrix
    var_names = [n for n in AN if n in filtered]
    N = len(var_names)
    X_raw = np.full((T, N), np.nan)

    for j, name in enumerate(var_names):
        df = filtered[name]
        for _, row in df.iterrows():
            y, m = row["date"].year, row["date"].month
            if name == "gdp":
                # Place quarterly GDP at quarter-end month
                qem = ((m - 1) // 3) * 3 + 3
                idx = np.where((datet[:, 0] == y) & (datet[:, 1] == qem))[0]
            else:
                idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
            if len(idx) > 0:
                X_raw[idx[0], j] = row[name]

    # Transform
    X_trans = X_raw.copy()
    for j, name in enumerate(var_names):
        if name in datasets:
            tcode = datasets[name][2]
            freq = "quarterly" if name == "gdp" else "monthly"
            X_trans[:, j] = transform_series(X_raw[:, j].copy(), tcode, freq)

    # Standardize
    mu = np.nanmean(X_trans, axis=0)
    sigma = np.nanstd(X_trans, axis=0)
    sigma[sigma < 1e-10] = 1.0

    # Groups
    groups = []
    for name in var_names:
        if name in datasets:
            groups.append(datasets[name][3])
        elif name == "interbank":
            groups.append("financial")
        elif name == "fx_usd":
            groups.append("financial")
        else:
            groups.append("other")

    return PipelineData(
        X_raw=X_raw,
        X_trans=X_trans,
        datet=datet,
        var_names=var_names,
        groups=groups,
        mu=mu,
        sigma=sigma,
        filtered=filtered,
    )
