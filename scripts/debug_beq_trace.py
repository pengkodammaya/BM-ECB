"""Trace BEQ computation step-by-step to find bugs."""
import sys; sys.path.insert(0,"src")
import numpy as np
import pandas as pd
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series

# Load data
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
MN = [n for n in DATASETS if n != "gdp"]
AN = MN + ["gdp"]

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

gdp_df = filtered["gdp"].copy().sort_values("date")
gv = gdp_df["gdp"].values
gq = np.full(len(gv), np.nan)
for i in range(1, len(gv)):
    if gv[i-1] > 0:
        gq[i] = (gv[i] - gv[i-1]) / gv[i-1]
gdp_df["gdp"] = gq
gdp_df = gdp_df.dropna(subset=["gdp"])
filtered["gdp"] = gdp_df

md = [df["date"].min() for df in filtered.values()]
Mx = [df["date"].max() for df in filtered.values()]
sd = max(md)
ed = max(Mx)
datet = generate_dates(sd.year, sd.month, ed.year, ed.month)
T = len(datet)
X = np.full((T, len(MN) + 1), np.nan)

for j, name in enumerate(MN):
    df = filtered[name]
    for _, row in df.iterrows():
        y, m = row["date"].year, row["date"].month
        idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
        if len(idx) > 0:
            X[idx[0], j] = row[name]

gdp_df_q = filtered["gdp"]
for _, row in gdp_df_q.iterrows():
    y, m = row["date"].year, row["date"].month
    qem = ((m - 1) // 3) * 3 + 3
    idx = np.where((datet[:, 0] == y) & (datet[:, 1] == qem))[0]
    if len(idx) > 0:
        X[idx[0], -1] = row["gdp"]

X_trans = X.copy()
for j, name in enumerate(AN):
    tcode = DATASETS[name][2]
    freq = "quarterly" if name == "gdp" else "monthly"
    X_trans[:, j] = transform_series(X[:, j].copy(), tcode, freq)

mu = np.nanmean(X_trans, axis=0)
sigma = np.nanstd(X_trans, axis=0)
sigma[sigma < 1e-10] = 1.0
X_std = (X_trans - mu) / sigma
X_raw = X_trans.copy()

ff = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
X_std = X_std[ff:]
X_raw = X_raw[ff:]
datet_est = datet[ff:]

client.close()

print(f"Data: {len(datet_est)} months, {len(MN)} monthly + 1 quarterly")
print(f"GDP obs at quarter-end: {np.sum(~np.isnan(X_raw[:, -1]))}")
print(f"GDP values (first 5 quarter-ends): {X_raw[datet_est[:,1]%3==0, -1][:5]}")
print(f"GDP values (last 5 quarter-ends): {X_raw[datet_est[:,1]%3==0, -1][-5:]}")
print()

# ====================================================================
# MANUAL BEQ TRACE
# ====================================================================
from nowcasting_toolbox.beq.interpolate import extrapolate_bvar
from nowcasting_toolbox.beq.combinations import generate_combinations
from nowcasting_toolbox.beq.forecast import bridge_forecast

nM = len(MN)  # 8
nQ = 1

# Split data
Xm_raw = X_raw[:, :nM]
Xq_raw = X_raw[:, nM:nM + nQ]
Y = Xq_raw[datet_est[:, 1] % 3 == 0, -1]
dateQ = datet_est[datet_est[:, 1] % 3 == 0]

print(f"Xm_raw shape: {Xm_raw.shape}")
print(f"Xq_raw shape: {Xq_raw.shape}")
print(f"Y shape: {Y.shape}")
print(f"dateQ shape: {dateQ.shape}")
print(f"NaN in Y: {np.sum(np.isnan(Y))}")
print()

# Generate bridge equation specs
specs = generate_combinations(nM, nQ, types=[901])
print(f"Total bridge equations: {len(specs)}")
print(f"Spec format: [interp_type, monthly_1, monthly_2, quarterly]")
print(f"First 3 specs: {specs[:3]}")
print(f"Last 3 specs: {specs[-3:]}")
print()

# Trace first few bridge equations
n_bad = 0
n_good = 0
Y_fcst_samples = []
errors = []

for i in range(min(5, len(specs))):
    spec = specs[i]
    interp_type = int(spec[0])
    m1 = int(spec[1]) if not np.isnan(spec[1]) else None
    m2 = int(spec[2]) if not np.isnan(spec[2]) else None

    sel_m = [idx for idx in [m1, m2] if idx is not None]
    if not sel_m:
        continue

    Xm_sel = Xm_raw[:, sel_m]
    print(f"[{i}] Spec: type={interp_type}, monthly={sel_m}")

    # Interpolate
    try:
        Xm_interp = extrapolate_bvar(Xm_sel, method=interp_type)
        if Xm_interp is None or Xm_interp.size == 0:
            print(f"     Interpolation returned empty")
            n_bad += 1
            continue
    except Exception as e:
        print(f"     Interpolation FAILED: {e}")
        n_bad += 1
        continue

    # Forecast
    try:
        Y_fcst_i, date_fcst, contrib, coeffs = bridge_forecast(
            Xm_interp, datet_est, None, Y, dateQ,
            lagM=1, lagQ=1, lagY=1, dummies=None, re_estimate=True,
        )
        nan_count = np.sum(np.isnan(Y_fcst_i))
        print(f"     Y_fcst shape: {Y_fcst_i.shape}, NaN: {nan_count}/{len(Y_fcst_i)}")
        print(f"     Y_fcst last 5: {Y_fcst_i[-5:]}")
        print(f"     Valid coeffs: {np.sum(~np.isnan(coeffs))} of {len(coeffs)}")
        if nan_count == 0:
            Y_fcst_samples.append(Y_fcst_i)
            n_good += 1
        else:
            n_bad += 1
    except Exception as e:
        print(f"     Forecast FAILED: {e}")
        import traceback
        traceback.print_exc()
        n_bad += 1
        continue
    print()

print(f"\nGood: {n_good}, Bad: {n_bad}")

# Check median
if Y_fcst_samples:
    Y_fcst_indiv = np.column_stack([f for f in Y_fcst_samples])
    Y_fcst_median = np.nanmedian(Y_fcst_indiv, axis=1)
    print(f"\nMedian Y_fcst (last 5): {Y_fcst_median[-5:]}")
    print(f"Median Y_fcst[-1] = {Y_fcst_median[-1]:.6f} -> {Y_fcst_median[-1]*100:.2f}% QoQ")

# Check actual GDP
print(f"\nActual Y (last 5): {Y[-5:]}")
print(f"Actual Y[-1] = {Y[-1]:.6f} -> {Y[-1]*100:.2f}% QoQ")
