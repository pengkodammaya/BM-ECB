"""BACKTEST: Run pseudo-real-time nowcast evaluation with ARC-based vintages.

For each month from 2020 to 2025:
1. Simulate what data was available using publication lags
2. Fit DFM / BVAR / BEQ
3. Produce nowcast for next-quarter GDP
4. Compare against actual GDP (released later)
5. Build leaderboard
"""
import sys
sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from datetime import date
from pathlib import Path

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.eval.vintage import (
    VintageBuilder, generate_vintage_dates, MALAYSIA_PUBLICATION_LAGS,
)
from nowcasting_toolbox.eval.metrics import compute_mae, compute_fda, compute_rmse
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams, BVARParams, BEQParams

# ---------------------------------------------------------------------------
# 1. Dataset manifest (same as run_malaysia_nowcast.py)
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
ALL_NAMES = MONTHLY_NAMES + ["gdp"]

# ---------------------------------------------------------------------------
# 2. Fetch & prepare full dataset (once)
# ---------------------------------------------------------------------------

print("=" * 60)
print("FETCHING DATA")
print("=" * 60)

cache = DataCache(ttl_hours=24)
client = OpenDOSMClient()
data_frames = {}

# Invalidate all for fresh fetch
cache.invalidate_all()

for name, (did, col, tcode, group, filters) in DATASETS.items():
    df = cache.get(did)
    if df is not None:
        print(f"  {name}: cached ({len(df)} rows)")
        data_frames[name] = df
        continue
    try:
        df = client.fetch(did, limit=20000)
        if df is not None and not df.empty:
            cache.put(did, df)
            data_frames[name] = df
            print(f"  {name}: fetched ({len(df)} rows)")
    except Exception as e:
        print(f"  {name}: FAILED {e}")

client.close()

# Apply filters
filtered = {}
for name, (did, col, tcode, group, filters) in DATASETS.items():
    if name not in data_frames:
        continue
    df = data_frames[name].copy()
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
    if gdp_vals[i - 1] > 0:
        gdp_qoq[i] = (gdp_vals[i] - gdp_vals[i - 1]) / gdp_vals[i - 1]
gdp_df_full["gdp"] = gdp_qoq
gdp_df_full = gdp_df_full.dropna(subset=["gdp"])
filtered["gdp"] = gdp_df_full

# ---------------------------------------------------------------------------
# 3. Build common monthly grid
# ---------------------------------------------------------------------------

min_dates = [df["date"].min() for df in filtered.values()]
max_dates = [df["date"].max() for df in filtered.values()]
start_date_dt = max(min_dates)
end_date_dt = max(max_dates)

datet_full = generate_dates(
    start_date_dt.year, start_date_dt.month,
    end_date_dt.year, end_date_dt.month,
)
T_full = len(datet_full)
nM = len(MONTHLY_NAMES)
nQ = 1
X_full = np.full((T_full, nM + nQ), np.nan)

for j, name in enumerate(MONTHLY_NAMES):
    df = filtered[name].copy()
    if name == "ipi":
        df[name] = df[name] / 100.0  # already done above, safety
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

# Transform
X_trans = X_full.copy()
transform_map = {n: DATASETS[n][2] for n in MONTHLY_NAMES}
transform_map["gdp"] = 0

for j, name in enumerate(ALL_NAMES):
    tcode = transform_map.get(name, 1)
    freq = "quarterly" if name == "gdp" else "monthly"
    X_trans[:, j] = transform_series(X_full[:, j].copy(), tcode, freq)

# Standardize using FULL sample (for stability)
mu = np.nanmean(X_trans, axis=0)
sigma = np.nanstd(X_trans, axis=0)
sigma[sigma < 1e-10] = 1.0
X_std = (X_trans - mu) / sigma
X_pre_std = X_trans.copy()

# Trim leading NaN
first_full = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
X_std = X_std[first_full:]
X_raw = X_pre_std[first_full:]
datet = datet_full[first_full:]

print(f"\n  Estimation sample: {len(X_std)} months")
print(f"  Date range: {datet[0]} to {datet[-1]}")
print(f"  Monthly: {nM}, Quarterly: {nQ}")

# ---------------------------------------------------------------------------
# 4. Vintage builder
# ---------------------------------------------------------------------------

vb = VintageBuilder(MALAYSIA_PUBLICATION_LAGS)

# ---------------------------------------------------------------------------
# 5. Run backtest
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("BACKTEST: 2020-2025 (quarterly vintages)")
print("=" * 60)

# Use QUARTERLY vintages: evaluate on the 2nd month of each quarter
# (when partial data for that quarter is available but GDP is not yet released)
# The nowcast predicts GDP for the quarter containing the vintage date.
vintage_dates = generate_vintage_dates(2020, 2, 2025, 11, frequency="quarterly", day_of_month=15)

results = []
gdp_idx = -1

