"""Full 3-model backtest with ensemble and leaderboard."""
import sys
sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from datetime import date
from pathlib import Path
from rich.console import Console
from rich.table import Table

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.bnm import fetch_interest_rate_history, fetch_exchange_rate_history
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.eval.vintage import (
    ARCVintageBuilder, generate_vintage_dates,
)
from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule
from nowcasting_toolbox.eval.metrics import compute_mae, compute_fda, compute_rmse
from nowcasting_toolbox.utils.covid import correct_covid
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.bvar import BVAR
from nowcasting_toolbox.beq import BEQ
from nowcasting_toolbox.config import DFMParams, BVARParams, BEQParams

console = Console()

# ---------------------------------------------------------------------------
# 1. Data pipeline
# ---------------------------------------------------------------------------
DATASETS = {
    "ipi": ("ipi", "index", 0, "industry", {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, "prices", {"division": "overall"}),
    "cpi_core": ("cpi_core", "index", 1, "prices", {"division": "overall"}),
    "ppi": ("ppi", "index", 1, "prices", {"series": "abs"}),
    "u_rate": ("lfs_month", "u_rate", 0, "labour", {}),
    "p_rate": ("lfs_month", "p_rate", 0, "labour", {}),
    "u_rate_youth": ("lfs_month_youth", "u_rate_15_30", 0, "labour", {}),  # youth unemployment
    "leading": ("economic_indicators", "leading", 1, "leading", {}),
    "coincident": ("economic_indicators", "coincident", 1, "coincident", {}),
    "exports": ("trade_headline", "exports", 1, "external", {"series": "abs"}),
    "imports_capital": ("trade_enduse_bec", "imports", 0, "external", {"bec": "000", "end_use": "capital", "series": "growth_mom"}),  # capital goods imports -> investment signal
    "imports_consumer": ("trade_enduse_bec", "imports", 0, "external", {"bec": "000", "end_use": "consumption", "series": "growth_mom"}),  # consumer goods imports -> consumption signal
    "wrt": ("iowrt", "sales", 1, "services", {"series": "abs"}),
    "gdp": ("gdp_qtr_real_sa", "value", 0, "target", {"series": "abs"}),
}
MONTHLY_NAMES = [n for n in DATASETS if n != "gdp"]
ALL_NAMES = MONTHLY_NAMES + ["gdp"]

cache = DataCache(ttl_hours=24)
client = OpenDOSMClient()
filtered = {}

console.print("[cyan]Fetching data...[/cyan]")
for name, (did, col, tcode, group, filters) in DATASETS.items():
    df = cache.get(did)
    if df is None:
        df = client.fetch(did, limit=20000)
        if df is not None and not df.empty:
            cache.put(did, df)
    if df is None or df.empty:
        continue
    df = df.copy()
    for fcol, fval in filters.items():
        if fcol in df.columns:
            df = df[df[fcol] == fval]
    if col not in df.columns:
        continue
    df = df[["date", col]].dropna().rename(columns={col: name})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date")
    filtered[name] = df

if "ipi" in filtered:
    filtered["ipi"]["ipi"] = filtered["ipi"]["ipi"] / 100.0

# Convert pre-computed growth rates from % to decimal
for var in ["ipi", "exports", "wrt", "imports_capital", "imports_consumer"]:
    if var in filtered:
        filtered[var][var] = filtered[var][var] / 100.0

# ---------------------------------------------------------------------------
# 1b. BNM Financial Data (daily -> monthly, full history)
# ---------------------------------------------------------------------------
console.print("[cyan]Fetching BNM financial data (month-by-month history)...[/cyan]")

# Interbank overnight rate (2015-present)
try:
    ir_df = fetch_interest_rate_history(start_year=2015, verbose=False)
    if not ir_df.empty:
        ir_df = ir_df.rename(columns={"value": "interbank"})
        filtered["interbank"] = ir_df[["date", "interbank"]]
        console.print(f"  [dim]Interbank overnight: {len(filtered['interbank'])} monthly obs[/dim]")
except Exception as e:
    console.print(f"  [yellow]Interbank rate failed: {e}[/yellow]")

# USD/MYR exchange rate (2015-present)
try:
    fx_df = fetch_exchange_rate_history(start_year=2015, currency_code="USD", verbose=False)
    if not fx_df.empty:
        # Compute MoM growth (dlog)
        fx_vals = fx_df["value"].values
        fx_growth = np.full(len(fx_vals), np.nan)
        for i in range(1, len(fx_vals)):
            if fx_vals[i-1] > 0:
                fx_growth[i] = np.log(fx_vals[i]) - np.log(fx_vals[i-1])
        fx_df["fx_usd"] = fx_growth
        fx_df = fx_df.dropna(subset=["fx_usd"])
        filtered["fx_usd"] = fx_df[["date", "fx_usd"]]
        console.print(f"  [dim]MYR/USD: {len(filtered['fx_usd'])} monthly obs[/dim]")
except Exception as e:
    console.print(f"  [yellow]MYR/USD failed: {e}[/yellow]")

# Update DATASETS with BNM variables
BNM_VARS = []
if "interbank" in filtered:
    BNM_VARS.append("interbank")
if "fx_usd" in filtered:
    BNM_VARS.append("fx_usd")

DATASETS_EXTRA = {
    "interbank": ("bnm_interest_rate", "interbank", 0, "financial", {}),
    "fx_usd": ("bnm_exchange_rate", "fx_usd", 0, "financial", {}),  # already MoM growth
}
for k in BNM_VARS:
    DATASETS[k] = DATASETS_EXTRA.get(k)

MONTHLY_NAMES = [n for n in DATASETS if n != "gdp"]
ALL_NAMES = MONTHLY_NAMES + ["gdp"]
ALL_GROUPS = [DATASETS[n][3] for n in ALL_NAMES]  # for block factors

# Update ARC dataset IDs
DATASET_IDS_FOR_ARC = [
    "ipi", "cpi_headline", "cpi_core", "ppi",
    "u_rate", "u_rate",
    "leading", "coincident",
    "exports", "wrt",
] + BNM_VARS + ["gdp"]

gdp_df = filtered["gdp"].copy().sort_values("date")
gdp_vals = gdp_df["gdp"].values
gdp_qoq_arr = np.full(len(gdp_vals), np.nan)
for i in range(1, len(gdp_vals)):
    if gdp_vals[i - 1] > 0:
        gdp_qoq_arr[i] = (gdp_vals[i] - gdp_vals[i - 1]) / gdp_vals[i - 1]
gdp_df["gdp"] = gdp_qoq_arr
gdp_df = gdp_df.dropna(subset=["gdp"])
filtered["gdp"] = gdp_df

min_dates = [df["date"].min() for df in filtered.values()]
max_dates = [df["date"].max() for df in filtered.values()]
# Use GDP data start, but not earlier than 2018 (too sparse before)
gdp_start = max(filtered["gdp"]["date"].min(), pd.Timestamp("2018-01-01"))
start_dt = gdp_start
end_dt = max(max_dates)
datet_full = generate_dates(start_dt.year, start_dt.month, end_dt.year, end_dt.month)
T = len(datet_full)
nM = len(MONTHLY_NAMES)
nQ = 1
X_full = np.full((T, nM + nQ), np.nan)

for j, name in enumerate(MONTHLY_NAMES):
    df = filtered[name]
    for _, row in df.iterrows():
        y, m = row["date"].year, row["date"].month
        idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == m))[0]
        if len(idx) > 0:
            X_full[idx[0], j] = row[name]

