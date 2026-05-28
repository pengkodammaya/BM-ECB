"""Nowcast investment, exports, and imports using GDP demand-side components."""
import sys; sys.path.insert(0,"src")
import numpy as np
import pandas as pd
from pathlib import Path

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams
from rich.console import Console
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# 1. Load monthly indicators (same as main pipeline)
# ---------------------------------------------------------------------------
MONTHLY = {
    "ipi": ("ipi", "index", 0, "industry", {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, "prices", {"division": "overall"}),
    "cpi_core": ("cpi_core", "index", 1, "prices", {"division": "overall"}),
    "ppi": ("ppi", "index", 1, "prices", {"series": "abs"}),
    "u_rate": ("lfs_month", "u_rate", 0, "labour", {}),
    "p_rate": ("lfs_month", "p_rate", 0, "labour", {}),
    "leading": ("economic_indicators", "leading", 1, "leading", {}),
    "coincident": ("economic_indicators", "coincident", 1, "coincident", {}),
    "exports_m": ("trade_headline", "exports", 1, "external", {"series": "abs"}),
    "wrt": ("iowrt", "sales", 1, "services", {"series": "abs"}),
}

# GDP components to nowcast — use YoY (no seasonality, matches DOSM reporting)
DEMAND_TARGETS = {
    "Investment (GFCF)": ("gdp_qtr_real_demand", "e3", "growth_yoy"),
    "Exports":           ("gdp_qtr_real_demand", "e5", "growth_yoy"),
    "Imports":           ("gdp_qtr_real_demand", "e6", "growth_yoy"),
    "Consumption":       ("gdp_qtr_real_demand", "e1", "growth_yoy"),
    "GDP (demand side)": ("gdp_qtr_real_demand", "e0", "growth_yoy"),
}

cache = DataCache(ttl_hours=24)
client = OpenDOSMClient()

# Fetch monthly indicators
console.print("[cyan]Loading monthly indicators...[/cyan]")
filtered = {}
for name, (did, col, tcode, group, filters) in MONTHLY.items():
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

if "ipi" in filtered:
    filtered["ipi"]["ipi"] = filtered["ipi"]["ipi"] / 100.0

# Also add BNM interbank rate if available
from nowcasting_toolbox.data.sources.bnm import fetch_interest_rate_history
try:
    ir_df = fetch_interest_rate_history(start_year=2015, verbose=False)
    if not ir_df.empty:
        ir_df = ir_df.rename(columns={"value": "interbank"})
        filtered["interbank"] = ir_df[["date", "interbank"]]
except Exception:
    pass

monthly_names = list(filtered.keys())
console.print(f"  [dim]Monthly indicators: {len(monthly_names)}[/dim]")

# ---------------------------------------------------------------------------
# 2. Nowcast each demand component
# ---------------------------------------------------------------------------
results = {}

for label, (dataset_id, type_code, series_type) in DEMAND_TARGETS.items():
    console.print(f"\n[bold]{label} ({type_code})[/bold]")

    # Fetch demand component data
    df_demand = cache.get(dataset_id)
    if df_demand is None:
        df_demand = client.fetch(dataset_id, limit=20000)
        if df_demand is not None and not df_demand.empty:
            cache.put(dataset_id, df_demand)
    if df_demand is None or df_demand.empty:
        console.print(f"  [yellow]No data[/yellow]")
        continue

    # Filter to the specific expenditure type and QoQ growth series
    demand_col = df_demand[
        (df_demand["type"] == type_code) &
        (df_demand["series"] == series_type)
    ].copy()
    if len(demand_col) == 0:
        console.print(f"  [yellow]No {series_type} data for {type_code}[/yellow]")
        continue

    demand_col = demand_col[["date", "value"]].rename(columns={"value": "target"})
    demand_col["date"] = pd.to_datetime(demand_col["date"])
    demand_col = demand_col.sort_values("date").dropna(subset=["target"])
    # QoQ growth rates from API are in % — convert to decimal
    demand_col["target"] = demand_col["target"] / 100.0

    # Build common grid
    all_dfs = list(filtered.values()) + [demand_col]
    min_dates = [df["date"].min() for df in all_dfs]
    max_dates = [df["date"].max() for df in all_dfs]
    gdp_start = max(demand_col["date"].min(), pd.Timestamp("2018-01-01"))
    start_dt = gdp_start
    end_dt = max(max_dates)
    datet = generate_dates(start_dt.year, start_dt.month, end_dt.year, end_dt.month)
    T = len(datet)
    nM = len(monthly_names)
    X = np.full((T, nM + 1), np.nan)

    # Fill monthly indicators
    for j, name in enumerate(monthly_names):
        df = filtered[name]
        for _, row in df.iterrows():
            y, m = row["date"].year, row["date"].month
            idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
            if len(idx) > 0:
                X[idx[0], j] = row[name]

    # Fill demand component target (quarterly, QoQ growth)
    for _, row in demand_col.iterrows():
        y, m = row["date"].year, row["date"].month
        q_end_m = ((m - 1) // 3) * 3 + 3
        idx = np.where((datet[:, 0] == y) & (datet[:, 1] == q_end_m))[0]
        if len(idx) > 0:
            X[idx[0], -1] = row["target"]

    # Transform and standardize
    X_trans = X.copy()
    for j, name in enumerate(monthly_names):
        tcode = MONTHLY.get(name, (None, None, 0, None, {}))[2]
        X_trans[:, j] = transform_series(X[:, j].copy(), tcode, "monthly")
    X_trans[:, -1] = X[:, -1].copy()  # target already QoQ, no further transform

    mu = np.nanmean(X_trans, axis=0)
    sigma = np.nanstd(X_trans, axis=0)
    sigma[sigma < 1e-10] = 1.0
    X_std = (X_trans - mu) / sigma

    ff = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
    X_est = X_std[ff:]

    target_obs = np.sum(~np.isnan(X_est[:, -1]))
    console.print(f"  [dim]Estimation: {X_est.shape[0]} months, {target_obs} target obs[/dim]")

    if target_obs < 5:
        console.print(f"  [yellow]Too few observations, skipping[/yellow]")
        continue

    # Run DFM
    try:
        dfm = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
        res = dfm.fit(X_est)
        nowcast_std = float(res.X_sm[-1, -1])
        nowcast_pct = nowcast_std * sigma[-1] + mu[-1]

        # Also get latest actual
        actual_pct = np.nan
        for i in range(len(X_est)-1, -1, -1):
            if not np.isnan(X_est[i, -1]):
                actual_pct = X_est[i, -1] * sigma[-1] + mu[-1]
                break

        results[label] = {
            "nowcast_pct": nowcast_pct * 100,
            "actual_pct": actual_pct * 100,
        }
        console.print(f"  [green]Nowcast: {nowcast_pct*100:+.1f}% YoY  |  Latest actual: {actual_pct*100:+.1f}% YoY[/green]")
    except Exception as e:
        console.print(f"  [red]DFM failed: {e}[/red]")

client.close()

# ---------------------------------------------------------------------------
# 3. Report
# ---------------------------------------------------------------------------
if results:
    console.print()
    table = Table(title="GDP Component Nowcasts (DFM, Latest Quarter)")
    table.add_column("Component", style="bold")
    table.add_column("Nowcast (YoY %)", justify="right")
    table.add_column("Latest Actual (YoY %)", justify="right")
    table.add_column("Diff (pp)", justify="right")

    for label, vals in results.items():
        nw = vals["nowcast_pct"]
        act = vals["actual_pct"]
        diff = nw - act if not np.isnan(nw) and not np.isnan(act) else np.nan
        diff_str = f"{diff:+.2f}" if not np.isnan(diff) else "—"
        table.add_row(label, f"{nw:+.2f}", f"{act:+.2f}", diff_str)

    console.print(table)
