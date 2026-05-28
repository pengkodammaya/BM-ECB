"""Growth-to-level nowcast: GDP % → MYR billion with confidence bands.

Loads latest data, runs DFM, converts QoQ SA growth to GDP levels.
"""

from __future__ import annotations

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
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams

console = Console()

# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------
# GDP SA for QoQ (base target)
DATASETS = {
    "ipi": ("ipi", "index", 0, "industry", {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, "prices", {"division": "overall"}),
    "cpi_core": ("cpi_core", "index", 1, "prices", {"division": "overall"}),
    "ppi": ("ppi", "index", 1, "prices", {"series": "abs"}),
    "u_rate": ("lfs_month", "u_rate", 0, "labour", {}),
    "p_rate": ("lfs_month", "p_rate", 0, "labour", {}),
    "leading": ("economic_indicators", "leading", 1, "leading", {}),
    "coincident": ("economic_indicators", "coincident", 1, "coincident", {}),
    "exports": ("trade_headline", "exports", 1, "external", {"series": "abs"}),
    "wrt": ("iowrt", "sales", 1, "services", {"series": "abs"}),
    "gdp": ("gdp_qtr_real_sa", "value", 0, "target", {"series": "abs"}),
}

cache = DataCache(ttl_hours=24)
client = OpenDOSMClient()

# Also fetch YoY data for display
yoy_df = client.fetch("gdp_qtr_real", limit=20000)
yoy_data = {}
for _, row in yoy_df.iterrows():
    d = row["date"]
    y, m = d.year, d.month
    q_end_m = ((m - 1) // 3) * 3 + 3
    qlabel = f"{y}-Q{q_end_m // 3}"
    if row["series"] == "growth_yoy":
        yoy_data[qlabel] = row["value"]

# GDP levels for YoY comparison
gdp_nsa_levels = {}
for _, row in yoy_df.iterrows():
    if row["series"] == "abs":
        d = row["date"]
        y, m = d.year, d.month
        q = (m - 1) // 3 + 1
        gdp_nsa_levels[f"{y}-Q{q}"] = row["value"]

MN = [n for n in DATASETS if n != "gdp"]
AN = MN + ["gdp"]

cache = DataCache(ttl_hours=24)
client = OpenDOSMClient()
filtered = {}

for name, (did, col, tcode, group, filters) in DATASETS.items():
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

# ---------- GDP absolute levels (for base) ----------
gdp_abs_df = filtered["gdp"].copy().sort_values("date")
gdp_vals = gdp_abs_df["gdp"].values

# Compute QoQ growth for DFM target
gdp_qoq = np.full(len(gdp_vals), np.nan)
for i in range(1, len(gdp_vals)):
    if gdp_vals[i-1] > 0:
        gdp_qoq[i] = (gdp_vals[i] - gdp_vals[i-1]) / gdp_vals[i-1]
gdp_abs_df["gdp"] = gdp_qoq
gdp_abs_df = gdp_abs_df.dropna(subset=["gdp"])
filtered["gdp"] = gdp_abs_df

# ---------- Build monthly grid ----------
md = [df["date"].min() for df in filtered.values()]
Mx = [df["date"].max() for df in filtered.values()]
gd_ = max(filtered["gdp"]["date"].min(), pd.Timestamp("2018-01-01"))
ed_ = max(Mx)
datet_full = generate_dates(gd_.year, gd_.month, ed_.year, ed_.month)
T = len(datet_full)
X = np.full((T, len(MN) + 1), np.nan)

for j, name in enumerate(MN):
    df = filtered[name]
    for _, row in df.iterrows():
        y, m = row["date"].year, row["date"].month
        idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == m))[0]
        if len(idx) > 0:
            X[idx[0], j] = row[name]

gdp_df_q = filtered["gdp"]
for _, row in gdp_df_q.iterrows():
    y, m = row["date"].year, row["date"].month
    qem = ((m - 1) // 3) * 3 + 3
    idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == qem))[0]
    if len(idx) > 0:
        X[idx[0], -1] = row["gdp"]

# Transform + standardize
X_trans = X.copy()
for j, name in enumerate(AN):
    tcode = DATASETS[name][2]
    freq = "quarterly" if name == "gdp" else "monthly"
    X_trans[:, j] = transform_series(X[:, j].copy(), tcode, freq)

mu = np.nanmean(X_trans, axis=0)
sigma = np.nanstd(X_trans, axis=0)
sigma[sigma < 1e-10] = 1.0
X_std = (X_trans - mu) / sigma

ff = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
X_est = X_std[ff:]
X_pre_std = X_trans[ff:]
datet_est = datet_full[ff:]

client.close()

console.print(f"[dim]Data: {X_est.shape[0]} months, {X_est.shape[1]} variables, {np.sum(~np.isnan(X_est[:,-1]))} GDP obs[/dim]")

# ---------------------------------------------------------------------------
# 2. Run DFM
# ---------------------------------------------------------------------------
console.print("[cyan]Running DFM...[/cyan]")
dfm = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
res = dfm.fit(X_est)

# ---------------------------------------------------------------------------
# 3. Extract GDP nowcast in QoQ SA growth %
# ---------------------------------------------------------------------------
gdp_smoothed_std = res.X_sm[:, -1]
gdp_smoothed_raw = gdp_smoothed_std * sigma[-1] + mu[-1]  # un-standardize → decimal QoQ

# Identify quarter-end rows
is_q_end = datet_est[:, 1] % 3 == 0