gdp_df_q = filtered["gdp"]
for _, row in gdp_df_q.iterrows():
    y, m = row["date"].year, row["date"].month
    q_end_m = ((m - 1) // 3) * 3 + 3
    idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == q_end_m))[0]
    if len(idx) > 0:
        X_full[idx[0], -1] = row["gdp"]

X_trans = X_full.copy()
for j, name in enumerate(ALL_NAMES):
    tcode = DATASETS[name][2]
    freq = "quarterly" if name == "gdp" else "monthly"
    X_trans[:, j] = transform_series(X_full[:, j].copy(), tcode, freq)

mu = np.nanmean(X_trans, axis=0)
sigma = np.nanstd(X_trans, axis=0)
sigma[sigma < 1e-10] = 1.0
X_raw = X_trans.copy()

first_full = np.where(~np.all(np.isnan(X_raw), axis=1))[0][0]
X_raw = X_raw[first_full:]
datet = datet_full[first_full:]

client.close()

console.print(f"[dim]Data: {len(datet)} months, {nM} monthly + {nQ} quarterly, {np.sum(~np.isnan(X_raw[:,-1]))} GDP obs[/dim]")

# ---------------------------------------------------------------------------
# 2. Build live ARC schedule and vintage builder
# ---------------------------------------------------------------------------
console.print("[cyan]Loading ARC release calendar...[/cyan]")
arc_schedule = build_publication_schedule(
    years=[2023, 2024, 2025, 2026],  # ARC available for these years
    cache_dir=Path("data/malaysia"),
)
vb = ARCVintageBuilder(schedule=arc_schedule)
coverage = vb.describe_coverage()
console.print(f"[dim]ARC: {coverage['num_datasets']} datasets, {coverage['total_releases']} releases[/dim]")
console.print(f"[dim]2020-2022 vintages use fallback approximate lags[/dim]")