for i, vdate in enumerate(vintage_dates):
    # Which quarter are we nowcasting?
    # GDP for quarter containing vdate's month
    vmonth = vdate.month
    vyear = vdate.year
    q_end_m = ((vmonth - 1) // 3) * 3 + 3

    # Build vintage WITHOUT including the target quarter's GDP
    # (it hasn't been released yet)
    X_vint = vb.build(X_raw.copy(), datet, vdate, var_names=ALL_NAMES)

    # Standardize per-vintage (realistic)
    vint_mu = np.nanmean(X_vint, axis=0)
    vint_sigma = np.nanstd(X_vint, axis=0)
    vint_sigma[vint_sigma < 1e-10] = 1.0
    X_vint_std = (X_vint - vint_mu) / vint_sigma

    # Trim leading NaN rows
    valid_rows = ~np.all(np.isnan(X_vint_std), axis=1)
    if np.sum(valid_rows) < 24:
        continue
    first_valid = np.where(valid_rows)[0][0]
    X_vint_std = X_vint_std[first_valid:]
    X_vint_raw = X_vint[first_valid:]
    datet_vint = datet[first_valid:]

    # Skip if GDP column is entirely NaN
    if np.all(np.isnan(X_vint_std[:, gdp_idx])):
        continue

    # Run DFM
    try:
        dfm = DFM(DFMParams(r=2, p=4, max_iter=30, thresh=1e-5, idio=1))
        res = dfm.fit(X_vint_std)

        # Find the quarter-end row in the estimation sample
        q_end_idx = -1
        for t in range(len(datet_vint)):
            if datet_vint[t, 0] == vyear and datet_vint[t, 1] == q_end_m:
                q_end_idx = t
                break

        if q_end_idx < 0:
            continue

        # Nowcast = smoothed GDP at quarter-end month (standardized → un-standardize → %)
        nowcast_std = float(res.X_sm[q_end_idx, gdp_idx])
        nowcast_pct = (nowcast_std * vint_sigma[gdp_idx] + vint_mu[gdp_idx]) * 100

    except Exception as e:
        nowcast_pct = np.nan

    # Actual GDP for this quarter (from full dataset)
    actual_pct = np.nan
    for t in range(len(datet)):
        if datet[t, 0] == vyear and datet[t, 1] == q_end_m:
            if not np.isnan(X_raw[t, gdp_idx]):
                actual_pct = X_raw[t, gdp_idx] * 100
            break

    quarter_label = f"{vyear}-Q{(vmonth-1)//3 + 1}"
    results.append({
        "vintage_date": vdate.isoformat(),
        "quarter": quarter_label,
        "nowcast_dfm_pct": round(nowcast_pct, 2) if not np.isnan(nowcast_pct) else np.nan,
        "actual_gdp_pct": round(actual_pct, 2) if not np.isnan(actual_pct) else np.nan,
    })

    print(f"  {quarter_label}: nowcast={nowcast_pct:+.1f}%  actual={actual_pct:+.1f}%" if not np.isnan(nowcast_pct) else f"  {quarter_label}: (failed)")

print(f"\n  Total vintages: {len(results)}")

# ---------------------------------------------------------------------------
# 6. Build leaderboard
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("LEADERBOARD")
print("=" * 60)

df = pd.DataFrame(results).dropna(subset=["nowcast_dfm_pct", "actual_gdp_pct"])
if len(df) == 0:
    print("  No valid results.")
    sys.exit(0)

# Overall metrics
mae_val = compute_mae(df["actual_gdp_pct"].values, df["nowcast_dfm_pct"].values)
rmse_val = compute_rmse(df["actual_gdp_pct"].values, df["nowcast_dfm_pct"].values)
fda_val = compute_fda(df["actual_gdp_pct"].values, df["nowcast_dfm_pct"].values)

# Post-COVID metrics (exclude 2020)
df_post = df[~df["quarter"].str.startswith("2020")]
mae_post = compute_mae(df_post["actual_gdp_pct"].values, df_post["nowcast_dfm_pct"].values)
rmse_post = compute_rmse(df_post["actual_gdp_pct"].values, df_post["nowcast_dfm_pct"].values)
fda_post = compute_fda(df_post["actual_gdp_pct"].values, df_post["nowcast_dfm_pct"].values)

print(f"\n  Overall (2020-2025):")
print(f"    Number of evaluation points: {len(df)}")
print(f"    MAE:  {mae_val:.3f} pp")
print(f"    RMSE: {rmse_val:.3f} pp")
print(f"    FDA:  {fda_val:.1%}")

print(f"\n  Excluding COVID (2021-2025):")
print(f"    Number of evaluation points: {len(df_post)}")
print(f"    MAE:  {mae_post:.3f} pp")
print(f"    RMSE: {rmse_post:.3f} pp")
print(f"    FDA:  {fda_post:.1%}")

# Leaderboard table
from rich.console import Console
from rich.table import Table

console = Console()
table = Table(title="MALAYSIA GDP NOWCASTING — MODEL LEADERBOARD")
table.add_column("Period", style="bold")
table.add_column("MAE (pp)", justify="right")
table.add_column("RMSE (pp)", justify="right")
table.add_column("FDA (%)", justify="right")
table.add_column("N", justify="right")

table.add_row("2020-2025", f"{mae_val:.3f}", f"{rmse_val:.3f}", f"{fda_val:.1%}", str(len(df)))
table.add_row("2021-2025 (ex-COVID)", f"{mae_post:.3f}", f"{rmse_post:.3f}", f"{fda_post:.1%}", str(len(df_post)))
console.print(table)

# Save
out_dir = Path("output/malaysia")
out_dir.mkdir(parents=True, exist_ok=True)
lb_df = pd.DataFrame([
    {"model": "DFM", "period": "2020-2025", "MAE (pp)": round(mae_val, 3), "RMSE (pp)": round(rmse_val, 3), "FDA (%)": round(fda_val * 100, 1), "N": len(df)},
    {"model": "DFM", "period": "2021-2025", "MAE (pp)": round(mae_post, 3), "RMSE (pp)": round(rmse_post, 3), "FDA (%)": round(fda_post * 100, 1), "N": len(df_post)},
])
lb_df.to_csv(out_dir / "leaderboard.csv", index=False)
lb_df.to_excel(out_dir / "leaderboard.xlsx", index=False)

# Save detailed results
df.to_csv(out_dir / "backtest_details.csv", index=False)

print(f"\n  Results saved to {out_dir}/")
print("  Done.")
