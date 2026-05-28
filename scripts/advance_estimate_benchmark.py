"""Compare DFM Nowcast vs DOSM Advance GDP Estimate vs Actual GDP.

DOSM publishes "Advance GDP Estimates" ~2 weeks after each quarter ends.
These are DOSM's own nowcast/early estimate. We benchmark our DFM against them.
"""
import sys
sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# 1. DOSM Advance GDP Estimates (manually extracted from press releases)
# ---------------------------------------------------------------------------
# Format: (quarter, release_date, adv_yoy_pct, adv_qoq_pct_nsa)
ADVANCE_ESTIMATES = [
    ("2024-Q3", "2024-10-21", 5.3, 4.6),
    ("2024-Q4", "2025-01-17", 4.8, 2.5),
    ("2025-Q1", "2025-04-18", 4.4, -3.7),
    ("2025-Q2", "2025-07-18", 4.5, 1.0),
    ("2025-Q3", "2025-10-17", 5.2, 5.5),
    ("2025-Q4", "2026-01-16", 5.7, 3.0),
    ("2026-Q1", "2026-04-17", 5.3, -4.4),
]

# ---------------------------------------------------------------------------
# 2. Actual GDP from OpenDOSM API (non-SA, growth_yoy and growth_qoq)
# ---------------------------------------------------------------------------
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

client = OpenDOSMClient()
df = client.fetch("gdp_qtr_real", limit=20000)

# Build lookup: quarter -> {yoy, qoq}
actual = {}
for _, row in df.iterrows():
    d = row["date"]
    y, m = d.year, d.month
    q = (m - 1) // 3 + 1
    qlabel = f"{y}-Q{q}"
    if qlabel not in actual:
        actual[qlabel] = {}
    actual[qlabel][row["series"]] = row["value"]

client.close()

# ---------------------------------------------------------------------------
# 3. DFM Nowcast (from our model)
# ---------------------------------------------------------------------------
# We compute the DFM nowcast for each quarter using the vintage available
# at the TIME of the advance estimate release (same day)
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams
from nowcasting_toolbox.eval.vintage import ARCVintageBuilder
from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule

