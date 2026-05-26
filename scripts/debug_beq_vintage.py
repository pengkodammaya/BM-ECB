"""Trace BEQ at a specific backtest vintage to find failure point."""
import sys; sys.path.insert(0,"src")
import numpy as np
import pandas as pd
from datetime import date

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.eval.vintage import ARCVintageBuilder, generate_vintage_dates
from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule
from nowcasting_toolbox.beq import BEQ
from nowcasting_toolbox.config import BEQParams

# Load data (same pipeline)
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
gdp_start = max(filtered["gdp"]["date"].min(), pd.Timestamp("2018-01-01"))
sd = gdp_start
ed = max(Mx)
datet_full = generate_dates(sd.year, sd.month, ed.year, ed.month)
T = len(datet_full)
X_full = np.full((T, len(MN) + 1), np.nan)

for j, name in enumerate(MN):
    df = filtered[name]
    for _, row in df.iterrows():
        y, m = row["date"].year, row["date"].month
        idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == m))[0]
        if len(idx) > 0:
            X_full[idx[0], j] = row[name]

gdp_df_q = filtered["gdp"]
for _, row in gdp_df_q.iterrows():
    y, m = row["date"].year, row["date"].month
    qem = ((m - 1) // 3) * 3 + 3
    idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == qem))[0]
    if len(idx) > 0:
        X_full[idx[0], -1] = row["gdp"]

X_trans = X_full.copy()
for j, name in enumerate(AN):
    tcode = DATASETS[name][2]
    freq = "quarterly" if name == "gdp" else "monthly"
    X_trans[:, j] = transform_series(X_full[:, j].copy(), tcode, freq)

mu = np.nanmean(X_trans, axis=0)
sigma = np.nanstd(X_trans, axis=0)
sigma[sigma < 1e-10] = 1.0
X_raw = X_trans.copy()

ff = np.where(~np.all(np.isnan(X_raw), axis=1))[0][0]
X_raw = X_raw[ff:]
datet = datet_full[ff:]

client.close()

# Build vintage builder
arc_schedule = build_publication_schedule(years=[2023, 2024, 2025, 2026], cache_dir=__import__('pathlib').Path("data/malaysia"))
vb = ARCVintageBuilder(schedule=arc_schedule)

DATASET_IDS_FOR_ARC = ["ipi", "cpi_headline", "cpi_core", "ppi", "u_rate", "u_rate", "leading", "coincident", "gdp"]

# Test at a few vintage dates where BEQ failed
test_dates = [
    date(2020, 5, 15),   # Q1 2020 (early, few obs)
    date(2023, 8, 15),   # Q2 2023 (BEQ showed NaN in backtest)
    date(2025, 5, 15),   # Q1 2025 (BEQ worked: 1.4%)
]

for vdate in test_dates:
    print(f"\n{'='*60}")
    print(f"VINTAGE: {vdate}")
    print(f"{'='*60}")

    X_vint = vb.build(X_raw.copy(), datet, vdate, var_names=AN, dataset_ids=DATASET_IDS_FOR_ARC)

    # Count valid rows
    valid_rows = ~np.all(np.isnan(X_vint), axis=1)
    first = np.where(valid_rows)[0][0]
    X_vint_trim = X_vint[first:]
    datet_vint = datet[first:]

    # Count GDP obs in vintage
    gdp_col = -1
    gdp_valid = np.sum(~np.isnan(X_vint_trim[:, gdp_col]))
    print(f"Vintage size: {X_vint_trim.shape[0]} rows, GDP obs: {gdp_valid}")

    # Run BEQ
    beq = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
    res = beq.fit(X_vint_trim, datet_vint, AN)

    yfc = res.Y_fcst
    xsm = res.X_sm

    # Check results
    nan_yfc = np.sum(np.isnan(yfc))
    print(f"Y_fcst: {len(yfc)} quarters, {nan_yfc} NaN")
    if len(yfc) > 0:
        print(f"Y_fcst last 5: {yfc[-5:]}")

    # Check X_sm GDP at quarter-end rows
    q_end_rows = np.where(datet_vint[:, 1] % 3 == 0)[0]
    if len(q_end_rows) > 0:
        last_q = q_end_rows[-1]
        gdp_val = xsm[last_q, gdp_col]
        y, m = int(datet_vint[last_q, 0]), int(datet_vint[last_q, 1])
        print(f"X_sm at {y}-{m:02d}: {gdp_val:.6f} -> {gdp_val*100:.2f}% QoQ")