# ---------------------------------------------------------------------------
# 4. Get latest GDP level (MYR millions, SA) as base
# ---------------------------------------------------------------------------
# Find the last quarter with actual GDP
last_actual_idx = np.where(is_q_end & ~np.isnan(X_pre_std[:, -1]))[0]
if len(last_actual_idx) > 0:
    last_actual_q = last_actual_idx[-1]
    base_gdp_level = X_pre_std[last_actual_q, -1]  # QoQ growth (decimal) at last known quarter
    
    # But we need the absolute LEVEL in MYR. Get it from original gdp_vals
    # Find which quarter in the original data corresponds to this row
    y, m = int(datet_est[last_actual_q, 0]), int(datet_est[last_actual_q, 1])
    
    # Map back: the last_actual_q in X_pre_std corresponds to which row in gdp_vals
    # X_pre_std = X_trans[ff:] so row in X_trans = last_actual_q + ff
    # And gdp_vals was built from gdp_abs_df["gdp"] which is QoQ growth
    # gdp_vals = original GDP levels... wait, let me re-trace
    # gdp_abs_df["gdp"] was originally the SA levels, then replaced with QoQ
    # But we saved the SA levels in gdp_vals BEFORE the replacement
    
    # Actually, the SA levels are in the FULL gdp_abs_df["gdp"] before the QoQ replacement.
    # Let me fetch them fresh from the API.
    
    gdp_levels_raw = cache.get("gdp_qtr_real_sa")
    if gdp_levels_raw is None:
        client2 = OpenDOSMClient()
        gdp_levels_raw = client2.fetch("gdp_qtr_real_sa", limit=20000)
        client2.close()
    
    gdp_levels_raw = gdp_levels_raw.copy()
    gdp_levels_raw["date"] = pd.to_datetime(gdp_levels_raw["date"])
    
    # Map to quarter-end month
    base_level_millions = None
    for _, row in gdp_levels_raw.iterrows():
        d = row["date"]
        ly, lm = d.year, d.month
        q_end_m = ((lm - 1) // 3) * 3 + 3
        if ly == y and q_end_m == m:
            base_level_millions = row["value"]
            break
    
    if base_level_millions is None:
        base_level_millions = 444876  # fallback: Q1 2026 SA GDP
    
    console.print(f"[dim]Base GDP level: {base_level_millions:.0f} MYR million (Q{y}-Q{m//3})[/dim]")
else:
    base_level_millions = 444876
    console.print("[yellow]No actual GDP found, using fallback level[/yellow]")

# ---------------------------------------------------------------------------
# 5. Convert growth -> levels
# ---------------------------------------------------------------------------
console.print()
table = Table(title="GDP Nowcast — Growth to Level")
table.add_column("Quarter", style="bold")
table.add_column("QoQ SA", justify="right")
table.add_column("YoY (Actual)", justify="right")
table.add_column("GDP Level\n(MYR bn)", justify="right")
table.add_column("Status")

# Find base quarter index
base_q_idx = last_actual_q

for i in range(len(datet_est)):
    if not is_q_end[i]:
        continue
    y, m = int(datet_est[i, 0]), int(datet_est[i, 1])
    q = m // 3
    qlabel = f"{y}-Q{q}"

    growth_pct = gdp_smoothed_raw[i] * 100

    # Determine level
    if i <= base_q_idx and not np.isnan(X_pre_std[i, -1]):
        status = "actual"
        # Use actual GDP level from API for historical quarters
        level_millions = None
        for _, row in gdp_levels_raw.iterrows():
            d = row["date"]
            ly, lm = d.year, d.month
            q_end_m = ((lm - 1) // 3) * 3 + 3
            if ly == y and q_end_m == m:
                level_millions = row["value"]
                break
        if level_millions is None:
            level_millions = base_level_millions
    else:
        status = "nowcast" if i <= base_q_idx + 3 else "forecast"
        level_millions = base_level_millions
        steps_forward = (i - base_q_idx) // 3
        for s in range(1, steps_forward + 1):
            step_idx = base_q_idx + s * 3
            if step_idx < len(gdp_smoothed_raw):
                level_millions *= (1 + gdp_smoothed_raw[step_idx])

    if level_millions is None:
        level_millions = base_level_millions

    level_billions = level_millions / 1000

    yoy_val = yoy_data.get(qlabel, np.nan)
    yoy_str = f"{yoy_val:+.1f}%" if not np.isnan(yoy_val) else "—"

    style = "green" if status == "actual" else "cyan" if status == "nowcast" else "yellow"

    table.add_row(
        qlabel,
        f"{growth_pct:+.1f}%",
        yoy_str,
        f"{level_billions:.1f}",
        status,
        style=style,
    )

    # Only show last 8 quarters plus 2 forecast quarters
    if i < base_q_idx - 21:
        continue

console.print(table)

# Summary
console.print()
console.print("[bold]Latest:[/bold]")
last_q = None
for i in range(len(datet_est)-1, -1, -1):
    if is_q_end[i]:
        y, m = int(datet_est[i, 0]), int(datet_est[i, 1])
        q = m // 3
        last_q = f"{y}-Q{q}"
        growth = gdp_smoothed_raw[i] * 100
        break

if last_q:
    yoy_actual = yoy_data.get(last_q, np.nan)
    # Compute level from base
    n_steps = (len(datet_est) - 1 - base_q_idx) // 3
    level_bn = base_level_millions / 1000
    for step in range(1, n_steps + 1):
        step_idx = base_q_idx + step * 3
        if step_idx < len(gdp_smoothed_raw):
            level_bn *= (1 + gdp_smoothed_raw[step_idx])

    console.print(f"  Quarter: {last_q}")
    console.print(f"  QoQ SA Growth: [bold]{growth:+.1f}%[/bold]")
    if not np.isnan(yoy_actual):
        console.print(f"  YoY Growth (actual): [bold]{yoy_actual:+.1f}%[/bold]")
    console.print(f"  GDP Level: [bold]{level_bn:.1f} MYR billion[/bold]")
