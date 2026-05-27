"""Run component nowcasts with BVAR/BEQ using cached data."""
import sys, json; sys.path.insert(0, "src")
import numpy as np
import pandas as pd
from pathlib import Path

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.bnm import fetch_interest_rate_history, fetch_exchange_rate_history
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.bvar import BVAR
from nowcasting_toolbox.beq import BEQ
from nowcasting_toolbox.config import DFMParams, BVARParams, BEQParams

# Use longer TTL since we have cached data
cache = DataCache(ttl_hours=72)
client = OpenDOSMClient()

# Load datasets from cache/API
DATASETS = {
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
    "wrt_volume": ("iowrt", "volume", 1, "consumption", {"series": "abs"}),
}

filtered = {}
for name, (did, col, tcode, group, filters) in DATASETS.items():
    print(f"Loading {name}...", end=" ")
    df = cache.get(did)
    if df is None:
        df = client.fetch(did, limit=20000)
        if df is not None and not df.empty:
            cache.put(did, df)
    if df is None or df.empty:
        print("EMPTY")
        continue
    df = df.copy()
    for fc, fv in filters.items():
        if fc in df.columns:
            df = df[df[fc] == fv]
    if col not in df.columns:
        print("NO COL")
        continue
    df = df[["date", col]].dropna().rename(columns={col: name})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date")
    filtered[name] = df
    print(f"{len(df)} rows")

# Transform growth rates
for var in ["ipi", "imports_capital", "imports_consumer"]:
    if var in filtered:
        filtered[var][var] = filtered[var][var] / 100.0

# Load BNM financial data
try:
    df_ib = fetch_interest_rate_history()
    if df_ib is not None and not df_ib.empty:
        df_ib = df_ib.rename(columns={"value": "interbank"})
        DATASETS["interbank"] = ("interbank", "interbank", 0, "financial", {})
        filtered["interbank"] = df_ib[["date", "interbank"]].dropna()
        print(f"interbank: {len(filtered['interbank'])} rows")
except Exception as e:
    print(f"BNM interbank failed: {e}")

try:
    df_fx = fetch_exchange_rate_history()
    if df_fx is not None and not df_fx.empty:
        df_fx = df_fx.rename(columns={"value": "fx_usd"})
        DATASETS["fx_usd"] = ("fx_usd", "fx_usd", 0, "financial", {})
        filtered["fx_usd"] = df_fx[["date", "fx_usd"]].dropna()
        print(f"fx_usd: {len(filtered['fx_usd'])} rows")
except Exception as e:
    print(f"BNM FX failed: {e}")

# Build common grid
gdp_sa = client.fetch("gdp_qtr_real_sa", limit=20000)
if gdp_sa is None or gdp_sa.empty:
    gdp_sa = pd.DataFrame()
if not gdp_sa.empty:
    gdp_sa["date"] = pd.to_datetime(gdp_sa["date"])
    gdp_sa = gdp_sa[gdp_sa["series"] == "abs"]
    gd_start = max(gdp_sa["date"].min(), pd.Timestamp("2018-01-01"))
else:
    gd_start = pd.Timestamp("2018-01-01")

max_dates = [df["date"].max() for df in filtered.values()]
ed_end = max(max_dates)
datet = generate_dates(gd_start.year, gd_start.month, ed_end.year, ed_end.month)
T = len(datet)

# Build monthly matrix
monthly_names = sorted(filtered.keys())
nM = len(monthly_names)
X_monthly = np.full((T, nM), np.nan)
for j, name in enumerate(monthly_names):
    df = filtered[name]
    for _, row in df.iterrows():
        y, m = row["date"].year, row["date"].month
        idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
        if len(idx) > 0:
            X_monthly[idx[0], j] = row[name]

Xm_trans = X_monthly.copy()
for j, name in enumerate(monthly_names):
    tcode = DATASETS[name][2]
    Xm_trans[:, j] = transform_series(X_monthly[:, j].copy(), tcode, "monthly")

# Component indicator groups
COMPONENT_INDICATORS = {
    "consumption": [n for n in DATASETS],
    "investment":  [n for n in DATASETS if DATASETS[n][3] in ("industry", "financial", "leading", "external")],
    "government":  [n for n in DATASETS],
    "exports_comp":[n for n in DATASETS if DATASETS[n][3] in ("external", "financial", "industry", "global_equity", "global_commodity", "global_demand")],
    "imports_comp":[n for n in DATASETS if DATASETS[n][3] in ("external", "services", "prices", "global_commodity")],
}
for ck, indicators in COMPONENT_INDICATORS.items():
    if len(indicators) < 3:
        COMPONENT_INDICATORS[ck] = [n for n in DATASETS]

COMPONENT_PARAMS = {
    "consumption": (2, 4), "investment": (3, 2), "government": (2, 2),
    "exports_comp": (3, 2), "imports_comp": (3, 2),
}

