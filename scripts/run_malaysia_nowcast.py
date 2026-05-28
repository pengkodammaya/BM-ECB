"""Build and run a complete Malaysian nowcast pipeline.

1. Fetch all datasets from OpenDOSM API
2. Transform to growth rates / appropriate stationarity
3. Align on monthly date grid
4. Build ragged edge (simulate real-time data availability)
5. Run DFM nowcast
6. Report results
"""
import sys
sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from pathlib import Path

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams

# ---------------------------------------------------------------------------
# 1. Define dataset manifest
# ---------------------------------------------------------------------------

DATASETS = {
    # (id, value_column, transform_code, group, filter_dict)
    # Monthly indicators - use pre-computed growth rates where available
    "ipi":        ("ipi", "index", 0, "industry", {"series": "growth_mom"}),  # already MoM %
    "cpi_headline": ("cpi_headline", "index", 1, "prices", {"division": "overall"}),
    "cpi_core":   ("cpi_core", "index", 1, "prices", {"division": "overall"}),
    "ppi":        ("ppi", "index", 1, "prices", {"series": "abs"}),
    "u_rate":     ("lfs_month", "u_rate", 0, "labour", {}),  # already a rate
    "p_rate":     ("lfs_month", "p_rate", 0, "labour", {}),  # participation rate
    "leading":    ("economic_indicators", "leading", 1, "leading", {}),
    "coincident": ("economic_indicators", "coincident", 1, "coincident", {}),

    # Quarterly target - seasonally adjusted real GDP (compute QoQ from levels)
    "gdp":        ("gdp_qtr_real_sa", "value", 0, "target", {"series": "abs"}),
}

# ---------------------------------------------------------------------------
# 2. Fetch all data
# ---------------------------------------------------------------------------

print("=" * 60)
print("FETCHING MALAYSIAN DATA FROM OPENDOSM API")
print("=" * 60)

cache = DataCache(ttl_hours=24)
client = OpenDOSMClient()
data_frames = {}

for name, (did, col, tcode, group, filters) in DATASETS.items():
    print(f"  Fetching {name} ({did})...", end=" ", flush=True)

    # Check cache first
    df = cache.get(did)
    if df is not None and not df.empty:
        print(f"cached ({len(df)} rows)")
        data_frames[name] = df
        continue

    try:
        # Fetch all rows with a large limit (API supports this)
        df = client.fetch(did, limit=20000)
        if df is not None and not df.empty:
            cache.put(did, df)
            print(f"fetched ({len(df)} rows)")
            data_frames[name] = df
        else:
            print("empty")
    except Exception as e:
        print(f"FAILED: {e}")

client.close()

# ---------------------------------------------------------------------------
# 3. Apply filters (e.g., "overall" CPI, "abs" GDP)
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("FILTERING & TRANSFORMING")
print("=" * 60)

filtered = {}
for name, (did, col, tcode, group, filters) in DATASETS.items():
    if name not in data_frames:
        print(f"  SKIP {name} (no data)")
        continue
    df = data_frames[name].copy()

    for fcol, fval in filters.items():
        if fcol in df.columns:
            df = df[df[fcol] == fval]

    # Extract date + value
    if col not in df.columns:
        print(f"  SKIP {name} (col '{col}' not found in {list(df.columns)})")
        continue

    df = df[["date", col]].dropna().rename(columns={col: name})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date")

    print(f"  {name}: {len(df)} obs, {df['date'].min().date()} to {df['date'].max().date()}")
    filtered[name] = df

# ---------------------------------------------------------------------------
# 4. Build common monthly grid
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("BUILDING MONTHLY PANEL")
print("=" * 60)

# Find overlapping date range
min_dates = [df["date"].min() for df in filtered.values()]
max_dates = [df["date"].max() for df in filtered.values()]
start_date = max(min_dates)
end_date = max(max_dates)

print(f"  Range: {start_date.date()} to {end_date.date()}")

# Build monthly grid
start_y, start_m = start_date.year, start_date.month
end_y, end_m = end_date.year, end_date.month
datet = generate_dates(start_y, start_m, end_y, end_m)
T = len(datet)

