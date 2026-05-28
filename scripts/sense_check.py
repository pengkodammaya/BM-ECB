"""Compare DFM nowcast against DOSM official GDP figures (sense check)."""
import sys
sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from datetime import date

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
# 1. Fetch official GDP figures from DOSM
# ---------------------------------------------------------------------------
client = OpenDOSMClient()

# Non-SA GDP (has growth_qoq, growth_yoy)
df_real = client.fetch("gdp_qtr_real", limit=20000)
# SA GDP (abs levels only)
df_sa = client.fetch("gdp_qtr_real_sa", limit=20000)

# Official quarterly figures (non-SA — shift to quarter-end months)
official = {}
for _, row in df_real.iterrows():
    d = row["date"]
    y, m = d.year, d.month
    q_end_m = ((m - 1) // 3) * 3 + 3
    qdate = pd.Timestamp(y, q_end_m, 1)
    if qdate not in official:
        official[qdate] = {}
    official[qdate][row["series"]] = row["value"]

# Latest quarter-end dates
latest_dates = sorted(official.keys())[-8:]

# SA QoQ (computed from SA levels)
# GDP dates are 1st month of quarter (1,4,7,10) — shift to 3rd month (3,6,9,12)
sa_abs = {}
for _, row in df_sa.iterrows():
    d = row["date"]
    y, m = d.year, d.month
    q_end_m = ((m - 1) // 3) * 3 + 3
    sa_abs[pd.Timestamp(y, q_end_m, 1)] = row["value"]

sa_qoq = {}
sa_dates = sorted(sa_abs.keys())
for i in range(1, len(sa_dates)):
    if sa_abs[sa_dates[i-1]] > 0:
        sa_qoq[sa_dates[i]] = (sa_abs[sa_dates[i]] - sa_abs[sa_dates[i-1]]) / sa_abs[sa_dates[i-1]]

client.close()

# ---------------------------------------------------------------------------
# 2. Build our DFM nowcast (same pipeline as before)
# ---------------------------------------------------------------------------
DATASETS = {
    "ipi":          ("ipi", "index", 0, "industry", {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, "prices", {"division": "overall"}),
    "cpi_core":     ("cpi_core", "index", 1, "prices", {"division": "overall"}),
    "ppi":          ("ppi", "index", 1, "prices", {"series": "abs"}),
    "u_rate":       ("lfs_month", "u_rate", 0, "labour", {}),
    "p_rate":       ("lfs_month", "p_rate", 0, "labour", {}),
    "leading":      ("economic_indicators", "leading", 1, "leading", {}),
    "coincident":   ("economic_indicators", "coincident", 1, "coincident", {}),
    "gdp":          ("gdp_qtr_real_sa", "value", 0, "target", {"series": "abs"}),
}
MONTHLY_NAMES = [n for n in DATASETS if n != "gdp"]

cache = DataCache(ttl_hours=24)
# Re-open client (previous one was closed)
client2 = OpenDOSMClient()
filtered = {}
for name, (did, col, tcode, group, filters) in DATASETS.items():
    df = cache.get(did)
    if df is None:
        df = client2.fetch(did, limit=20000)
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

# IPI % -> decimal
if "ipi" in filtered:
    filtered["ipi"]["ipi"] = filtered["ipi"]["ipi"] / 100.0

# GDP: absolute levels -> QoQ growth
gdp_df_full = filtered["gdp"].copy().sort_values("date")
gdp_vals = gdp_df_full["gdp"].values
gdp_qoq = np.full(len(gdp_vals), np.nan)
for i in range(1, len(gdp_vals)):
    if gdp_vals[i-1] > 0:
        gdp_qoq[i] = (gdp_vals[i] - gdp_vals[i-1]) / gdp_vals[i-1]
gdp_df_full["gdp"] = gdp_qoq
gdp_df_full = gdp_df_full.dropna(subset=["gdp"])
filtered["gdp"] = gdp_df_full

# Build monthly grid
min_dates = [df["date"].min() for df in filtered.values()]
max_dates = [df["date"].max() for df in filtered.values()]
start_dt = max(min_dates)
end_dt = max(max_dates)
datet_full = generate_dates(start_dt.year, start_dt.month, end_dt.year, end_dt.month)
T = len(datet_full)
nM = len(MONTHLY_NAMES)
X = np.full((T, nM + 1), np.nan)

for j, name in enumerate(MONTHLY_NAMES):
    df = filtered[name]
    for _, row in df.iterrows():
        y, m = row["date"].year, row["date"].month
        idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == m))[0]
        if len(idx) > 0:
            X[idx[0], j] = row[name]

gdp_df_q = filtered["gdp"]
for _, row in gdp_df_q.iterrows():
    y, m = row["date"].year, row["date"].month
    q_end_m = ((m - 1) // 3) * 3 + 3
    idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == q_end_m))[0]
    if len(idx) > 0:
        X[idx[0], -1] = row["gdp"]

# Transform and standardize
X_trans = X.copy()
for j, name in enumerate(MONTHLY_NAMES + ["gdp"]):
    tcode = DATASETS[name][2]
    freq = "quarterly" if name == "gdp" else "monthly"
    X_trans[:, j] = transform_series(X[:, j].copy(), tcode, freq)

mu = np.nanmean(X_trans, axis=0)
sigma = np.nanstd(X_trans, axis=0)
sigma[sigma < 1e-10] = 1.0
X_std = (X_trans - mu) / sigma

first_full = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
X_est = X_std[first_full:]
datet_est = datet_full[first_full:]

# Run DFM
dfm = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
res = dfm.fit(X_est)
gdp_smoothed_pct = (res.X_sm[:, -1] * sigma[-1] + mu[-1]) * 100

