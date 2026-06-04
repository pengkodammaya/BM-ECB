"""CLI service layer: data loading and processing for select-vars and news commands.

Extracted from cli/main.py to keep CLI functions small and testable.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series

logger = logging.getLogger(__name__)


def load_indicator_data(
    datasets: dict,
    cache_ttl_hours: int = 24,
) -> tuple[dict[str, pd.DataFrame], dict[str, dict]]:
    """Load indicator data from OpenDOSM API with caching.

    Parameters
    ----------
    datasets : dict
        Dataset specification dict {name: (dataset_id, col, tcode, group, filters, ...)}.
    cache_ttl_hours : int
        Cache TTL in hours.

    Returns
    -------
    filtered : dict[str, pd.DataFrame]
        Filtered DataFrames keyed by variable name.
    var_meta : dict[str, dict]
        Metadata for each variable (group, lag_days, freq).
    """
    cache = DataCache(ttl_hours=cache_ttl_hours)
    client = OpenDOSMClient()
    filtered = {}
    var_meta = {}

    for name, spec in datasets.items():
        did = spec[0]
        col = spec[1]
        filters = spec[4] if len(spec) > 4 else {}

        try:
            df = cache.get(did)
            if df is None:
                df = client.fetch(did, limit=20000)
                if df is not None and not df.empty:
                    cache.put(did, df)
            if df is None or df.empty:
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

            # Extract metadata if available
            if len(spec) >= 7:
                var_meta[name] = {
                    "group": spec[3],
                    "lag_days": spec[5],
                    "freq": spec[6],
                }
        except Exception as e:
            logger.warning("Failed to load %s: %s", name, e)

    client.close()
    return filtered, var_meta


def prepare_gdp_qoq(gdp_df: pd.DataFrame) -> pd.DataFrame:
    """Convert GDP levels to QoQ growth rates.

    Parameters
    ----------
    gdp_df : pd.DataFrame
        DataFrame with 'date' and 'gdp' columns (absolute levels).

    Returns
    -------
    pd.DataFrame
        DataFrame with QoQ growth rates.
    """
    gdp_df = gdp_df.copy().sort_values("date")
    gv = gdp_df["gdp"].values
    gq = np.full(len(gv), np.nan)
    for i in range(1, len(gv)):
        if gv[i-1] > 0:
            gq[i] = (gv[i] - gv[i-1]) / gv[i-1]
    gdp_df["gdp"] = gq
    return gdp_df.dropna(subset=["gdp"])


def build_monthly_grid(
    filtered: dict[str, pd.DataFrame],
    datasets: dict,
    start_year: int = 2018,
    start_month: int = 1,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Build monthly data grid from filtered DataFrames.

    Parameters
    ----------
    filtered : dict[str, pd.DataFrame]
        Filtered DataFrames keyed by variable name.
    datasets : dict
        Dataset specification dict.
    start_year : int
        Start year for the grid.
    start_month : int
        Start month for the grid.

    Returns
    -------
    X : (T, N) array
        Data matrix with monthly indicators + quarterly GDP.
    datet : (T, 2) array
        Year-month for each row.
    mn : list[str]
        Monthly variable names.
    """
    mn = [n for n in datasets if n != "gdp" and n in filtered]
    Mx = [df["date"].max() for df in filtered.values()]
    gd = max(filtered["gdp"]["date"].min(), pd.Timestamp(f"{start_year}-{start_month:02d}-01"))
    ed = max(Mx)
    datet = generate_dates(gd.year, gd.month, ed.year, ed.month)
    T = len(datet)
    X = np.full((T, len(mn) + 1), np.nan)

    for j, name in enumerate(mn):
        df = filtered[name]
        for _, row in df.iterrows():
            y, m = row["date"].year, row["date"].month
            idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
            if len(idx) > 0:
                X[idx[0], j] = row[name]

    gdp_df_q = filtered["gdp"]
    for _, row in gdp_df_q.iterrows():
        y, m = row["date"].year, row["date"].month
        qem = ((m - 1) // 3) * 3 + 3
        idx = np.where((datet[:, 0] == y) & (datet[:, 1] == qem))[0]
        if len(idx) > 0:
            X[idx[0], -1] = row["gdp"]

    return X, datet, mn


def apply_transforms(
    X: np.ndarray,
    mn: list[str],
    datasets: dict,
) -> np.ndarray:
    """Apply stationarity transforms to monthly indicators.

    Parameters
    ----------
    X : (T, N) array
        Raw data matrix.
    mn : list[str]
        Monthly variable names.
    datasets : dict
        Dataset specification dict.

    Returns
    -------
    X_trans : (T, N) array
        Transformed data matrix.
    """
    X_trans = X.copy()
    for j, name in enumerate(mn):
        tcode = datasets[name][2]
        X_trans[:, j] = transform_series(X[:, j].copy(), tcode, "monthly")
    return X_trans


def align_quarterly(
    X_trans: np.ndarray,
    mn: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Align data to quarterly frequency (GDP observation months).

    Parameters
    ----------
    X_trans : (T, N) array
        Transformed data matrix.
    mn : list[str]
        Monthly variable names.

    Returns
    -------
    X_valid : (T_q, n_monthly) array
        Monthly indicators at GDP observation months.
    y_valid : (T_q,) array
        GDP values at observation months.
    """
    gdp_col = -1
    gdp_rows = ~np.isnan(X_trans[:, gdp_col])
    X_monthly = X_trans[gdp_rows, :len(mn)]
    y_target = X_trans[gdp_rows, gdp_col]

    valid = ~np.any(np.isnan(X_monthly), axis=1) & ~np.isnan(y_target)
    return X_monthly[valid], y_target[valid]


def load_vintage_data(
    old_date: date,
    new_date: date,
    datasets: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Load and build vintages for news decomposition.

    Parameters
    ----------
    old_date : date
        Old vintage date.
    new_date : date
        New vintage date.
    datasets : dict
        Dataset specification dict.

    Returns
    -------
    X_old_std : (T, N) array
        Standardized old vintage.
    X_new_std : (T, N) array
        Standardized new vintage.
    datet : (T, 2) array
        Year-month for each row.
    AN : list[str]
        All variable names (monthly + GDP).
    """
    from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule
    from nowcasting_toolbox.eval.vintage import ARCVintageBuilder

    MN = [n for n in datasets if n != "gdp"]
    AN = MN + ["gdp"]

    # Load data
    filtered, _ = load_indicator_data(datasets, cache_ttl_hours=6)

    if "ipi" in filtered:
        filtered["ipi"]["ipi"] = filtered["ipi"]["ipi"] / 100.0

    # GDP QoQ
    if "gdp" in filtered:
        filtered["gdp"] = prepare_gdp_qoq(filtered["gdp"])

    # Build grid
    Mx = [df["date"].max() for df in filtered.values()]
    gd = max(filtered["gdp"]["date"].min(), pd.Timestamp("2018-01-01"))
    ed = max(Mx)
    datet_full = generate_dates(gd.year, gd.month, ed.year, ed.month)
    T = len(datet_full)
    X_full = np.full((T, len(MN) + 1), np.nan)

    for j, name in enumerate(MN):
        df = filtered[name]
        for _, row in df.iterrows():
            y, m = row["date"].year, row["date"].month
            idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == m))[0]
            if len(idx) > 0:
                X_full[idx[0], j] = row[name]

    gdp_df_q = filtered["gdp"]
    for _, row in gdp_df_q.iterrows():
        y, m = row["date"].year, row["date"].month
        qem = ((m - 1) // 3) * 3 + 3
        idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == qem))[0]
        if len(idx) > 0:
            X_full[idx[0], -1] = row["gdp"]

    X_trans = X_full.copy()
    for j, name in enumerate(AN):
        tcode = datasets[name][2]
        freq = "quarterly" if name == "gdp" else "monthly"
        X_trans[:, j] = transform_series(X_full[:, j].copy(), tcode, freq)

    mu = np.nanmean(X_trans, axis=0)
    sigma = np.nanstd(X_trans, axis=0)
    sigma[sigma < 1e-10] = 1.0
    X_raw = X_trans.copy()
    ff = np.where(~np.all(np.isnan(X_raw), axis=1))[0][0]
    X_raw = X_raw[ff:]
    datet = datet_full[ff:]

    # Vintage builder
    arc_schedule = build_publication_schedule(years=[2023, 2024, 2025, 2026], cache_dir=Path("data/malaysia"))
    vb = ARCVintageBuilder(schedule=arc_schedule)
    DID_MAP = ["ipi", "cpi_headline", "cpi_core", "ppi", "u_rate", "p_rate", "leading", "coincident", "exports", "wrt", "gdp"]

    # Build vintages
    X_old_raw = vb.build(X_raw.copy(), datet, old_date, var_names=AN, dataset_ids=DID_MAP)
    X_new_raw = vb.build(X_raw.copy(), datet, new_date, var_names=AN, dataset_ids=DID_MAP)

    # Standardize
    vint_mu = np.nanmean(X_old_raw, axis=0)
    vint_sigma = np.nanstd(X_old_raw, axis=0)
    vint_sigma[vint_sigma < 1e-10] = 1.0
    X_old_std = (X_old_raw - vint_mu) / vint_sigma
    X_new_std = (X_new_raw - vint_mu) / vint_sigma
    valid_rows = ~np.all(np.isnan(X_old_std), axis=1)
    first = np.where(valid_rows)[0][0]
    X_old_std = X_old_std[first:]
    X_new_std = X_new_std[first:]

    return X_old_std, X_new_std, datet[first:], AN