# Names of monthly indicators (everything except gdp)
monthly_names = [n for n in filtered if n != "gdp"]
nM = len(monthly_names)
nQ = 1  # just GDP

print(f"  Grid: {T} months, {nM} monthly indicators + {nQ} quarterly target")

# Build X matrix: monthly columns first, then quarterly GDP
X = np.full((T, nM + nQ), np.nan)

for j, name in enumerate(monthly_names):
    df = filtered[name].copy()
    # Convert % to decimal for pre-computed growth rates (IPI growth_mom is in %)
    if name == "ipi":
        df[name] = df[name] / 100.0
    for _, row in df.iterrows():
        y, m = row["date"].year, row["date"].month
        idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
        if len(idx) > 0:
            X[idx[0], j] = row[name]

# GDP: align quarterly data (dates are 1st month of quarter -> map to 3rd month)
# Values are absolute levels in MYR millions, compute QoQ growth
gdp_df = filtered["gdp"].copy()
gdp_df = gdp_df.sort_values("date")
gdp_vals = gdp_df["gdp"].values
# Compute QoQ growth: (x_t - x_{t-1}) / x_{t-1}
gdp_qoq = np.full(len(gdp_vals), np.nan)
for i in range(1, len(gdp_vals)):
    if gdp_vals[i-1] > 0:
        gdp_qoq[i] = (gdp_vals[i] - gdp_vals[i-1]) / gdp_vals[i-1]
gdp_df["gdp"] = gdp_qoq
gdp_df = gdp_df.dropna(subset=["gdp"])

for _, row in gdp_df.iterrows():
    y, m = row["date"].year, row["date"].month
    # Shift from 1st month (1,4,7,10) to 3rd month (3,6,9,12)
    q_end_m = ((m - 1) // 3) * 3 + 3
    idx = np.where((datet[:, 0] == y) & (datet[:, 1] == q_end_m))[0]
    if len(idx) > 0:
        X[idx[0], -1] = row["gdp"]

print(f"  Complete rows: {np.sum(~np.any(np.isnan(X), axis=1))} / {T}")

# ---------------------------------------------------------------------------
# 5. Transform to growth rates / stationarity
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("TRANSFORMING (GROWTH RATES)")
print("=" * 60)

X_trans = X.copy()
transform_map = {n: DATASETS[n][2] for n in monthly_names}
transform_map["gdp"] = 0  # GDP already QoQ % from API, treat as level (no further transform)

for j, name in enumerate(monthly_names + ["gdp"]):
    tcode = transform_map.get(name, 1)
    col = X_trans[:, j].copy()
    freq = "quarterly" if name == "gdp" else "monthly"
    X_trans[:, j] = transform_series(col, tcode, freq)
    valid = np.sum(~np.isnan(X_trans[:, j]))
    print(f"  {name}: {valid} valid after transform (code {tcode})")

# Standardize (z-score)
mu = np.nanmean(X_trans, axis=0)
sigma = np.nanstd(X_trans, axis=0)
sigma[sigma < 1e-10] = 1.0
X_std = (X_trans - mu) / sigma

# Keep pre-standardized version for reporting
X_pre_std = X_trans.copy()

# Trim leading NaN rows (from transforms)
first_full = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
X_est = X_std[first_full:]
X_est_raw = X_pre_std[first_full:]  # pre-standardized, for reporting
datet_est = datet[first_full:]

print(f"\n  Estimation sample: {len(X_est)} months from {datet_est[0]} to {datet_est[-1]}")

# ---------------------------------------------------------------------------
# 7. Simulate ragged edge (last 6 months: only some variables available)
# ---------------------------------------------------------------------------

# Approximate publication lags (days after reference month):
# IPI: 8 days, CPI: 19 days, PPI: 25 days, Labour: 12 days, Leading: 25 days
# For simplicity: assume we're nowcasting from May 2026, data available up to:
# - IPI: Mar 2026 (2-month lag in our monthly grid)
# - CPI: Apr 2026 (1-month lag)  
# - PPI: Mar 2026 (2-month lag)
# - Labour: Apr 2026 (1-month lag)
# - Leading/Coincident: Mar 2026 (2-month lag)
# - GDP: Q1 2026 (released May 15 2026, so we have it)

# For now we just run on the full available history.
# The ragged edge is the natural trailing NaNs from differing publication lags.

X_nowcast = X_est.copy()

# ---------------------------------------------------------------------------
# 8. Run DFM nowcast
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("RUNNING DFM NOWCAST")
print("=" * 60)

params = DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1)
dfm = DFM(params, verbose=True)
result = dfm.fit(X_nowcast)