gdp_idx = -1
results = []

# Generate vintage dates for backtest
vintage_dates = generate_vintage_dates(2020, 2, 2025, 11, frequency="quarterly", day_of_month=15)

console.print("[cyan]Running backtest with live ARC vintages...[/cyan]")

# COVID correction: set to 0 for none, 2 to NaN-block Feb-Sep 2020
DO_COVID = 2  # 0=none, 2=remove COVID from estimation

for i, vdate in enumerate(vintage_dates):
    vmonth = vdate.month
    vyear = vdate.year
    q_end_m = ((vmonth - 1) // 3) * 3 + 3
    q_label = f"{vyear}-Q{(vmonth-1)//3 + 1}"

    X_vint = vb.build(X_raw.copy(), datet, vdate, var_names=ALL_NAMES, dataset_ids=DATASET_IDS_FOR_ARC)

    # Apply COVID correction to the vintage data
    if DO_COVID > 0:
        X_vint = correct_covid(X_vint, datet, mode=DO_COVID)
    vint_mu = np.nanmean(X_vint, axis=0)
    vint_sigma = np.nanstd(X_vint, axis=0)
    vint_sigma[vint_sigma < 1e-10] = 1.0
    X_vint_std = (X_vint - vint_mu) / vint_sigma
    X_vint_raw = X_vint.copy()  # keep pre-standardized for BEQ

    valid_rows = ~np.all(np.isnan(X_vint_std), axis=1)
    if np.sum(valid_rows) < 24:
        continue
    first = np.where(valid_rows)[0][0]
    X_vint_std = X_vint_std[first:]
    X_vint_raw = X_vint[first:]  # also trim raw
    datet_vint = datet[first:]

    if np.all(np.isnan(X_vint_std[:, gdp_idx])):
        continue

    row = {"quarter": q_label, "vintage_date": vdate.isoformat()}

    # Actual GDP
    actual_pct = np.nan
    for t in range(len(datet)):
        if datet[t, 0] == vyear and datet[t, 1] == q_end_m:
            if not np.isnan(X_raw[t, gdp_idx]):
                actual_pct = X_raw[t, gdp_idx] * 100
            break
    row["actual_gdp_pct"] = round(actual_pct, 2) if not np.isnan(actual_pct) else np.nan

    # --- NAIVE (last known quarter GDP = forecast) ---
    naive_pct = np.nan
    for t in range(len(datet)-1, -1, -1):
        m = int(datet[t, 1])
        if m % 3 != 0:
            continue
        target_pos = datet[t, 0] * 100 + m
        current_pos = vyear * 100 + q_end_m
        if target_pos < current_pos and not np.isnan(X_raw[t, gdp_idx]):
            naive_pct = X_raw[t, gdp_idx] * 100
            break
    row["naive_pct"] = round(naive_pct, 2) if not np.isnan(naive_pct) else np.nan

    # --- DFM ---
    try:
        dfm = DFM(DFMParams(r=3, p=2, max_iter=30, thresh=1e-5, idio=1, block_factors=0))
        res = dfm.fit(X_vint_std)
        q_end_idx = -1
        for t in range(len(datet_vint)):
            if datet_vint[t, 0] == vyear and datet_vint[t, 1] == q_end_m:
                q_end_idx = t; break
        if q_end_idx >= 0:
            nw = float(res.X_sm[q_end_idx, gdp_idx]) * vint_sigma[gdp_idx] + vint_mu[gdp_idx]
            row["dfm_pct"] = round(nw * 100, 2)
    except Exception as e:
        row["dfm_pct"] = np.nan

    # --- BVAR (reduced iterations for speed) ---
    try:
        X_filled = X_vint_std.copy()
        for j in range(X_filled.shape[1]):
            col = X_filled[:, j]; nm = np.isnan(col); vl = ~nm
            if np.any(nm) and np.sum(vl) >= 2:
                idx_arr = np.arange(len(col))
                X_filled[nm, j] = np.interp(idx_arr[nm], idx_arr[vl], col[vl])
        bvar = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-5, bvar_max_iter=10))
        res_b = bvar.fit(X_filled, datet_vint)
        nw = float(res_b.X_sm[-1, gdp_idx]) * vint_sigma[gdp_idx] + vint_mu[gdp_idx]
        row["bvar_pct"] = round(nw * 100, 2)
    except Exception:
        row["bvar_pct"] = np.nan

    # --- BEQ (uses raw transformed data, not standardized) ---
    try:
        beq = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
        # BEQ expects non-standardized data (matches MATLAB toolbox)
        res_e = beq.fit(X_vint_raw, datet_vint, ALL_NAMES)
        if res_e.X_sm is not None and res_e.X_sm.shape[0] > 0:
            q_end_idx = -1
            for t in range(len(datet_vint)):
                if datet_vint[t, 0] == vyear and datet_vint[t, 1] == q_end_m:
                    q_end_idx = t; break
            if q_end_idx >= 0 and q_end_idx < res_e.X_sm.shape[0]:
                # BEQ X_sm has GDP in original scale (already un-standardized)
                nw = float(res_e.X_sm[q_end_idx, gdp_idx])
                row["beq_pct"] = round(nw * 100, 2) if not np.isnan(nw) else np.nan
    except Exception:
        row["beq_pct"] = np.nan

    results.append(row)

    if (i + 1) % 3 == 0:
        models_done = sum(1 for c in ["dfm_pct","bvar_pct","beq_pct"] if c in row and not np.isnan(row[c]))
        console.print(f"  [dim]{q_label}: DFM={row.get('dfm_pct','?'):.1f}% BVAR={row.get('bvar_pct','?'):.1f}% BEQ={row.get('beq_pct','?'):.1f}% NAIVE={row.get('naive_pct','?'):.1f}%  actual={actual_pct:+.1f}%[/dim]")

