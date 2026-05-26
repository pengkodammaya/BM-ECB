"""Strengthen component nowcasts using existing data with smarter indicators."""

# For investment: use construction IPI + capital goods imports + credit
# For exports: use exports from trade_headline (already deployed) + exchange rate
# For imports: use imports from trade_headline (already have) + retained imports

import sys; sys.path.insert(0,"src")
import numpy as np
import pandas as pd

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams
from rich.console import Console
from rich.table import Table

console = Console()

# Load ALL available monthly indicators (max set)
MONTHLY = {
    # Core indicators
    "ipi": ("ipi", "index", 0, {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, {"division": "overall"}),
    "cpi_core": ("cpi_core", "index", 1, {"division": "overall"}),
    "ppi": ("ppi", "index", 1, {"series": "abs"}),
    "u_rate": ("lfs_month", "u_rate", 0, {}),
    "p_rate": ("lfs_month", "p_rate", 0, {}),
    "leading": ("economic_indicators", "leading", 1, {}),
    "coincident": ("economic_indicators", "coincident", 1, {}),
    # Trade indicators
    "exports": ("trade_headline", "exports", 1, {"series": "abs"}),
    "imports": ("trade_headline", "imports", 1, {"series": "abs"}),
    "trade_balance": ("trade_headline", "balance", 0, {"series": "abs"}),  # level, not growth
    # Services/WRT
    "wrt": ("iowrt", "sales", 1, {"series": "abs"}),
}

cache = DataCache(ttl_hours=24)
client = OpenDOSMClient()

filtered = {}
for name, (did, col, tcode, filters) in MONTHLY.items():
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

# Add BNM interbank rate
from nowcasting_toolbox.data.sources.bnm import fetch_interest_rate_history, fetch_exchange_rate_history
try:
    ir_df = fetch_interest_rate_history(start_year=2015, verbose=False)
    if not ir_df.empty:
        ir_df = ir_df.rename(columns={"value": "interbank"})
        filtered["interbank"] = ir_df[["date", "interbank"]]
except: pass
try:
    fx_df = fetch_exchange_rate_history(start_year=2015, currency_code="USD", verbose=False)
    if not fx_df.empty:
        fx_vals = fx_df["value"].values
        fx_growth = np.full(len(fx_vals), np.nan)
        for i in range(1, len(fx_vals)):
            if fx_vals[i-1] > 0:
                fx_growth[i] = np.log(fx_vals[i]) - np.log(fx_vals[i-1])
        fx_df["fx_usd"] = fx_growth
        fx_df = fx_df.dropna(subset=["fx_usd"])
        filtered["fx_usd"] = fx_df[["date", "fx_usd"]]
except: pass

monthly_names = sorted(filtered.keys())
console.print(f"[cyan]Monthly indicators: {len(monthly_names)}[/cyan]")

# Demand targets with smarter indicator selection per component
# Each target can use a different subset of indicators
COMPONENT_INDICATORS = {
    "Investment (GFCF)": [n for n in monthly_names if n not in ["exports", "cpi_headline", "cpi_core"]],  # investment-relevant
    "Exports":           [n for n in monthly_names if n not in ["wrt", "p_rate"]],  # export-relevant
    "Imports":           [n for n in monthly_names if n not in ["wrt"]],  # import-relevant
    "Consumption":       [n for n in monthly_names],  # all relevant
}

DEMAND_TARGETS = {
    "Investment (GFCF)": ("gdp_qtr_real_demand", "e3", "growth_yoy"),
    "Exports":           ("gdp_qtr_real_demand", "e5", "growth_yoy"),
    "Imports":           ("gdp_qtr_real_demand", "e6", "growth_yoy"),
    "Consumption":       ("gdp_qtr_real_demand", "e1", "growth_yoy"),
    "GDP (demand)":      ("gdp_qtr_real_demand", "e0", "growth_yoy"),
}

results = {}
for label, (dataset_id, type_code, series_type) in DEMAND_TARGETS.items():
    use_indicators = COMPONENT_INDICATORS.get(label, monthly_names)

    # Fetch demand component
    df_demand = cache.get(dataset_id)
    if df_demand is None:
        df_demand = client.fetch(dataset_id, limit=20000)
        if df_demand is not None and not df_demand.empty:
            cache.put(dataset_id, df_demand)
    if df_demand is None or df_demand.empty:
        continue

    demand_col = df_demand[
        (df_demand["type"] == type_code) & (df_demand["series"] == series_type)
    ].copy()
    if len(demand_col) == 0:
        continue

    demand_col = demand_col[["date", "value"]].rename(columns={"value": "target"})
    demand_col["date"] = pd.to_datetime(demand_col["date"])
    demand_col = demand_col.sort_values("date").dropna(subset=["target"])
    demand_col["target"] = demand_col["target"] / 100.0

    # Build grid with selected indicators
    all_dfs = [filtered[n] for n in use_indicators] + [demand_col]
    max_dates = [df["date"].max() for df in all_dfs]
    gdp_start = max(demand_col["date"].min(), pd.Timestamp("2018-01-01"))
    end_dt = max(max_dates)
    datet = generate_dates(gdp_start.year, gdp_start.month, end_dt.year, end_dt.month)
    T = len(datet)
    nM = len(use_indicators)
    X = np.full((T, nM + 1), np.nan)

    for j, name in enumerate(use_indicators):
        df = filtered[name]
        for _, row in df.iterrows():
            y, m = row["date"].year, row["date"].month
            idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
            if len(idx) > 0:
                X[idx[0], j] = row[name]

    for _, row in demand_col.iterrows():
        y, m = row["date"].year, row["date"].month
        q_end_m = ((m - 1) // 3) * 3 + 3
        idx = np.where((datet[:, 0] == y) & (datet[:, 1] == q_end_m))[0]
        if len(idx) > 0:
            X[idx[0], -1] = row["target"]

    # Transform
    X_trans = X.copy()
    for j, name in enumerate(use_indicators):
        tcode = MONTHLY.get(name, (None, None, 0, None, {}))[2]
        X_trans[:, j] = transform_series(X[:, j].copy(), tcode, "monthly")
    X_trans[:, -1] = X[:, -1].copy()

    mu = np.nanmean(X_trans, axis=0)
    sigma = np.nanstd(X_trans, axis=0)
    sigma[sigma < 1e-10] = 1.0
    X_std = (X_trans - mu) / sigma
    ff = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
    X_est = X_std[ff:]

    target_obs = np.sum(~np.isnan(X_est[:, -1]))
    if target_obs < 5:
        continue

    try:
        dfm = DFM(DFMParams(r=3, p=2, max_iter=50, thresh=1e-5, idio=1))
        res = dfm.fit(X_est)
        nw_std = float(res.X_sm[-1, -1])
        nw_pct = nw_std * sigma[-1] + mu[-1]

        act_pct = np.nan
        for i in range(len(X_est)-1, -1, -1):
            if not np.isnan(X_est[i, -1]):
                act_pct = X_est[i, -1] * sigma[-1] + mu[-1]
                break

        results[label] = {"nowcast": nw_pct * 100, "actual": act_pct * 100, "indicators": len(use_indicators)}
    except Exception as e:
        console.print(f"  [red]{label}: {e}[/red]")

client.close()

# Report
console.print()
table = Table(title="GDP Component Nowcasts (DFM, YoY %, Selected Indicators)")
table.add_column("Component", style="bold")
table.add_column("Indicators", justify="right")
table.add_column("Nowcast (YoY %)", justify="right")
table.add_column("Actual (YoY %)", justify="right")
table.add_column("Diff (pp)", justify="right")

for label, vals in results.items():
    diff = vals["nowcast"] - vals["actual"]
    table.add_row(label, str(vals["indicators"]), f"{vals['nowcast']:+.1f}", f"{vals['actual']:+.1f}", f"{diff:+.1f}")

console.print(table)