# Fetch demand data
df_demand = client.fetch("gdp_qtr_real_demand", limit=20000)
if df_demand is None or df_demand.empty:
    df_demand = pd.DataFrame()
nowcasts = {}

COMPONENTS = [
    ("consumption", "e1", "growth_yoy"),
    ("investment",  "e3", "growth_yoy"),
    ("government",  "e2", "growth_yoy"),
    ("exports_comp","e5", "growth_yoy"),
    ("imports_comp","e6", "growth_yoy"),
]

for comp_key, comp_type, comp_series in COMPONENTS:
    try:
        target_indicators = COMPONENT_INDICATORS.get(comp_key, monthly_names)
        target_names = [n for n in target_indicators if n in filtered]
        n_comp = len(target_names)
        if n_comp == 0:
            continue

        comp_val = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == comp_series)].copy()
        if len(comp_val) == 0:
            continue
        comp_val = comp_val[["date", "value"]].rename(columns={"value": "target"})
        comp_val["date"] = pd.to_datetime(comp_val["date"])
        comp_val = comp_val.sort_values("date").dropna()
        comp_val["target"] = comp_val["target"] / 100.0

        Xc = np.full((T, n_comp + 1), np.nan)
        for j, name in enumerate(target_names):
            df = filtered.get(name)
            if df is not None:
                for _, row in df.iterrows():
                    y, m = row["date"].year, row["date"].month
                    idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
                    if len(idx) > 0:
                        Xc[idx[0], j] = row[name]
        for _, row in comp_val.iterrows():
            y, m = row["date"].year, row["date"].month
            qem = ((m - 1) // 3) * 3 + 3
            idx = np.where((datet[:, 0] == y) & (datet[:, 1] == qem))[0]
            if len(idx) > 0:
                Xc[idx[0], -1] = row["target"]

        Xc_trans = Xc.copy()
        for j, name in enumerate(target_names):
            tcode = DATASETS.get(name, (None, None, 0, None, {}))[2]
            Xc_trans[:, j] = transform_series(Xc[:, j].copy(), tcode, "monthly")
        Xc_trans[:, -1] = Xc[:, -1].copy()

        muc = np.nanmean(Xc_trans, axis=0)
        sigmac = np.nanstd(Xc_trans, axis=0)
        sigmac[sigmac < 1e-10] = 1.0
        Xc_std = (Xc_trans - muc) / sigmac
        ffc = np.where(~np.all(np.isnan(Xc_std), axis=1))[0][0]
        Xc_est = Xc_std[ffc:]

        if np.sum(~np.isnan(Xc_est[:, -1])) < 5:
            continue

        cr, cp = COMPONENT_PARAMS.get(comp_key, (3, 2))

        # DFM
        dfm_c = DFM(DFMParams(r=cr, p=cp, max_iter=15, thresh=1e-4, idio=1))
        res_c = dfm_c.fit(Xc_est)
        nw = float(res_c.X_sm[-1, -1]) * sigmac[-1] + muc[-1]
        nowcasts[comp_key] = round(nw * 100, 2)

        # BVAR
        try:
            Xc_filled = Xc_est.copy()
            for j in range(Xc_filled.shape[1]):
                col = Xc_filled[:, j]
                nm = np.isnan(col); vl = ~nm
                if np.any(nm) and np.sum(vl) >= 2:
                    idx_arr = np.arange(len(col))
                    Xc_filled[nm, j] = np.interp(idx_arr[nm], idx_arr[vl], col[vl])
            bvar_c = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-3, bvar_max_iter=5))
            res_bc = bvar_c.fit(Xc_filled, datet[ffc:])
            nwb = float(res_bc.X_sm[-1, -1]) * sigmac[-1] + muc[-1]
            nowcasts[comp_key + "_bvar"] = round(nwb * 100, 2)
        except Exception as e:
            nowcasts[comp_key + "_bvar"] = None
            print(f"  BVAR {comp_key}: {e}")

        # BEQ
        try:
            Xc_raw = Xc_trans[ffc:]
            all_names = target_names + ["target"]
            beq_c = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
            res_ec = beq_c.fit(Xc_raw, datet[ffc:], all_names)
            if res_ec.X_sm is not None and res_ec.X_sm.shape[0] > 0:
                nwe = float(res_ec.X_sm[-1, -1])
                nowcasts[comp_key + "_beq"] = round(nwe * 100, 2)
            else:
                nowcasts[comp_key + "_beq"] = None
        except Exception as e:
            nowcasts[comp_key + "_beq"] = None
            print(f"  BEQ {comp_key}: {e}")

        print(f"  {comp_key}: DFM={nowcasts.get(comp_key):+.1f}%  BVAR={nowcasts.get(comp_key+'_bvar', '—'):>4s}  BEQ={nowcasts.get(comp_key+'_beq', '—'):>4s}")

    except Exception as e:
        print(f"  FAILED {comp_key}: {e}")

client.close()
print("\n=== Component Results ===")
print(json.dumps(nowcasts, indent=2))