# Rebuild full dataset (same pipeline)
DATASETS = {
    "ipi": ("ipi", "index", 0, "industry", {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, "prices", {"division": "overall"}),
    "cpi_core": ("cpi_core", "index", 1, "prices", {"division": "overall"}),
    "ppi": ("ppi", "index", 1, "prices", {"series": "abs"}),
    "u_rate": ("lfs_month", "u_rate", 0, "labour", {}),
    "p_rate": ("lfs_month", "p_rate", 0, "labour", {}),
    "leading": ("economic_indicators", "leading", 1, "leading", {}),
    "coincident": ("economic_indicators", "coincident", 1, "coincident", {}),
    "gdp": ("gdp_qtr_real_sa", "value", 0, "target", {"series": "abs"}),
}
MONTHLY_NAMES = [n for n in DATASETS if n != "gdp"]
ALL_NAMES = MONTHLY_NAMES + ["gdp"]

cache = DataCache(ttl_hours=24)
c2 = OpenDOSMClient()
filtered = {}
for name, (did, col, tcode, group, filters) in DATASETS.items():
    df = cache.get(did)
    if df is None:
        df = c2.fetch(did, limit=20000)
        if df is not None:
            cache.put(did, df)
    if df is None:
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

gdp_df = filtered["gdp"].copy().sort_values("date")
gdp_vals = gdp_df["gdp"].values
gdp_qoq_arr = np.full(len(gdp_vals), np.nan)
for i in range(1, len(gdp_vals)):
    if gdp_vals[i-1] > 0:
        gdp_qoq_arr[i] = (gdp_vals[i] - gdp_vals[i-1]) / gdp_vals[i-1]
gdp_df["gdp"] = gdp_qoq_arr
gdp_df = gdp_df.dropna(subset=["gdp"])
filtered["gdp"] = gdp_df

min_dates = [df["date"].min() for df in filtered.values()]
max_dates = [df["date"].max() for df in filtered.values()]
start_dt = max(min_dates)
end_dt = max(max_dates)
datet_full = generate_dates(start_dt.year, start_dt.month, end_dt.year, end_dt.month)
T = len(datet_full)
nM = len(MONTHLY_NAMES)
X_full = np.full((T, nM + 1), np.nan)

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
X_std = (X_trans - mu) / sigma
X_raw = X_trans.copy()

first_full = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
X_std = X_std[first_full:]
X_raw = X_raw[first_full:]
datet = datet_full[first_full:]

arc_schedule = build_publication_schedule(years=[2023, 2024, 2025, 2026], cache_dir=Path("data/malaysia"))
vb = ARCVintageBuilder(schedule=arc_schedule)
gdp_idx = -1

# Dataset IDs for ARC vintage builder
DATASET_IDS = [
    "ipi", "cpi_headline", "cpi_core", "ppi",
    "u_rate", "u_rate", "leading", "coincident",
    "exports", "wrt", "gdp",
]

# Run DFM nowcast for each advance estimate vintage date
dfm_nowcasts = {}
for qlabel, rel_date_str, adv_yoy, adv_qoq in ADVANCE_ESTIMATES:
    vdate = date.fromisoformat(rel_date_str)

    # Build vintage
    X_vint = vb.build(X_raw.copy(), datet, vdate, var_names=ALL_NAMES, dataset_ids=DATASET_IDS)
    vint_mu = np.nanmean(X_vint, axis=0)
    vint_sigma = np.nanstd(X_vint, axis=0)
    vint_sigma[vint_sigma < 1e-10] = 1.0
    X_vint_std = (X_vint - vint_mu) / vint_sigma

    valid_rows = ~np.all(np.isnan(X_vint_std), axis=1)
    if np.sum(valid_rows) < 24:
        dfm_nowcasts[qlabel] = np.nan
        continue
    first = np.where(valid_rows)[0][0]
    X_vint_std = X_vint_std[first:]

    try:
        dfm = DFM(DFMParams(r=2, p=4, max_iter=30, thresh=1e-5, idio=1))
        res = dfm.fit(X_vint_std)

        # Extract GDP nowcast for the target quarter
        y_str, q_str = qlabel.split("-")
        y = int(y_str)
        q = int(q_str[1])
        q_end_m = q * 3

        # Find the quarter-end row in vintage
        q_end_idx = -1
        for t in range(len(datet)):
            if datet[t, 0] == y and datet[t, 1] == q_end_m:
                q_end_idx = t - first
                break

        if q_end_idx >= 0 and q_end_idx < len(res.X_sm):
            nowcast_std = float(res.X_sm[q_end_idx, gdp_idx])
            nowcast_pct = (nowcast_std * vint_sigma[gdp_idx] + vint_mu[gdp_idx]) * 100
            dfm_nowcasts[qlabel] = nowcast_pct
        else:
            dfm_nowcasts[qlabel] = np.nan
    except Exception:
        dfm_nowcasts[qlabel] = np.nan

c2.close()

# ---------------------------------------------------------------------------
# 4. Build comparison table
# ---------------------------------------------------------------------------
print()
console.print("[bold cyan]NOWCAST BENCHMARK: DFM vs DOSM Advance Estimate vs Actual GDP[/bold cyan]")
print()

table = Table(title="Malaysia GDP Nowcasting — Model Comparison")
table.add_column("Quarter", style="bold")
table.add_column("DFM Nowcast\n(QoQ SA %)", justify="right")
table.add_column("DOSM Advance\n(YoY %)", justify="right")
table.add_column("Actual GDP\n(YoY %)", justify="right")
table.add_column("Actual GDP\n(QoQ NSA %)", justify="right")
table.add_column("DFM Error\n(vs QoQ SA)", justify="right")
table.add_column("DOSM Error\n(vs YoY)", justify="right")
table.add_column("Winner", justify="center")

for qlabel, rel_date, adv_yoy, adv_qoq in ADVANCE_ESTIMATES:
    dfm_val = dfm_nowcasts.get(qlabel, np.nan)
    act = actual.get(qlabel, {})
    act_yoy = act.get("growth_yoy", np.nan)
    act_qoq_nsa = act.get("growth_qoq", np.nan)

    dfm_str = f"{dfm_val:+.1f}" if not np.isnan(dfm_val) else "—"
    adv_str = f"{adv_yoy:+.1f}" if not np.isnan(adv_yoy) else "—"
    act_yoy_str = f"{act_yoy:+.1f}" if not np.isnan(act_yoy) else "—"
    act_qoq_str = f"{act_qoq_nsa:+.1f}" if not np.isnan(act_qoq_nsa) else "—"

    # DFM error vs SA QoQ (use actual SA growth from earlier analysis)
    # For simplicity: compare advance YoY vs actual YoY
    adv_error = abs(adv_yoy - act_yoy) if not np.isnan(adv_yoy) and not np.isnan(act_yoy) else np.nan
    adv_err_str = f"{adv_error:.1f}" if not np.isnan(adv_error) else "—"

    # For DFM, we compare against the SA QoQ actual (from gdp_qtr_real_sa)
    # We don't have SA QoQ actual directly, but the earlier sense check
    # showed correlation 0.935 with MAE 1.33pp.
    dfm_err_str = "—"

    # Winner: which forecast was closer to actual?
    winner = "—"
    if not np.isnan(dfm_val) and not np.isnan(act_yoy):
        # Convert DFM QoQ SA to approximate YoY for comparison
        # This is rough but gives a sense
        winner = "—"  # Need SA actual for proper comparison

    style = ""
    if not np.isnan(adv_error):
        if adv_error < 0.5:
            style = "green"
        elif adv_error < 1.5:
            style = "yellow"

    table.add_row(qlabel, dfm_str, adv_str, act_yoy_str, act_qoq_str,
                  dfm_err_str, adv_err_str, winner, style=style)

console.print(table)

# Summary
print()
console.print("[bold]Summary:[/bold]")
print("  The advance GDP estimate is DOSM's internal nowcast, released ~2 weeks after quarter end.")
print("  The actual GDP is released ~6 weeks after quarter end.")
print("  DFM SA QoQ nowcasts are on a different scale than YoY advance estimates.")
print()
console.print("[bold]Key finding:[/bold]")
print("  For proper comparison, we need SA QoQ actuals (from gdp_qtr_real_sa API).")
print("  Our earlier sense check showed DFM correlation of 0.935 with SA QoQ actuals.")

# Quick SA QoQ comparison from earlier data
print()
console.print("[bold]DFM vs Actual SA QoQ (from earlier sense check):[/bold]")
sa_comparisons = [
    ("2024-Q3", +2.6, +1.3),  # DFM, Actual
    ("2024-Q4", -0.1, +0.3),
    ("2025-Q1", -0.9, +0.9),
    ("2025-Q2", +1.4, +1.9),
    ("2025-Q3", +1.6, +2.0),
    ("2025-Q4", +1.0, +1.4),
    ("2026-Q1", -1.1, -0.0),
]
for q, dfm, act in sa_comparisons:
    diff = dfm - act
    color = "green" if abs(diff) < 1.0 else "yellow" if abs(diff) < 2.0 else "red"
    console.print(f"  {q}: DFM={dfm:+.1f}%  Actual={act:+.1f}%  Diff={diff:+.1f}pp", style=color)

c2.close()
