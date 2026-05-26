"""Unified data loader supporting Excel, CSV, Parquet, and API sources.

Replicates common_load_data.m from the MATLAB toolbox.
Produces a consistent output structure that feeds into all three model engines.

Excel format (matching toolbox):
    Sheet "Monthly"  — rows 0-2: transform code, group, header; rows 4+: data
    Sheet "Quarterly" — same layout
    Sheet "blocks"   — block factor assignment matrix

API mode uses the OpenDOSM + BNM clients and the registry.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

from nowcasting_toolbox.config import ToolboxConfig
from nowcasting_toolbox.data.calendar import (
    generate_dates,
    month_to_quarter_indices,
    month_of_quarter,
)
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.bnm import fetch_interest_rate_history, fetch_exchange_rate_history
from nowcasting_toolbox.data.sources.registry import (
    get_registry,
    get_meta,
    get_target,
    DatasetMeta,
    Frequency,
)
from nowcasting_toolbox.data.transforms import transform_matrix, TransformCode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output structure (mirrors common_load_data.m outputs)
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field


@dataclass
class LoadedData:
    """Container matching the MATLAB toolbox data structure."""

    xest: np.ndarray     # (T, N+1) data matrix — monthly vars then quarterly GDP then extra quarterly
    datet: np.ndarray    # (T, 2) year, month
    t_m: np.ndarray      # (T, 1) time index (1-based)
    groups: list[str]     # group label per variable (length N+1)
    nameseries: list[str]  # short name per variable
    fullnames: list[str]   # descriptive name per variable
    groups_name: list[str]  # unique group names
    blocks: np.ndarray    # (N+1, n_blocks) block factor assignment

    # Parameters
    nM: int               # number of monthly variables
    nQ: int               # number of quarterly variables (includes target)
    startyear: int
    startmonth: int

    # Transform codes per variable
    transf_m: list[int] = field(default_factory=list)
    transf_q: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------


def load_data(
    config: ToolboxConfig,
    source: str = "api",
    file_path: Optional[Union[str, Path]] = None,
) -> LoadedData:
    """Load data from the specified source.

    Parameters
    ----------
    config : ToolboxConfig
        Full toolbox configuration (controls start date, cache, subset, etc.).
    source : str
        ``"api"`` — fetch from OpenDOSM/BNM APIs via local cache.
        ``"excel"`` — read a toolbox-format Excel file.
        ``"csv"`` — read a CSV file (wide format, date column).
        ``"parquet"`` — read a Parquet file.
    file_path : Path or str, optional
        Required for "excel", "csv", "parquet" modes.

    Returns
    -------
    LoadedData
    """
    if source == "api":
        return _load_from_api(config)
    elif source == "excel":
        if file_path is None:
            raise ValueError("file_path required for excel mode")
        return _load_from_excel(Path(file_path), config)
    elif source == "csv":
        if file_path is None:
            raise ValueError("file_path required for csv mode")
        return _load_from_flat(Path(file_path), config, fmt="csv")
    elif source == "parquet":
        if file_path is None:
            raise ValueError("file_path required for parquet mode")
        return _load_from_flat(Path(file_path), config, fmt="parquet")
    else:
        raise ValueError(f"Unknown source: {source}")


# ---------------------------------------------------------------------------
# API loader
# ---------------------------------------------------------------------------


def _load_from_api(config: ToolboxConfig) -> LoadedData:
    """Fetch Malaysian data from OpenDOSM + BNM, build the toolbox-compatible dataset."""
    cache = DataCache(ttl_hours=config.cache_ttl_hours)
    dosm = OpenDOSMClient()

    registry = get_registry()
    target_meta = get_target()
    monthly_metas = [m for m in registry if m.frequency == Frequency.MONTHLY and not m.is_target]
    daily_metas = [m for m in registry if m.frequency == Frequency.DAILY]
    quarterly_extras = [m for m in registry if m.frequency == Frequency.QUARTERLY and not m.is_target]

    # ---------- fetch monthly indicators ----------
    monthly_dfs: list[pd.DataFrame] = []
    transf_m: list[int] = []
    names_m: list[str] = []
    fullnames_m: list[str] = []
    groups_m: list[str] = []

    for meta in monthly_metas:
        df = _cached_fetch(cache, dosm, meta)
        if df is None or df.empty:
            logger.info("Skipping %s — no data", meta.id)
            continue
        monthly_dfs.append(df)
        transf_m.append(int(meta.transform))
        names_m.append(meta.id)
        fullnames_m.append(meta.name)
        groups_m.append(meta.group)

    # ---------- fetch target (GDP) ----------
    gdp_df = _cached_fetch(cache, dosm, bnm, target_meta)
    if gdp_df is None or gdp_df.empty:
        raise RuntimeError("Target variable (GDP) not available from API")

    # ---------- align all monthly to common date grid ----------
    date_grid = _build_date_grid(config, monthly_dfs + [gdp_df])
    T = len(date_grid)

    # Build monthly block
    nM = len(monthly_dfs)
    Xm = np.full((T, nM), np.nan)
    for j, df in enumerate(monthly_dfs):
        Xm[:, j] = _align_to_grid(df, date_grid, "monthly")

    # Build quarterly block (target + extras)
    nQ = 1 + len(quarterly_extras)
    Xq = np.full((T, nQ), np.nan)
    # GDP target (last column)
    Xq[:, -1] = _align_to_grid(gdp_df, date_grid, "quarterly")
    # Quarterly extras
    for j, meta in enumerate(quarterly_extras):
        df = _cached_fetch(cache, dosm, meta)
        if df is not None and not df.empty:
            Xq[:, j] = _align_to_grid(df, date_grid, "quarterly")

    # ---------- assemble xest ----------
    xest = np.column_stack([Xm, Xq])

    transf_q = [int(TransformCode.QOQ_ANN)] * nQ  # quarterly data uses QoQ ann
    groups = groups_m + ["national_accounts"] * nQ
    nameseries = names_m + [target_meta.id] + [m.id for m in quarterly_extras]
    fullnames = fullnames_m + [target_meta.name] + [m.name for m in quarterly_extras]
    groups_name = sorted(set(groups))
    blocks = _build_blocks(groups, groups_name)

    # Trim to estimation sample
    startidx = _find_date_index(date_grid, config.startyear, config.startmonth)
    xest = xest[startidx:]
    datet = date_grid[startidx:]

    return LoadedData(
        xest=xest,
        datet=datet,
        t_m=np.arange(1, len(datet) + 1).reshape(-1, 1),
        groups=groups,
        nameseries=nameseries,
        fullnames=fullnames,
        groups_name=groups_name,
        blocks=blocks,
        nM=nM,
        nQ=nQ,
        startyear=config.startyear,
        startmonth=config.startmonth,
        transf_m=transf_m,
        transf_q=transf_q,
    )


# ---------------------------------------------------------------------------
# Excel loader (toolbox format)
# ---------------------------------------------------------------------------


def _load_from_excel(file_path: Path, config: ToolboxConfig) -> LoadedData:
    """Load data from a toolbox-format Excel file."""
    xl = pd.ExcelFile(file_path)

    # Parse Monthly sheet
    monthly_raw = pd.read_excel(xl, sheet_name="Monthly", header=None)
    transf_m_raw = monthly_raw.iloc[0, 1:].tolist()
    groups_m_raw = monthly_raw.iloc[1, 1:].tolist()
    names_m = monthly_raw.iloc[2, 1:].tolist()
    fullnames_m = monthly_raw.iloc[3, 1:].tolist()
    data_m = monthly_raw.iloc[4:].reset_index(drop=True)
    data_m.columns = ["date"] + names_m
    data_m["date"] = pd.to_datetime(
        pd.to_numeric(data_m["date"], errors="coerce"),
        unit="D",
        origin="1899-12-30",
    )

    # Parse Quarterly sheet
    quarterly_raw = pd.read_excel(xl, sheet_name="Quarterly", header=None)
    transf_q_raw = quarterly_raw.iloc[0, 1:].tolist()
    groups_q_raw = quarterly_raw.iloc[1, 1:].tolist()
    names_q = quarterly_raw.iloc[2, 1:].tolist()
    fullnames_q = quarterly_raw.iloc[3, 1:].tolist()
    data_q = quarterly_raw.iloc[4:].reset_index(drop=True)
    data_q.columns = ["date"] + names_q
    data_q["date"] = pd.to_datetime(
        pd.to_numeric(data_q["date"], errors="coerce"),
        unit="D",
        origin="1899-12-30",
    )

    # Merge on a common monthly grid
    date_grid = _build_date_grid(config, [data_m, data_q])
    T = len(date_grid)

    nM = len(names_m)
    nQ = len(names_q)
    Xm = np.full((T, nM), np.nan)
    for j, name in enumerate(names_m):
        Xm[:, j] = _align_to_grid(data_m, date_grid, "monthly", col=name)

    Xq = np.full((T, nQ), np.nan)
    for j, name in enumerate(names_q):
        Xq[:, j] = _align_to_grid(data_q, date_grid, "quarterly", col=name)

    xest = np.column_stack([Xm, Xq])

    # Groups / blocks
    groups = groups_m_raw + groups_q_raw
    nameseries = names_m + names_q
    fullnames = fullnames_m + fullnames_q
    groups_name = sorted(set(groups))
    blocks = _build_blocks(groups, groups_name)

    # Parse blocks sheet if present
    if "blocks" in xl.sheet_names:
        blocks_df = pd.read_excel(xl, sheet_name="blocks", header=None)
        blocks = blocks_df.to_numpy(dtype=float)

    # Trim to estimation sample
    startidx = _find_date_index(date_grid, config.startyear, config.startmonth)
    xest = xest[startidx:]
    datet = date_grid[startidx:]

    return LoadedData(
        xest=xest,
        datet=datet,
        t_m=np.arange(1, len(datet) + 1).reshape(-1, 1),
        groups=groups,
        nameseries=nameseries,
        fullnames=fullnames,
        groups_name=groups_name,
        blocks=blocks,
        nM=nM,
        nQ=nQ,
        startyear=config.startyear,
        startmonth=config.startmonth,
        transf_m=[int(c) for c in transf_m_raw],
        transf_q=[int(c) for c in transf_q_raw],
    )


# ---------------------------------------------------------------------------
# Flat file loader (CSV / Parquet)
# ---------------------------------------------------------------------------


def _load_from_flat(file_path: Path, config: ToolboxConfig, fmt: str) -> LoadedData:
    """Load from a CSV or Parquet file with columns: date, series1, series2, ...
    Monthly variables first, then quarterly. Metadata passed via config or defaults.
    """
    if fmt == "csv":
        df = pd.read_csv(file_path)
    else:
        df = pd.read_parquet(file_path)

    if "date" not in df.columns:
        raise ValueError("Flat file must have a 'date' column")

    df["date"] = pd.to_datetime(df["date"])
    date_grid = _build_date_grid(config, [df])
    T = len(date_grid)

    # Assume all columns except 'date' are data, split evenly
    data_cols = [c for c in df.columns if c != "date"]
    N = len(data_cols)
    nM = N // 2
    nQ = N - nM

    X = np.full((T, N), np.nan)
    for j, col in enumerate(data_cols):
        X[:, j] = _align_to_grid(df, date_grid, "monthly", col=col)

    xest = X
    startidx = _find_date_index(date_grid, config.startyear, config.startmonth)

    return LoadedData(
        xest=xest[startidx:],
        datet=date_grid[startidx:],
        t_m=np.arange(1, T - startidx + 1).reshape(-1, 1),
        groups=["group1"] * nM + ["target"] * nQ,
        nameseries=data_cols,
        fullnames=data_cols,
        groups_name=["group1", "target"],
        blocks=np.ones((N, 1)),
        nM=nM,
        nQ=nQ,
        startyear=config.startyear,
        startmonth=config.startmonth,
        transf_m=[1] * nM,
        transf_q=[3] * nQ,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cached_fetch(
    cache: DataCache,
    dosm: OpenDOSMClient,
    meta: DatasetMeta,
) -> Optional[pd.DataFrame]:
    """Fetch with cache-first strategy."""
    df = cache.get(meta.id)
    if df is not None:
        return df
    try:
        if meta.source == "bnm" and meta.bnm_path:
            # BNM data is fetched separately via fetch_*_history functions
            pass
        else:
            df = dosm.fetch_all(meta.id)
        if df is not None and not df.empty:
            cache.put(meta.id, df)
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", meta.id, exc)
    return df


def _build_date_grid(
    config: ToolboxConfig,
    dataframes: list[pd.DataFrame],
) -> np.ndarray:
    """Build a common year-month grid spanning all input DataFrames."""
    all_dates: list[pd.Timestamp] = []
    for df in dataframes:
        if "date" in df.columns:
            all_dates.extend(df["date"].dropna().tolist())
    if not all_dates:
        raise ValueError("No dates found in data sources")
    min_date = min(all_dates)
    max_date = max(all_dates)
    return generate_dates(
        max(config.startyear, min_date.year),
        max(config.startmonth, min_date.month) if min_date.year == config.startyear else 1,
        max_date.year,
        max_date.month,
    )


def _align_to_grid(
    df: pd.DataFrame,
    date_grid: np.ndarray,
    freq: str,
    col: str = "index",
) -> np.ndarray:
    """Align a DataFrame series to the monthly date grid.

    For quarterly data, the value for the 3rd month is repeated
    (or interpolated) across the quarter.
    """
    T = len(date_grid)
    result = np.full(T, np.nan)

    if "date" not in df.columns:
        return result

    # Build lookup: date -> value
    if col == "index":
        value_col = [c for c in df.columns if c != "date"]
        if not value_col:
            return result
        col = value_col[0]
    if col not in df.columns:
        return result

    # Drop NaN values
    sub = df[["date", col]].dropna()
    lookup = dict(zip(
        sub["date"].dt.to_period("M").astype(str),
        sub[col],
    ))

    for i in range(T):
        y, m = date_grid[i]
        key = f"{y}-{m:02d}"
        if key in lookup:
            result[i] = lookup[key]

    # For quarterly data, forward-fill within quarter
    if freq == "quarterly":
        for i in range(T):
            if not np.isnan(result[i]):
                val = result[i]
                # fill month 1 and 2 of next quarter... actually, the toolbox
                # places quarterly value at the 3rd month and NaN elsewhere.
                # The state-space model handles the aggregation internally.
                pass

    return result


def _find_date_index(
    date_grid: np.ndarray,
    year: int,
    month: int,
) -> int:
    """Find 0-based index of (year, month) in date_grid."""
    mask = (date_grid[:, 0] == year) & (date_grid[:, 1] == month)
    indices = np.where(mask)[0]
    if len(indices) == 0:
        return 0
    return int(indices[0])


def _build_blocks(groups: list[str], groups_name: list[str]) -> np.ndarray:
    """Build a one-hot block assignment matrix."""
    N = len(groups)
    K = len(groups_name)
    blocks = np.zeros((N, K))
    for j, g in enumerate(groups):
        if g in groups_name:
            blocks[j, groups_name.index(g)] = 1.0
    return blocks
