"""Backtest: evaluate component-level nowcast accuracy (C, I, G, X, M).
Includes global high-frequency indicators (SOX, CPO, BDRY) via yfinance."""
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
from nowcasting_toolbox.bvar import BVAR
from nowcasting_toolbox.config import DFMParams, BVARParams
import yfinance as yf

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

# Skip global indicators for backtest speed
MONTHLY = {k: v for k, v in MONTHLY.items() if v[3] not in ("global_equity", "global_commodity", "global_demand")}
# ---------------------------------------------------------------------------
GLOBAL_INDICATORS = {
    "sp500": ("^GSPC", "global_equity"),
    "shcomp": ("000001.SS", "global_equity"),
    "sox":    ("^SOX", "global_equity"),
    "brent":  ("BZ=F", "global_commodity"),
    "cpo":    ("CPO=F", "global_commodity"),
    "bdry":   ("BDRY", "global_demand"),
}
for label, (ticker, group) in GLOBAL_INDICATORS.items():
    try:
        raw = yf.download(ticker, start="2015-01-01", progress=False)
        if raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"].iloc[:, 0] if raw["Close"].ndim == 2 else raw["Close"]
        else:
            close = raw["Close"]
        monthly = close.resample("ME").last().dropna()
        growth = np.log(monthly).diff().dropna()
        df = growth.reset_index()
        df.columns = ["date", label]
        df["date"] = pd.to_datetime(df["date"])
        MONTHLY[label] = (label, label, 0, group, {})
        filtered[label] = df
        console.print(f"  [dim]Loaded {label} ({ticker}): {len(df)} monthly obs[/dim]")
    except Exception as e:
        console.print(f"  [yellow]Skipping {label}: {e}[/yellow]")

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

# ---------------------------------------------------------------------------
# 1c. Per-component indicator mapping (matches daily_update.py)
# ---------------------------------------------------------------------------
COMPONENT_INDICATORS = {
    "Consumption (e1)": [n for n in filtered if n != "gdp"],
    "Investment (e3)":  [n for n in filtered if MONTHLY[n][3] in ("industry", "leading", "external", "coincident")],
    "Government (e2)":  [n for n in filtered if n != "gdp"],  # all: no BNM in backtest
    "Exports (e5)":     [n for n in filtered if MONTHLY[n][3] in ("external", "financial", "industry", "global_equity", "global_commodity", "global_demand")],
    "Imports (e6)":     [n for n in filtered if MONTHLY[n][3] in ("external", "services", "prices", "global_commodity")],
}
# Fallback: if a subset is too small (<3 indicators), use all
for ck, indicators in COMPONENT_INDICATORS.items():
    if len(indicators) < 3:
        COMPONENT_INDICATORS[ck] = [n for n in filtered if n != "gdp"]

monthly_names_all = sorted(filtered.keys())
nM_all = len(monthly_names_all)

# Build common grid using GDP SA range
gdp_sa = client.fetch("gdp_qtr_real_sa", limit=20000)
gdp_sa["date"] = pd.to_datetime(gdp_sa["date"])
gd_start = max(gdp_sa["date"].min(), pd.Timestamp("2018-01-01"))

max_dates = [df["date"].max() for df in filtered.values()] + [gdp_sa["date"].max()]
ed_end = max(max_dates)

datet_full = generate_dates(gd_start.year, gd_start.month, ed_end.year, ed_end.month)
T = len(datet_full)
X_monthly = np.full((T, nM_all), np.nan)

for j, name in enumerate(monthly_names_all):
    df = filtered[name]
    for _, row in df.iterrows():
        y, m = row["date"].year, row["date"].month
        idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == m))[0]
        if len(idx) > 0:
            X_monthly[idx[0], j] = row[name]

# Transform monthly indicators
Xm_trans = X_monthly.copy()
for j, name in enumerate(monthly_names_all):
    tcode = MONTHLY[name][2]
    Xm_trans[:, j] = transform_series(X_monthly[:, j].copy(), tcode, "monthly")

client.close()

# ---------------------------------------------------------------------------
# 2. Vintage builder
# ---------------------------------------------------------------------------
arc_schedule = build_publication_schedule(years=[2023, 2024, 2025, 2026], cache_dir=Path("data/malaysia"))
vb = ARCVintageBuilder(schedule=arc_schedule)

vintage_dates = generate_vintage_dates(2023, 5, 2025, 8, frequency="quarterly", day_of_month=15)

# ---------------------------------------------------------------------------
# 3. Build vintages once (all indicators), then loop components
# ---------------------------------------------------------------------------
console.print("[cyan]Component Backtest[/cyan]")
all_results = {label: {"dfm_preds": [], "bvar_preds": [], "acts": []} for label in COMPONENTS}

# Pre-build full vintage matrices for each vintage date
vintage_matrices = {}
for vdate in vintage_dates:
    Xm_full_vint = vb.build(Xm_trans.copy(), datet_full, vdate, var_names=monthly_names_all, dataset_ids=None)
    vintage_matrices[vdate] = Xm_full_vint

