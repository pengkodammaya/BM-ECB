"""Test BVAR and BEQ on Malaysian data pipeline."""
import sys
sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.bvar import BVAR
from nowcasting_toolbox.beq import BEQ
from nowcasting_toolbox.config import DFMParams, BVARParams, BEQParams, BEQParams as BParams

# ---------------------------------------------------------------------------
# 1. Fetch data (same pipeline as before)
# ---------------------------------------------------------------------------
DATASETS = {
    "ipi": ("ipi", "index", 0, {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, {"division": "overall"}),
    "cpi_core": ("cpi_core", "index", 1, {"division": "overall"}),
    "ppi": ("ppi", "index", 1, {"series": "abs"}),
    "u_rate": ("lfs_month", "u_rate", 0, {}),
    "p_rate": ("lfs_month", "p_rate", 0, {}),
    "leading": ("economic_indicators", "leading", 1, {}),
    "coincident": ("economic_indicators", "coincident", 1, {}),
    "gdp": ("gdp_qtr_real_sa", "value", 0, {"series": "abs"}),
}
MONTHLY_NAMES = [n for n in DATASETS if n != "gdp"]
ALL_NAMES = MONTHLY_NAMES + ["gdp"]

cache = DataCache(ttl_hours=24)
client = OpenDOSMClient()
filtered = {}

for name, (did, col, tcode, filters) in DATASETS.items():
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
start_dt = max(min_dates)
end_dt = max(max_dates)
datet = generate_dates(start_dt.year, start_dt.month, end_dt.year, end_dt.month)
T = len(datet)
nM = len(MONTHLY_NAMES)
nQ = 1
X = np.full((T, nM + nQ), np.nan)

for j, name in enumerate(MONTHLY_NAMES):
    df = filtered[name]
    for _, row in df.iterrows():
        y, m = row["date"].year, row["date"].month
        idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
        if len(idx) > 0:
            X[idx[0], j] = row[name]

gdp_df_q = filtered["gdp"]
for _, row in gdp_df_q.iterrows():
    y, m = row["date"].year, row["date"].month
    q_end_m = ((m - 1) // 3) * 3 + 3
    idx = np.where((datet[:, 0] == y) & (datet[:, 1] == q_end_m))[0]
    if len(idx) > 0:
        X[idx[0], -1] = row["gdp"]

X_trans = X.copy()
for j, name in enumerate(ALL_NAMES):
    tcode = DATASETS[name][2]
    freq = "quarterly" if name == "gdp" else "monthly"
    X_trans[:, j] = transform_series(X[:, j].copy(), tcode, freq)

mu = np.nanmean(X_trans, axis=0)
sigma = np.nanstd(X_trans, axis=0)
sigma[sigma < 1e-10] = 1.0
X_std = (X_trans - mu) / sigma

first_full = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
X_est = X_std[first_full:]

client.close()

print(f"Data: {X_est.shape[0]} months x {X_est.shape[1]} variables")
print(f"GDP obs: {np.sum(~np.isnan(X_est[:, -1]))}")

# ---------------------------------------------------------------------------
# 2. Run all three models
# ---------------------------------------------------------------------------

results = {}

# DFM
print("\n--- DFM ---")
dfm = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
res_dfm = dfm.fit(X_est)
dfm_nowcast = float(res_dfm.X_sm[-1, -1]) * sigma[-1] + mu[-1]
results["DFM"] = dfm_nowcast * 100
print(f"  Nowcast: {dfm_nowcast*100:+.2f}% QoQ SA")

# BVAR
print("\n--- BVAR ---")
try:
    # Fill NaN for BVAR (it needs complete data)
    X_filled = X_est.copy()
    for j in range(X_filled.shape[1]):
        col = X_filled[:, j]
        nan_mask = np.isnan(col)
        if np.any(nan_mask):
            valid = ~nan_mask
            if np.sum(valid) >= 2:
                idx_arr = np.arange(len(col))
                X_filled[nan_mask, j] = np.interp(idx_arr[nan_mask], idx_arr[valid], col[valid])

    bvar = BVAR(BVARParams(bvar_lags=3, bvar_thresh=1e-6, bvar_max_iter=50))
    res_bvar = bvar.fit(X_filled, datet[first_full:])
    bvar_nowcast = float(res_bvar.X_sm[-1, -1]) * sigma[-1] + mu[-1]
    results["BVAR"] = bvar_nowcast * 100
    print(f"  Nowcast: {bvar_nowcast*100:+.2f}% QoQ SA")
except Exception as e:
    print(f"  FAILED: {e}")
    results["BVAR"] = np.nan

# BEQ (uses raw transformed data, not standardized)
print("\n--- BEQ ---")
try:
    beq = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
    # BEQ expects non-standardized data (matches MATLAB toolbox convention)
    X_beq = X_trans[first_full:]  # raw transformed, not z-scored
    res_beq = beq.fit(X_beq, datet[first_full:], ALL_NAMES)
    if res_beq.X_sm is not None and res_beq.X_sm.shape[0] > 0:
        beq_nowcast = float(res_beq.X_sm[-1, -1])  # already in original scale
        results["BEQ"] = beq_nowcast * 100
        print(f"  Nowcast: {beq_nowcast*100:+.2f}% QoQ SA")
    else:
        print(f"  No forecast produced")
        results["BEQ"] = np.nan
except Exception as e:
    print(f"  FAILED: {e}")
    import traceback
    traceback.print_exc()
    results["BEQ"] = np.nan

# ---------------------------------------------------------------------------
# 3. Ensemble
# ---------------------------------------------------------------------------
valid_results = {k: v for k, v in results.items() if not np.isnan(v)}
if valid_results:
    ensemble_nowcast = np.median(list(valid_results.values()))
    results["ENSEMBLE"] = ensemble_nowcast
    print(f"\n--- ENSEMBLE (median) ---")
    print(f"  Nowcast: {ensemble_nowcast:+.2f}% QoQ SA")

# ---------------------------------------------------------------------------
# 4. Report
# ---------------------------------------------------------------------------
print("\n" + "=" * 50)
print("NOWCAST RESULTS (Latest Quarter)")
print("=" * 50)
for model, val in results.items():
    status = "OK" if not np.isnan(val) else "FAIL"
    val_str = f"{val:+.2f}% QoQ SA" if not np.isnan(val) else "FAILED"
    print(f"  {model:<12} {status} {val_str}")