console.print(f"  [dim]Total: {len(results)} vintages[/dim]")

# ---------------------------------------------------------------------------
# 3. Ensemble
# ---------------------------------------------------------------------------
df = pd.DataFrame(results)
for col in ["dfm_pct", "bvar_pct", "beq_pct", "naive_pct"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

model_cols = [c for c in ["dfm_pct", "bvar_pct", "beq_pct"] if c in df.columns]
if len(model_cols) >= 2:
    df["ensemble_pct"] = df[model_cols].median(axis=1)
elif len(model_cols) == 1:
    df["ensemble_pct"] = df[model_cols[0]]

# ---------------------------------------------------------------------------
# 4. Load DOSM Advance Estimates + Actual YoY for proper benchmark
# ---------------------------------------------------------------------------
advance_path = Path("data/malaysia/dosm_advance_estimates.csv")
advance_df = None
dosm_benchmark_rows = []

if advance_path.exists():
    advance_df = pd.read_csv(advance_path)

    # Fetch actual YoY GDP from cache (already fetched above)
    df_yoy = cache.get("gdp_qtr_real")
    if df_yoy is None:
        df_yoy = OpenDOSMClient().fetch("gdp_qtr_real", limit=20000)
    actual_yoy = {}
    for _, row in df_yoy.iterrows():
        if row["series"] == "growth_yoy":
            d = row["date"]
            y, m = d.year, d.month
            q = (m - 1) // 3 + 1
            actual_yoy[f"{y}-Q{q}"] = row["value"]

    # Build DOSM advance benchmark: advance YoY vs actual YoY
    dosm_preds = []
    dosm_acts = []
    for _, arow in advance_df.iterrows():
        qlabel = arow["quarter"]
        if qlabel in actual_yoy:
            dosm_preds.append(arow["overall_yoy"])
            dosm_acts.append(actual_yoy[qlabel])

    if len(dosm_preds) >= 3:
        dosm_pred_arr = np.array(dosm_preds)
        dosm_act_arr = np.array(dosm_acts)
        dosm_mae_yoy = compute_mae(dosm_act_arr, dosm_pred_arr)
        dosm_rmse_yoy = compute_rmse(dosm_act_arr, dosm_pred_arr)
        dosm_fda_yoy = compute_fda(dosm_act_arr, dosm_pred_arr)
        dosm_benchmark_rows.append({
            "model": "DOSM Advance (YoY)", "mae": dosm_mae_yoy,
            "rmse": dosm_rmse_yoy, "fda": dosm_fda_yoy,
            "n": len(dosm_preds), "type": "benchmark",
        })

    # Post-COVID subset
    pc_preds = []
    pc_acts = []
    for _, arow in advance_df.iterrows():
        qlabel = arow["quarter"]
        if qlabel.startswith(("2021", "2022", "2023", "2024", "2025")):
            if qlabel in actual_yoy:
                pc_preds.append(arow["overall_yoy"])
                pc_acts.append(actual_yoy[qlabel])

    dosm_benchmark_rows_pc = []
    if len(pc_preds) >= 3:
        pc_pred_arr = np.array(pc_preds)
        pc_act_arr = np.array(pc_acts)
        dosm_mae_pc = compute_mae(pc_act_arr, pc_pred_arr)
        dosm_rmse_pc = compute_rmse(pc_act_arr, pc_pred_arr)
        dosm_fda_pc = compute_fda(pc_act_arr, pc_pred_arr)
        dosm_benchmark_rows_pc.append({
            "model": "DOSM Advance (YoY)", "mae": dosm_mae_pc,
            "rmse": dosm_rmse_pc, "fda": dosm_fda_pc,
            "n": len(pc_preds), "type": "benchmark",
        })

# ---------------------------------------------------------------------------
# 5. Leaderboard
# ---------------------------------------------------------------------------
console.print("\n[bold cyan]MALAYSIA GDP NOWCASTING -- MODEL LEADERBOARD[/bold cyan]")
console.print(f"[dim]Evaluation: 2020-Q1 to 2025-Q4 | {len(df.dropna(subset=['actual_gdp_pct']))} vintages[/dim]")
console.print(f"[dim]Vintage method: Live ARC (2023-2026) + Fallback (2020-2022)[/dim]\n")

actual = pd.to_numeric(df["actual_gdp_pct"], errors="coerce")

post_covid = df[df["quarter"].str.startswith(("2021", "2022", "2023", "2024", "2025"))]

# --- Full Period ---
table = Table(title="Full Period (2020-2025)")
table.add_column("Model", style="bold")
table.add_column("MAE (pp)", justify="right")
table.add_column("RMSE (pp)", justify="right")
table.add_column("FDA (%)", justify="right")
table.add_column("N", justify="right")

lb_rows = []
for label, col in [("DFM", "dfm_pct"), ("BVAR", "bvar_pct"), ("BEQ", "beq_pct"), ("NAIVE", "naive_pct"), ("ENSEMBLE", "ensemble_pct")]:
    if col not in df.columns:
        continue
    sub = df[[col, "actual_gdp_pct"]].dropna()
    if len(sub) < 3:
        continue
    pred = pd.to_numeric(sub[col], errors="coerce")
    act = pd.to_numeric(sub["actual_gdp_pct"], errors="coerce")
    mae = compute_mae(act.values, pred.values)
    rmse = compute_rmse(act.values, pred.values)
    fda = compute_fda(act.values, pred.values)
    lb_rows.append({"model": label, "mae": mae, "rmse": rmse, "fda": fda, "n": len(sub), "type": "model"})
    table.add_row(label, f"{mae:.3f}", f"{rmse:.3f}", f"{fda:.1%}", str(len(sub)))

# --- DOSM Advance Estimate benchmark (proper YoY comparison) ---
for br in dosm_benchmark_rows:
    lb_rows.append(br)
    table.add_row(
        "[cyan]DOSM Advance (YoY)[/cyan]",
        f"{br['mae']:.3f}", f"{br['rmse']:.3f}",
        f"{br['fda']:.1%}", str(br['n']),
    )
    console.print("[dim]* DOSM Advance: official nowcast (~2wk after quarter end). Compared against actual YoY GDP.[/dim]")

console.print(table)

# ---------------------------------------------------------------------------
# 6. Component-level benchmark (sector breakdown)
# ---------------------------------------------------------------------------
SECTOR_MAP = {
    "overall_yoy": "p0", "agriculture_yoy": "p1", "mining_yoy": "p2",
    "manufacturing_yoy": "p3", "construction_yoy": "p4", "services_yoy": "p5",
}
SECTOR_NAMES = {"p0": "Overall", "p1": "Agriculture", "p2": "Mining",
                "p3": "Manufacturing", "p4": "Construction", "p5": "Services"}
SECTOR_DOSM = ["agriculture_yoy", "mining_yoy", "manufacturing_yoy", "construction_yoy", "services_yoy"]

# Fetch actual sector data for component benchmark
df_sector = cache.get("gdp_qtr_real_supply")
if df_sector is None:
    try:
        df_sector = OpenDOSMClient().fetch("gdp_qtr_real_supply", limit=20000)
    except Exception:
        df_sector = None

if df_sector is not None and advance_df is not None and len(advance_df) >= 3:
    console.print()
    table_sector = Table(title="Component-Level Benchmark: DOSM Advance vs Actual by Sector (YoY %)")
    table_sector.add_column("Sector", style="bold")
    table_sector.add_column("MAE (pp)", justify="right")
    table_sector.add_column("RMSE (pp)", justify="right")
    table_sector.add_column("FDA (%)", justify="right")
    table_sector.add_column("N", justify="right")

    sector_errors = []
    for sector_code in ["p1", "p2", "p3", "p4", "p5"]:
        sname = SECTOR_NAMES[sector_code]
        dosm_col = [k for k, v in SECTOR_MAP.items() if v == sector_code][0]

        preds = []
        acts = []
        for _, arow in advance_df.iterrows():
            qlabel = arow["quarter"]
            y, q = int(qlabel[:4]), int(qlabel[-1])  # "2024-Q2" -> 2024, 2
            q_date = pd.Timestamp(y, (q-1)*3 + 1, 1)
            
            # Actual from API
            if df_sector is not None:
                mask = (df_sector["date"] == q_date) & (df_sector["sector"] == sector_code) & (df_sector["series"] == "growth_yoy")
                act_rows = df_sector[mask]
                if len(act_rows) > 0:
                    acts.append(act_rows["value"].values[0])
                    preds.append(arow[dosm_col])

        if len(preds) >= 3:
            pa = np.array(preds); aa = np.array(acts)
            mae_s = compute_mae(aa, pa)
            rmse_s = compute_rmse(aa, pa)
            fda_s = compute_fda(aa, pa)
            sector_errors.append({"sector": sname, "mae": mae_s, "rmse": rmse_s, "fda": fda_s})
            table_sector.add_row(sname, f"{mae_s:.3f}", f"{rmse_s:.3f}", f"{fda_s:.1%}", str(len(preds)))

    if sector_errors:
        # Overall GDP benchmark
        dosm_preds_o = [a["overall_yoy"] for _, a in advance_df.iterrows()]
        acts_o = []
        for _, arow in advance_df.iterrows():
            qlabel = arow["quarter"]
            y, q = int(qlabel[:4]), int(qlabel[-1])
            q_date = pd.Timestamp(y, (q-1)*3 + 1, 1)
            mask = (df_sector["date"] == q_date) & (df_sector["sector"] == "p0") & (df_sector["series"] == "growth_yoy")
            act_rows = df_sector[mask]
            if len(act_rows) > 0:
                acts_o.append(act_rows["value"].values[0])

        if len(dosm_preds_o) == len(acts_o) and len(dosm_preds_o) >= 3:
            pa_o = np.array(dosm_preds_o[:len(acts_o)])
            aa_o = np.array(acts_o)
            mae_o = compute_mae(aa_o, pa_o)
            rmse_o = compute_rmse(aa_o, pa_o)
            fda_o = compute_fda(aa_o, pa_o)
            table_sector.add_row("[bold]OVERALL GDP[/bold]", f"{mae_o:.3f}", f"{rmse_o:.3f}", f"{fda_o:.1%}", str(len(acts_o)), style="bold cyan")

        console.print(table_sector)

# --- Post-COVID ---
console.print()
table2 = Table(title="Excluding COVID (2021-2025)")
table2.add_column("Model", style="bold")
table2.add_column("MAE (pp)", justify="right")
table2.add_column("RMSE (pp)", justify="right")
table2.add_column("FDA (%)", justify="right")
table2.add_column("N", justify="right")

lb_rows2 = []
for label, col in [("DFM", "dfm_pct"), ("BVAR", "bvar_pct"), ("BEQ", "beq_pct"), ("NAIVE", "naive_pct"), ("ENSEMBLE", "ensemble_pct")]:
    if col not in df.columns:
        continue
    sub = post_covid[[col, "actual_gdp_pct"]].dropna()
    if len(sub) < 3:
        continue
    pred = pd.to_numeric(sub[col], errors="coerce")
    act = pd.to_numeric(sub["actual_gdp_pct"], errors="coerce")
    mae = compute_mae(act.values, pred.values)
    rmse = compute_rmse(act.values, pred.values)
    fda = compute_fda(act.values, pred.values)
    lb_rows2.append({"model": label, "mae": mae, "rmse": rmse, "fda": fda, "n": len(sub), "type": "model"})
    table2.add_row(label, f"{mae:.3f}", f"{rmse:.3f}", f"{fda:.1%}", str(len(sub)))

# --- DOSM Advance benchmark post-COVID (proper YoY) ---
for br in dosm_benchmark_rows_pc:
    lb_rows2.append(br)
    table2.add_row(
        "[cyan]DOSM Advance (YoY)[/cyan]",
        f"{br['mae']:.3f}", f"{br['rmse']:.3f}",
        f"{br['fda']:.1%}", str(br['n']),
    )
    console.print("[dim]* DOSM Advance benchmark uses YoY actuals. Not comparable to QoQ SA model metrics.[/dim]")

console.print(table2)

# Best model
if lb_rows2:
    model_rows = [r for r in lb_rows2 if r["type"] == "model"]
    if model_rows:
        best_mae = min(model_rows, key=lambda r: r["mae"])
        best_fda = max(model_rows, key=lambda r: r["fda"])
        console.print(f"\n[green]Best MAE (post-COVID): {best_mae['model']} ({best_mae['mae']:.3f} pp)[/green]")
        console.print(f"[green]Best FDA (post-COVID): {best_fda['model']} ({best_fda['fda']:.1%})[/green]")

# Save
out_dir = Path("output/malaysia")
out_dir.mkdir(parents=True, exist_ok=True)

lb_df = pd.DataFrame(lb_rows)
lb_df.to_csv(out_dir / "leaderboard.csv", index=False)
lb_df.to_excel(out_dir / "leaderboard.xlsx", index=False)
# Include post-COVID
lb_df2 = pd.DataFrame(lb_rows2)
lb_df2.to_csv(out_dir / "leaderboard_postcovid.csv", index=False)

df.to_csv(out_dir / "backtest_details.csv", index=False)

console.print(f"\n[dim]Saved to {out_dir}/[/dim]")
console.print("[bold green]Done.[/bold green]")
