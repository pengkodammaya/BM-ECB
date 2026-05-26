"""Backtest: evaluate component-level nowcast accuracy (C, I, G, X, M)."""
import sys; sys.path.insert(0,"src")
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date
from rich.console import Console
from rich.table import Table

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.eval.vintage import ARCVintageBuilder, generate_vintage_dates
from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule
from nowcasting_toolbox.eval.metrics import compute_mae, compute_fda, compute_rmse
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams

console = Console()

# ---------------------------------------------------------------------------
# 1. Load monthly indicators (once)
# ---------------------------------------------------------------------------
MONTHLY = {
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
}

cache = DataCache(ttl_hours=24)
client = OpenDOSMClient()
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

for var in ["ipi", "imports_capital", "imports_consumer"]:
    if var in filtered:
        filtered[var][var] = filtered[var][var] / 100.0

# Also fetch demand-side data (once, all components)
df_demand = client.fetch("gdp_qtr_real_demand", limit=20000)
demand_abs = {}
for _, row in df_demand.iterrows():
    if row["series"] == "abs":
        key = row["type"]
        demand_abs[key] = {"date": row["date"], "value": row["value"]}

COMPONENTS = {
    "Consumption (e1)": ("e1", "growth_yoy"),
    "Investment (e3)":  ("e3", "growth_yoy"),
    "Government (e2)":  ("e2", "growth_yoy"),
    "Exports (e5)":     ("e5", "growth_yoy"),
    "Imports (e6)":     ("e6", "growth_yoy"),
}

# Extract component actuals at each quarter
comp_actuals = {}
for label, (tcode, series_type) in COMPONENTS.items():
    sub = df_demand[(df_demand["type"] == tcode) & (df_demand["series"] == series_type)].copy()
    sub["date"] = pd.to_datetime(sub["date"])
    sub = sub.sort_values("date")
    sub["value"] = sub["value"] / 100.0  # % -> decimal
    comp_actuals[label] = dict(zip(
        [f"{d.year}-Q{(d.month-1)//3+1}" for d in sub["date"]],
        sub["value"]
    ))

monthly_names = sorted(filtered.keys())
nM = len(monthly_names)

# Build common grid using GDP SA range
gdp_sa = client.fetch("gdp_qtr_real_sa", limit=20000)
gdp_sa["date"] = pd.to_datetime(gdp_sa["date"])
gd_start = max(gdp_sa["date"].min(), pd.Timestamp("2018-01-01"))

max_dates = [df["date"].max() for df in filtered.values()] + [gdp_sa["date"].max()]
ed_end = max(max_dates)

datet_full = generate_dates(gd_start.year, gd_start.month, ed_end.year, ed_end.month)
T = len(datet_full)
X_monthly = np.full((T, nM), np.nan)

for j, name in enumerate(monthly_names):
    df = filtered[name]
    for _, row in df.iterrows():
        y, m = row["date"].year, row["date"].month
        idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == m))[0]
        if len(idx) > 0:
            X_monthly[idx[0], j] = row[name]

# Transform monthly indicators
Xm_trans = X_monthly.copy()
for j, name in enumerate(monthly_names):
    tcode = MONTHLY[name][2]
    Xm_trans[:, j] = transform_series(X_monthly[:, j].copy(), tcode, "monthly")

client.close()

# ---------------------------------------------------------------------------
# 2. Vintage builder
# ---------------------------------------------------------------------------
arc_schedule = build_publication_schedule(years=[2023, 2024, 2025, 2026], cache_dir=Path("data/malaysia"))
vb = ARCVintageBuilder(schedule=arc_schedule)
DID_MAP = ["ipi", "cpi_headline", "cpi_core", "ppi", "u_rate", "u_rate", "u_rate_youth",
           "leading", "coincident", "exports", "imports_capital", "imports_consumer", "wrt"]

vintage_dates = generate_vintage_dates(2020, 2, 2025, 11, frequency="quarterly", day_of_month=15)

# ---------------------------------------------------------------------------
# 3. For each component, run DFM at each vintage
# ---------------------------------------------------------------------------
console.print("[cyan]Component Backtest[/cyan]")
all_results = {label: {"preds": [], "acts": []} for label in COMPONENTS}