# ---------------------------------------------------------------------------
# 3. Sense check: compare DFM nowcast vs DOSM official GDP
# ---------------------------------------------------------------------------
print()
console.print("[bold cyan]GDP NOWCAST — SENSE CHECK vs DOSM OFFICIAL[/bold cyan]")
print()

table = Table(title="Malaysia GDP: DFM Nowcast vs DOSM Official")
table.add_column("Quarter", style="bold")
table.add_column("DFM Nowcast\n(QoQ SA %)", justify="right")
table.add_column("DOSM Official\n(QoQ SA %)", justify="right")
table.add_column("DOSM Official\n(YoY %)", justify="right")
table.add_column("Diff\n(QoQ pp)", justify="right")

for i in range(len(datet_est)):
    y, m = datet_est[i]
    if m % 3 != 0:
        continue  # only quarter-end months
    q = (m // 3)
    qlabel = f"{y}-Q{q}"

    # DFM nowcast
    dfm_val = gdp_smoothed_pct[i]

    # DOSM official SA QoQ
    qdate = pd.Timestamp(y, m, 1)
    dosm_sa_val = sa_qoq.get(qdate, np.nan) * 100 if qdate in sa_qoq else np.nan

    # DOSM official YoY
    dosm_yoy = np.nan
    if qdate in official:
        dosm_yoy = official[qdate].get("growth_yoy", np.nan)

    if not np.isnan(dfm_val) or not np.isnan(dosm_sa_val):
        diff = (dfm_val - dosm_sa_val) if not np.isnan(dfm_val) and not np.isnan(dosm_sa_val) else np.nan
        diff_str = f"{diff:+.1f}" if not np.isnan(diff) else "—"
        dfm_str = f"{dfm_val:+.1f}" if not np.isnan(dfm_val) else "—"
        dosm_sa_str = f"{dosm_sa_val:+.1f}" if not np.isnan(dosm_sa_val) else "—"
        dosm_yoy_str = f"{dosm_yoy:+.1f}" if not np.isnan(dosm_yoy) else "—"

        # Color the row
        style = ""
        if not np.isnan(diff):
            if abs(diff) < 1.0:
                style = "green"
            elif abs(diff) < 2.0:
                style = "yellow"
            else:
                style = "red"

        table.add_row(qlabel, dfm_str, dosm_sa_str, dosm_yoy_str, diff_str, style=style)

console.print(table)

# Summary stats
diffs = []
for i in range(len(datet_est)):
    y, m = datet_est[i]
    if m % 3 != 0:
        continue
    qdate = pd.Timestamp(y, m, 1)
    dfm_val = gdp_smoothed_pct[i]
    dosm_sa_val = sa_qoq.get(qdate, np.nan) * 100 if qdate in sa_qoq else np.nan
    if not np.isnan(dfm_val) and not np.isnan(dosm_sa_val):
        diffs.append(dfm_val - dosm_sa_val)

if diffs:
    diffs_arr = np.array(diffs)
    print()
    console.print(f"[bold]Deviation from DOSM Official (QoQ SA, pp):[/bold]")
    console.print(f"  Mean:  {np.mean(diffs_arr):+.2f} pp")
    console.print(f"  MAE:   {np.mean(np.abs(diffs_arr)):.2f} pp")
    console.print(f"  RMSE:  {np.sqrt(np.mean(diffs_arr**2)):.2f} pp")
    console.print(f"  Max:   {np.max(np.abs(diffs_arr)):.1f} pp")
    console.print(f"  Corr:  {np.corrcoef([gdp_smoothed_pct[i] for i in range(len(datet_est)) if datet_est[i,1]%3==0], [sa_qoq.get(pd.Timestamp(int(datet_est[i,0]), int(datet_est[i,1]), 1), 0)*100 for i in range(len(datet_est)) if datet_est[i,1]%3==0])[0,1]:.3f}" if len(diffs)>=4 else "  Corr: N/A")

# Latest nowcast
print()
console.print("[bold]Latest:[/bold]")
last_q_idx = None
for i in range(len(datet_est)-1, -1, -1):
    if datet_est[i, 1] % 3 == 0 and not np.isnan(gdp_smoothed_pct[i]):
        last_q_idx = i
        break

if last_q_idx:
    y, m = datet_est[last_q_idx]
    q = m // 3
    console.print(f"  {y}-Q{q}: DFM nowcast = {gdp_smoothed_pct[last_q_idx]:+.1f}% QoQ SA")
    
    qdate = pd.Timestamp(y, m, 1)
    if qdate in sa_qoq:
        console.print(f"  {y}-Q{q}: DOSM official = {sa_qoq[qdate]*100:+.1f}% QoQ SA")
    
    next_m = m + 3
    next_y = y + (1 if next_m > 12 else 0)
    next_m = ((next_m - 1) % 12) + 1
    next_q = next_m // 3
    next_qdate = pd.Timestamp(next_y, next_m, 1)
    
    nowcast_next = None
    for i in range(len(datet_est)):
        if datet_est[i, 0] == next_y and datet_est[i, 1] == next_m:
            nowcast_next = gdp_smoothed_pct[i]
            break
    
    if nowcast_next is not None:
        console.print(f"  [bold]{next_y}-Q{next_q}: DFM nowcast (next) = {nowcast_next:+.1f}% QoQ SA[/bold]")
        if next_qdate in official:
            console.print(f"  [bold]{next_y}-Q{next_q}: DOSM official (actual) = {official[next_qdate].get('growth_qoq', 'N/A')}% QoQ NSA, {official[next_qdate].get('growth_yoy', 'N/A')}% YoY[/bold]")