# Extract GDP nowcast (last column)
gdp_smoothed = result.X_sm[:, -1]
gdp_raw = X_nowcast[:, -1]

print(f"\n  Log-likelihood: {result.L:.2f}")
print(f"  Factors: {result.r}, Lags: {result.p}")

# GDP nowcast in original scale (QoQ %)
gdp_mu = mu[-1]  # GDP mean (from standardization)
gdp_sigma = sigma[-1]  # GDP std

# Smoothed GDP in standardized units -> un-standardize -> % 
gdp_smoothed_pct = gdp_smoothed * gdp_sigma + gdp_mu

# Latest observations
print(f"\n  Latest GDP values (QoQ %):")
for i in range(max(0, len(datet_est)-6), len(datet_est)):
    y, m = datet_est[i]
    raw_val = X_est_raw[i, -1]  # pre-standardized value, in decimal
    smoothed_val = gdp_smoothed_pct[i]
    marker = " <-- NOWCAST" if i == len(datet_est)-1 else ""
    if not np.isnan(raw_val):
        actual_pct = raw_val * 100  # decimal -> %
        print(f"    {y}-{m:02d}: actual={actual_pct:+.1f}%, smoothed={smoothed_val*100:+.1f}%")
    else:
        print(f"    {y}-{m:02d}: (no data),  nowcast={smoothed_val*100:+.1f}%{marker}")

# Latest actual GDP
gdp_actual_pct = None
for i in range(len(datet_est)-1, -1, -1):
    if not np.isnan(X_est_raw[i, -1]):
        gdp_actual_pct = X_est_raw[i, -1] * 100
        break

print(f"\n  Latest actual GDP: {gdp_actual_pct:+.1f}% QoQ" if gdp_actual_pct else "\n  No actual GDP in sample")
print(f"  Nowcast (next quarter): {gdp_smoothed_pct[-1]*100:.1f}% QoQ")

# ---------------------------------------------------------------------------
# 9. Report
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("NOWCAST SUMMARY")
print("=" * 60)

names = monthly_names + ["GDP"]
groups = [DATASETS[n][3] for n in monthly_names] + ["target"]

print(f"\n{'Variable':<16} {'Group':<12} {'Data End':<12} {'Transform'}")
print("-" * 56)
for j, name in enumerate(names):
    col = X_nowcast[:, j]
    valid = ~np.isnan(col)
    if np.any(valid):
        last_valid = np.where(valid)[0][-1]
        last_date = f"{datet_est[last_valid, 0]}-{datet_est[last_valid, 1]:02d}"
    else:
        last_date = "N/A"
    tcode = transform_map.get(name, 1)
    if name == "gdp":
        tname = "QoQ % (level)"
    else:
        tname = {0: "level", 1: "MoM dlog", 2: "diff", 3: "QoQ ann", 4: "YoY"}.get(tcode, f"code{tcode}")
    print(f"{name:<16} {groups[j]:<12} {last_date:<12} {tname}")

# Factor loadings
print(f"\n  Factor loadings (|C| > 0.2):")
for j, name in enumerate(names):
    loadings = result.C[j, :]
    big = np.where(np.abs(loadings) > 0.2)[0]
    if len(big) > 0:
        ld_str = ", ".join([f"F{int(k)}={loadings[k]:.3f}" for k in big])
        print(f"    {name:<16} {ld_str}")

print("\nDone.")