for label, (tcode, series_type) in COMPONENTS.items():
    console.print(f"\n  [bold]{label}[/bold]")

    for vdate in vintage_dates:
        vmonth = vdate.month
        vyear = vdate.year
        q_end_m = ((vmonth - 1) // 3) * 3 + 3

        # Build monthly indicator vintage
        Xm_vint = vb.build(Xm_trans.copy(), datet_full, vdate, var_names=monthly_names, dataset_ids=DID_MAP[:nM] if len(DID_MAP) >= nM else None)

        # Build component target column at quarter-end rows
        comp_target = np.full((T, 1), np.nan)
        for qlabel, val in comp_actuals[label].items():
            parts = qlabel.split("-Q")
            y, q = int(parts[0]), int(parts[1])
            qem_target = q * 3
            idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == qem_target))[0]
            if len(idx) > 0:
                comp_target[idx[0], 0] = val

        # Combine monthly + target
        X_all = np.column_stack([Xm_vint, comp_target])

        # Trim leading NaN
        valid_rows = ~np.all(np.isnan(X_all), axis=1)
        if np.sum(valid_rows) < 24:
            continue
        first = np.where(valid_rows)[0][0]
        X_vint_t = X_all[first:]
        datet_vint = datet_full[first:]

        if np.all(np.isnan(X_vint_t[:, -1])):
            continue

        # Standardize per-vintage
        vmu = np.nanmean(X_vint_t, axis=0)
        vsigma = np.nanstd(X_vint_t, axis=0)
        vsigma[vsigma < 1e-10] = 1.0
        X_vint_std = (X_vint_t - vmu) / vsigma

        try:
            dfm = DFM(DFMParams(r=3, p=2, max_iter=30, thresh=1e-5, idio=1))
            res = dfm.fit(X_vint_std)

            # Find target quarter-end row
            q_end_idx = -1
            for t in range(len(datet_vint)):
                if datet_vint[t, 0] == vyear and datet_vint[t, 1] == q_end_m:
                    q_end_idx = t; break

            if q_end_idx >= 0 and q_end_idx < res.X_sm.shape[0]:
                nw_std = float(res.X_sm[q_end_idx, -1])
                nw_pct = nw_std * vsigma[-1] + vmu[-1]

                # Actual for this vintage
                act_pct = np.nan
                for t in range(len(datet_full)):
                    if datet_full[t, 0] == vyear and datet_full[t, 1] == q_end_m:
                        if not np.isnan(comp_target[t, 0]):
                            act_pct = comp_target[t, 0]
                        break

                if not np.isnan(act_pct):
                    all_results[label]["preds"].append(nw_pct * 100)
                    all_results[label]["acts"].append(act_pct * 100)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# 4. Report
# ---------------------------------------------------------------------------
console.print()
table = Table(title="Component Nowcast Accuracy (DFM, 24 Vintage Backtest)")
table.add_column("Component", style="bold")
table.add_column("MAE (pp)", justify="right")
table.add_column("RMSE (pp)", justify="right")
table.add_column("FDA (%)", justify="right")
table.add_column("N", justify="right")

for label in COMPONENTS:
    d = all_results[label]
    if len(d["preds"]) < 3:
        continue
    pa = np.array(d["preds"])
    aa = np.array(d["acts"])
    mae = compute_mae(aa, pa)
    rmse = compute_rmse(aa, pa)
    fda = compute_fda(aa, pa)

    style = ""
    if mae < 3.0:
        style = "green"
    elif mae < 6.0:
        style = "yellow"
    else:
        style = "red"

    table.add_row(label, f"{mae:.2f}", f"{rmse:.2f}", f"{fda:.0%}", str(len(pa)), style=style)

console.print(table)

# Save
lb = pd.DataFrame([
    {"component": l, "MAE": compute_mae(np.array(all_results[l]["acts"]), np.array(all_results[l]["preds"])),
     "RMSE": compute_rmse(np.array(all_results[l]["acts"]), np.array(all_results[l]["preds"])),
     "FDA": compute_fda(np.array(all_results[l]["acts"]), np.array(all_results[l]["preds"])),
     "N": len(all_results[l]["preds"])}
    for l in COMPONENTS if len(all_results[l]["preds"]) >= 3
])
lb.to_csv(Path("output/malaysia/component_leaderboard.csv"), index=False)
console.print("\n[dim]Saved to output/malaysia/component_leaderboard.csv[/dim]")