for label, (tcode, series_type) in COMPONENTS.items():
    console.print(f"\n  [bold]{label}[/bold]")

    # Filter to component-specific indicators
    comp_vars = sorted(COMPONENT_INDICATORS.get(label, monthly_names_all))
    comp_indices = [i for i, n in enumerate(monthly_names_all) if n in comp_vars]

    for vdate in vintage_dates:
        vmonth = vdate.month
        vyear = vdate.year
        q_end_m = ((vmonth - 1) // 3) * 3 + 3
        console.print(f"    [dim]{vyear}-Q{(vmonth-1)//3+1}[/dim]", end="")

        Xm_vint = vintage_matrices[vdate][:, comp_indices] if comp_indices else vintage_matrices[vdate]

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
            dfm = DFM(DFMParams(r=2, p=1, max_iter=10, thresh=1e-3, idio=1))
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
                    all_results[label]["dfm_preds"].append(nw_pct * 100)
                    all_results[label]["acts"].append(act_pct * 100)
        except Exception:
            pass

        # BVAR for component
        try:
            Xc_filled = X_vint_std.copy()
            for j in range(Xc_filled.shape[1]):
                col = Xc_filled[:, j]
                # Forward-fill only (no interpolation with future values)
                last_valid = np.nan
                for t in range(len(col)):
                    if not np.isnan(col[t]):
                        last_valid = col[t]
                    elif not np.isnan(last_valid):
                        Xc_filled[t, j] = last_valid
            bvar = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-3, bvar_max_iter=3))
            res_b = bvar.fit(Xc_filled, datet_vint)
            if q_end_idx >= 0 and res_b.X_sm.shape[0] > 0:
                nw_bvar = float(res_b.X_sm[q_end_idx, -1]) * vsigma[-1] + vmu[-1]
                if not np.isnan(act_pct):
                    all_results[label]["bvar_preds"].append(nw_bvar * 100)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# 4. Report
# ---------------------------------------------------------------------------
console.print()
table = Table(title="Component Nowcast Accuracy (BVAR primary + DFM, Backtest)")
table.add_column("Component", style="bold")
table.add_column("DFM MAE", justify="right")
table.add_column("BVAR MAE", justify="right")
table.add_column("DFM FDA", justify="right")
table.add_column("BVAR FDA", justify="right")
table.add_column("N", justify="right")

for label in COMPONENTS:
    d = all_results[label]
    aa = np.array(d["acts"])
    if len(aa) < 3:
        continue

    dfm_pa = np.array(d["dfm_preds"])
    bvar_pa = np.array(d["bvar_preds"])

    dfm_mae = compute_mae(aa[:len(dfm_pa)], dfm_pa) if len(dfm_pa) >= 3 else float("nan")
    bvar_mae = compute_mae(aa[:len(bvar_pa)], bvar_pa) if len(bvar_pa) >= 3 else float("nan")
    dfm_fda = compute_fda(aa[:len(dfm_pa)], dfm_pa) if len(dfm_pa) >= 3 else 0
    bvar_fda = compute_fda(aa[:len(bvar_pa)], bvar_pa) if len(bvar_pa) >= 3 else 0

    style = ""
    if not np.isnan(bvar_mae) and bvar_mae < dfm_mae:
        style = "green"  # BVAR wins
    elif not np.isnan(dfm_mae) and dfm_mae < 3.0:
        style = "cyan"

    table.add_row(label, f"{dfm_mae:.2f}", f"{bvar_mae:.2f}",
                  f"{dfm_fda:.0%}", f"{bvar_fda:.0%}",
                  str(len(aa)), style=style)

console.print(table)

# Save
rows = []
for l in COMPONENTS:
    aa = np.array(all_results[l]["acts"])
    dfm_pa = np.array(all_results[l]["dfm_preds"])
    bvar_pa = np.array(all_results[l]["bvar_preds"])
    if len(dfm_pa) >= 3:
        rows.append({"component": l, "model": "DFM",
                      "MAE": compute_mae(aa[:len(dfm_pa)], dfm_pa),
                      "RMSE": compute_rmse(aa[:len(dfm_pa)], dfm_pa),
                      "FDA": compute_fda(aa[:len(dfm_pa)], dfm_pa),
                      "N": len(dfm_pa)})
    if len(bvar_pa) >= 3:
        rows.append({"component": l, "model": "BVAR",
                      "MAE": compute_mae(aa[:len(bvar_pa)], bvar_pa),
                      "RMSE": compute_rmse(aa[:len(bvar_pa)], bvar_pa),
                      "FDA": compute_fda(aa[:len(bvar_pa)], bvar_pa),
                      "N": len(bvar_pa)})
lb = pd.DataFrame(rows)
lb.to_csv(Path("output/malaysia/component_leaderboard.csv"), index=False)
console.print("\n[dim]Saved to output/malaysia/component_leaderboard.csv[/dim]")
