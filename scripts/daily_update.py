"""Daily update: fetch live data, run all 3 models, append to history, update leaderboard.

Runs in GitHub Actions on schedule. No local cache needed — fetches fresh each time.
"""
import sys; sys.path.insert(0, "src")

import json
import traceback
import numpy as np
import pandas as pd
from datetime import datetime, date
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
from nowcasting_toolbox.eval.metrics import compute_mae, compute_fda, compute_rmse

# ---------------------------------------------------------------------------
# 1. Indicator manifest
# ---------------------------------------------------------------------------
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
    "wrt_volume": ("iowrt", "volume", 1, "consumption", {"series": "abs"}),  # real retail activity
    "gdp": ("gdp_qtr_real_sa", "value", 0, "target", {"series": "abs"}),
}
MN = [n for n in DATASETS if n != "gdp"]
AN = MN + ["gdp"]

# ---------------------------------------------------------------------------
# 2. Fetch data
# ---------------------------------------------------------------------------
print(f"[{datetime.now().isoformat()}] Daily update starting...")

cache = DataCache(ttl_hours=6)
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

# % to decimal
for var in ["ipi", "imports_capital", "imports_consumer"]:
    if var in filtered:
        filtered[var][var] = filtered[var][var] / 100.0

# BNM data
try:
    ir_df = fetch_interest_rate_history(start_year=2020, verbose=False)
    if not ir_df.empty:
        ir_df = ir_df.rename(columns={"value": "interbank"})
        filtered["interbank"] = ir_df[["date", "interbank"]]
except Exception as e:
    print(f"BNM interest rate failed (non-fatal): {e}")
try:
    fx_df = fetch_exchange_rate_history(start_year=2020, currency_code="USD", verbose=False)
    if not fx_df.empty:
        fx_vals = fx_df["value"].values
        fx_growth = np.full(len(fx_vals), np.nan)
        for i in range(1, len(fx_vals)):
            if fx_vals[i-1] > 0:
                fx_growth[i] = np.log(fx_vals[i]) - np.log(fx_vals[i-1])
        fx_df["fx_usd"] = fx_growth
        fx_df = fx_df.dropna(subset=["fx_usd"])
        filtered["fx_usd"] = fx_df[["date", "fx_usd"]]
except Exception:
    pass

# Extend manifest
for k in ["interbank", "fx_usd"]:
    if k in filtered:
        DATASETS[k] = (k, k, 0, "financial", {})

# ---------------------------------------------------------------------------
# 1.5 Add lagged FX features (3-month, 6-month) for export passthrough
# ---------------------------------------------------------------------------
if "fx_usd" in filtered:
    fx_df = filtered["fx_usd"].copy().sort_values("date")
    fx_vals = fx_df["fx_usd"].values
    fx_lag3 = np.full(len(fx_vals), np.nan)
    fx_lag6 = np.full(len(fx_vals), np.nan)
    fx_lag3[3:] = fx_vals[:-3]
    fx_lag6[6:] = fx_vals[:-6]
    fx_df["fx_lag3"] = fx_lag3
    fx_df["fx_lag6"] = fx_lag6
    fx_final = fx_df[["date", "fx_lag3", "fx_lag6"]].dropna()
    if len(fx_final) > 0:
        filtered["fx_lag3"] = fx_final[["date", "fx_lag3"]]
        filtered["fx_lag6"] = fx_final[["date", "fx_lag6"]]
        DATASETS["fx_lag3"] = ("fx_lag3", "fx_lag3", 0, "financial", {})
        DATASETS["fx_lag6"] = ("fx_lag6", "fx_lag6", 0, "financial", {})

# ---------------------------------------------------------------------------
# 1.6 Global demand / commodity indicators via yfinance
# ---------------------------------------------------------------------------
GLOBAL_INDICATORS = {
    "sp500": ("^GSPC", "global_equity"),      # S&P 500 — US/world demand proxy
    "shcomp": ("000001.SS", "global_equity"), # Shanghai Composite — China demand
    "sox":    ("^SOX", "global_equity"),       # Philly semi — E&E leads MY exports 1-3mo
    "brent":  ("BZ=F", "global_commodity"),    # Brent crude — energy commodity benchmark
    "cpo":    ("CPO=F", "global_commodity"),   # Crude palm oil — MY #1 agri-commodity
    "bdry":   ("BDRY", "global_demand"),       # Dry bulk shipping — trade volume proxy
}

for label, (ticker, group) in GLOBAL_INDICATORS.items():
    try:
        import yfinance as yf
        data = yf.download(ticker, start="2015-01-01", progress=False)
        if data is None or len(data) == 0:
            print(f"  yfinance {label}: no data")
            continue
        # Handle multi-level columns (yfinance v0.2+)
        if isinstance(data.columns, pd.MultiIndex):
            close_col = ("Close", ticker) if ("Close", ticker) in data.columns else data.columns[0]
        else:
            close_col = "Close" if "Close" in data.columns else "Adj Close"
        # Use close price, resample to month-end
        monthly = data[close_col].resample("ME").last().dropna()
        if len(monthly) < 24:
            continue
        # Compute MoM growth (dlog)
        vals = monthly.values
        growth = np.full(len(vals), np.nan)
        for i in range(1, len(vals)):
            if vals[i-1] > 0:
                growth[i] = np.log(vals[i]) - np.log(vals[i-1])
        df_out = pd.DataFrame({
            "date": monthly.index,
            label: growth,
        }).dropna()
        filtered[label] = df_out
        DATASETS[label] = (label, label, 0, group, {})  # transform 0 = already growth
        print(f"  yfinance {label}: {len(df_out)} monthly obs")
    except Exception as e:
        print(f"  yfinance {label} failed: {e}")

# ---------------------------------------------------------------------------
# 1.7 FRED economic data (US industrial production, capacity, sentiment)
# ---------------------------------------------------------------------------
FRED_SERIES = {
    "us_ip":      ("INDPRO", "global_demand"),   # US Industrial Production
    "us_caputil": ("TCU", "global_demand"),       # US Capacity Utilization
    "us_sentiment": ("UMCSENT", "global_demand"), # Consumer sentiment
}

fred_key_path = Path(".fred_key")
if fred_key_path.exists():
    fred_key = fred_key_path.read_text().strip()
    for label, (sid, group) in FRED_SERIES.items():
        try:
            import httpx
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": sid, "api_key": fred_key, "file_type": "json",
                "observation_start": "2015-01-01",
            }
            resp = httpx.get(url, params=params, timeout=15)
            data = resp.json()
            obs = data.get("observations", [])
            records = [(o["date"], float(o["value"])) for o in obs if o["value"] != "."]
            if len(records) < 24:
                continue
            df_fred = pd.DataFrame(records, columns=["date", label])
            df_fred["date"] = pd.to_datetime(df_fred["date"])
            # Resample to month-end (some daily, some monthly)
            df_fred = df_fred.set_index("date").resample("ME").last().dropna().reset_index()
            # For indices (INDPRO, TCU): compute MoM growth; for sentiment: use level
            if sid in ("INDPRO", "TCU"):
                vals = df_fred[label].values
                growth = np.full(len(vals), np.nan)
                for i in range(1, len(vals)):
                    if vals[i-1] > 0:
                        growth[i] = np.log(vals[i]) - np.log(vals[i-1])
                df_fred[label] = growth
                df_fred = df_fred.dropna()
                tcode = 0  # already growth
            else:
                tcode = 0  # level
            filtered[label] = df_fred
            DATASETS[label] = (label, label, tcode, group, {})
            print(f"  FRED {label}: {len(df_fred)} monthly obs")
        except Exception as e:
            print(f"  FRED {label} failed: {e}")

# ---------------------------------------------------------------------------
try:
    sitc_df = client.fetch("trade_sitc_1d", limit=20000)
    if sitc_df is not None and len(sitc_df) > 0:
        # Section 7 = machinery/transport (E&E), Section 3 = mineral fuels, overall = total
        for section, label in [("overall", "sitc_total"), ("7", "sitc_machinery")]:
            sub = sitc_df[(sitc_df["section"] == section)].copy()
            if len(sub) > 0:
                sub = sub[["date", "exports"]].dropna().rename(columns={"exports": label})
                sub["date"] = pd.to_datetime(sub["date"])
                sub = sub.sort_values("date").drop_duplicates("date")
                filtered[label] = sub
                DATASETS[label] = (label, label, 1, "external", {})  # dlog transform
except Exception as e:
    print(f"SITC data failed (non-fatal): {e}")

# Define component-specific indicator subsets
COMPONENT_INDICATORS = {
    # Consumption touches every sector — use ALL indicators with more lags
    "consumption": [n for n in DATASETS if n != "gdp"],
    # Investment: industry + financial + leading + external
    "investment":  [n for n in DATASETS if DATASETS[n][3] in ("industry", "financial", "leading", "external") and n != "gdp"],
    # Government: labour + financial (fiscal policy correlates with employment)
    "government":  [n for n in DATASETS if DATASETS[n][3] in ("labour", "financial") and n != "gdp"],
    # Exports: external + financial + industry + global
    "exports_comp":[n for n in DATASETS if DATASETS[n][3] in ("external", "financial", "industry", "global_equity", "global_commodity", "global_demand") and n != "gdp"],
    # Imports: external + services + prices + global commodity
    "imports_comp":[n for n in DATASETS if DATASETS[n][3] in ("external", "services", "prices", "global_commodity") and n != "gdp"],
}
# Fallback: if a subset is too small (<3 indicators), use all
for ck, indicators in COMPONENT_INDICATORS.items():
    if len(indicators) < 3:
        COMPONENT_INDICATORS[ck] = [n for n in DATASETS if n != "gdp"]

# Use optimized hyperparameters for each component
COMPONENT_PARAMS = {
    "consumption": (2, 4),  # more lags (consumption smoothing), fewer factors
    "investment":  (3, 2),  # balanced
    "government":  (2, 2),  # simple model
    "exports_comp":(3, 2),  # balanced
    "imports_comp":(3, 2),  # balanced
}

# GDP QoQ
gdp_df = filtered["gdp"].copy().sort_values("date")
gv = gdp_df["gdp"].values
gq = np.full(len(gv), np.nan)
for i in range(1, len(gv)):
    if gv[i-1] > 0:
        gq[i] = (gv[i] - gv[i-1]) / gv[i-1]
gdp_df["gdp"] = gq
gdp_df = gdp_df.dropna(subset=["gdp"])
filtered["gdp"] = gdp_df

# Build grid
MN = [n for n in DATASETS if n != "gdp" and n in filtered]
AN = MN + ["gdp"]
md = [df["date"].min() for df in filtered.values()]
Mx = [df["date"].max() for df in filtered.values()]
gd = max(filtered["gdp"]["date"].min(), pd.Timestamp("2018-01-01"))
ed = max(Mx)
# Extend grid 6 months into future for forecasting
ed_extended = ed + pd.DateOffset(months=6)
datet = generate_dates(gd.year, gd.month, ed_extended.year, ed_extended.month)
T = len(datet)
nM = len(MN)
X = np.full((T, nM + 1), np.nan)

# Fill known data (automatically leaves future months as NaN)

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

# Transform + standardize
X_trans = X.copy()
for j, name in enumerate(AN):
    tcode = DATASETS.get(name, (None, None, 0, None, {}))[2]
    freq = "quarterly" if name == "gdp" else "monthly"
    X_trans[:, j] = transform_series(X[:, j].copy(), tcode, freq)

mu = np.nanmean(X_trans, axis=0)
sigma = np.nanstd(X_trans, axis=0)
sigma[sigma < 1e-10] = 1.0
X_std = (X_trans - mu) / sigma
ff = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
X_est = X_std[ff:]

client.close()

# ---------------------------------------------------------------------------
# 3. Run all 3 models — produce nowcasts at 3 horizons
# ---------------------------------------------------------------------------
nowcasts = {}
today_str = date.today().isoformat()

# Determine the current quarter and year
today_dt = date.today()
current_quarter = (today_dt.month - 1) // 3 + 1
current_year = today_dt.year

# Find the last row with actual GDP (backcast quarter)
last_actual_idx = np.where(~np.isnan(X_est[:, -1]))[0][-1] if np.any(~np.isnan(X_est[:, -1])) else len(X_est) - 1

# Find the CURRENT quarter end month in the grid (the quarter we're NOWCASTING)
current_q_end_m = current_quarter * 3
current_q_idx = -1
for i in range(len(datet) - ff):
    if datet[ff + i, 0] == current_year and datet[ff + i, 1] == current_q_end_m:
        current_q_idx = i
        break

# Find the NEXT quarter end month (1-quarter-ahead forecast)
next_q_end_m = current_q_end_m + 3
next_q_year = current_year + (1 if next_q_end_m > 12 else 0)
next_q_end_m = ((next_q_end_m - 1) % 12) + 1
next_q_idx = -1
for i in range(len(datet) - ff):
    if datet[ff + i, 0] == next_q_year and datet[ff + i, 1] == next_q_end_m:
        next_q_idx = i
        break

# Label quarters
backcast_label = f"Q{((datet[ff + last_actual_idx, 1]) // 3)} {int(datet[ff + last_actual_idx, 0])}"
nowcast_label = f"Q{current_quarter} {current_year}" if current_q_idx >= 0 else "N/A"
forecast_label = f"Q{next_q_end_m // 3} {next_q_year}" if next_q_idx >= 0 else "N/A"

# DFM
try:
    dfm = DFM(DFMParams(r=3, p=2, max_iter=50, thresh=1e-5, idio=1))
    res = dfm.fit(X_est)
    
    def _extract(res, idx, sigma_arr, mu_arr, gdp_col=-1):
        if idx is not None and idx >= 0 and idx < res.X_sm.shape[0]:
            return round((float(res.X_sm[idx, gdp_col]) * sigma_arr[gdp_col] + mu_arr[gdp_col]) * 100, 2)
        return None

    nowcasts["dfm"] = _extract(res, current_q_idx, sigma, mu)  # nowcast
    nowcasts["dfm_backcast"] = _extract(res, last_actual_idx, sigma, mu)
    nowcasts["dfm_forecast"] = _extract(res, next_q_idx, sigma, mu)
except Exception as e:
    print(f"DFM failed: {e}")
    nowcasts["dfm"] = None

# BVAR
try:
    X_filled = X_est.copy()
    for j in range(X_filled.shape[1]):
        col = X_filled[:, j]
        nm = np.isnan(col); vl = ~nm
        if np.any(nm) and np.sum(vl) >= 2:
            idx_arr = np.arange(len(col))
            X_filled[nm, j] = np.interp(idx_arr[nm], idx_arr[vl], col[vl])
    bvar = BVAR(BVARParams(bvar_lags=3, bvar_thresh=1e-5, bvar_max_iter=15))
    res_b = bvar.fit(X_filled, datet[ff:])
    nowcasts["bvar"] = _extract(res_b, current_q_idx, sigma, mu)
    nowcasts["bvar_backcast"] = _extract(res_b, last_actual_idx, sigma, mu)
    nowcasts["bvar_forecast"] = _extract(res_b, next_q_idx, sigma, mu)
except Exception as e:
    print(f"BVAR failed: {e}")
    nowcasts["bvar"] = None

# BEQ
try:
    X_raw_beq = X_trans[ff:]
    beq = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
    res_e = beq.fit(X_raw_beq, datet[ff:], AN)
    gdp_col = -1
    # Find last quarter-end with valid GDP
    last_q = None
    for i in range(len(datet)-ff-1, -1, -1):
        if (datet[ff+i, 1] % 3 == 0) and not np.isnan(res_e.X_sm[i, gdp_col]):
            last_q = i
            break
    if last_q is not None:
        def _beq_val(idx, s, m):
            if idx is not None and idx >= 0 and idx < res_e.X_sm.shape[0]:
                return round((float(res_e.X_sm[idx, gdp_col]) * s[gdp_col] + m[gdp_col]) * 100, 2)
            return None
        nowcasts["beq"] = _beq_val(current_q_idx, sigma, mu)
        nowcasts["beq_backcast"] = _beq_val(last_actual_idx, sigma, mu)
        nowcasts["beq_forecast"] = _beq_val(next_q_idx, sigma, mu)
except Exception as e:
    print(f"BEQ failed: {e}")
    nowcasts["beq"] = nowcasts["beq_backcast"] = nowcasts["beq_forecast"] = None

# Ensemble (nowcast horizon only)
dfm_val = nowcasts.get("dfm")
bvar_val = nowcasts.get("bvar")
beq_val = nowcasts.get("beq")
vals = [v for v in [dfm_val, bvar_val, beq_val] if v is not None]
nowcasts["ensemble"] = round(np.median(vals), 2) if vals else None

# ---------------------------------------------------------------------------
# 3.5 AR(1) benchmark
# ---------------------------------------------------------------------------
try:
    # Extract GDP values at quarter-end months (in standardized space)
    gdp_qoq = X_est[:, -1]
    q_end_mask = np.array([datet[ff + i, 1] % 3 == 0 for i in range(len(X_est))])
    valid_mask = q_end_mask & ~np.isnan(gdp_qoq)
    gdp_vals = gdp_qoq[valid_mask]
    if len(gdp_vals) >= 4:
        y_lag = gdp_vals[:-1]
        y_curr = gdp_vals[1:]
        valid = ~np.isnan(y_lag) & ~np.isnan(y_curr)
        if np.sum(valid) >= 4:
            X_ar = np.column_stack([np.ones(np.sum(valid)), y_lag[valid]])
            ar_coeffs = np.linalg.lstsq(X_ar, y_curr[valid], rcond=None)[0]
            last_gdp = gdp_vals[-1] if not np.isnan(gdp_vals[-1]) else gdp_vals[-2]
            ar_std = ar_coeffs[0] + ar_coeffs[1] * last_gdp
            ar_pct = (ar_std * sigma[-1] + mu[-1]) * 100  # un-standardize
            nowcasts["ar1"] = round(ar_pct, 2)
except Exception as e:
    print(f"AR(1) failed: {e}")
    nowcasts["ar1"] = None

# ---------------------------------------------------------------------------
# 3.6 DOSM Advance Estimate lookup
# ---------------------------------------------------------------------------
dosm_advance = None
advance_path = Path("data/malaysia/dosm_advance_estimates.csv")
if advance_path.exists():
    try:
        adv_df = pd.read_csv(advance_path)
        # Find advance estimate for the current quarter
        adv_row = adv_df[adv_df["quarter"] == f"{current_year}-Q{current_quarter}"]
        if len(adv_row) > 0:
            dosm_advance = adv_row.iloc[0]
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 3b. Component-level nowcasts: C, I, G, X, M with GDP identity reconciliation
# ---------------------------------------------------------------------------
client2 = OpenDOSMClient()

# Fetch demand-side data ONCE for all components
df_demand = client2.fetch("gdp_qtr_real_demand", limit=20000)
if df_demand is None:
    df_demand = pd.DataFrame()

COMPONENTS = [
    ("consumption", "e1", "growth_yoy"),
    ("investment",  "e3", "growth_yoy"),
    ("government",  "e2", "growth_yoy"),
    ("exports_comp","e5", "growth_yoy"),
    ("imports_comp","e6", "growth_yoy"),
]

# Collect absolute levels for GDP identity
comp_levels = {}
comp_levels_yoy = {}

# Extract absolute levels and actual YoY from pre-fetched demand data
if not df_demand.empty:
    for comp_key, comp_type, _ in COMPONENTS:
        try:
            abs_data = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == "abs")]
            if len(abs_data) > 0:
                abs_data = abs_data.copy()
                abs_data["date"] = pd.to_datetime(abs_data["date"])
                comp_levels[comp_key] = abs_data.sort_values("date").iloc[-1]["value"]
            yoy_data = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == "growth_yoy")]
            if len(yoy_data) > 0:
                yoy_data = yoy_data.copy()
                yoy_data["date"] = pd.to_datetime(yoy_data["date"])
                comp_levels_yoy[comp_key] = yoy_data.sort_values("date").iloc[-1]["value"]
        except Exception:
            pass

# Now run component-level nowcasts using targeted indicator subsets
for comp_key, comp_type, comp_series in COMPONENTS:
    try:
        # Get targeted indicators for this component
        target_indicators = COMPONENT_INDICATORS.get(comp_key, MN)
        target_names = [n for n in target_indicators if n in filtered]
        n_comp = len(target_names)

        # Filter component data from pre-fetched demand DataFrame
        comp_val = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == comp_series)].copy()
        if len(comp_val) == 0:
            continue
        comp_val = comp_val[["date", "value"]].rename(columns={"value": "target"})
        comp_val["date"] = pd.to_datetime(comp_val["date"])
        comp_val = comp_val.sort_values("date").dropna()
        comp_val["target"] = comp_val["target"] / 100.0

        # Build component-specific grid with targeted indicators
        Xc = np.full((T, n_comp + 1), np.nan)
        for j, name in enumerate(target_names):
            if name in filtered:
                df = filtered[name]
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

        # Use component-specific hyperparameters
        cr, cp = COMPONENT_PARAMS.get(comp_key, (3, 2))
        dfm_c = DFM(DFMParams(r=cr, p=cp, max_iter=30, thresh=1e-5, idio=1))
        res_c = dfm_c.fit(Xc_est)
        nwc = float(res_c.X_sm[-1, -1]) * sigmac[-1] + muc[-1]
        nowcasts[comp_key + "_dfm"] = round(nwc * 100, 2)

        # --- BVAR for component (PRIMARY) ---
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
            nowcasts[comp_key] = round(nwb * 100, 2)
        except Exception as e:
            nowcasts[comp_key] = nowcasts.get(comp_key + "_dfm")  # fallback to DFM

        # --- BEQ for component: skip (BVAR interpolation fails on component subsets) ---
        nowcasts[comp_key + "_beq"] = None
    except Exception as e:
        print(f"  Component {comp_key}: {e}")
        nowcasts[comp_key] = None

client2.close()

# ---------------------------------------------------------------------------
# 3c. GDP Identity Reconciliation: derive imports from C+I+G+X-GDP
# ---------------------------------------------------------------------------
# GDP = C + I + G + X - M  (expenditure approach)
# => M_growth = (C*C_growth + I*I_growth + G*G_growth + X*X_growth - GDP*GDP_growth) / M
try:
    # Get absolute levels of each component
    c_level = comp_levels.get("consumption", 0)
    i_level = comp_levels.get("investment", 0)
    g_level = comp_levels.get("government", 0)
    x_level = comp_levels.get("exports_comp", 0)
    m_level_abs = abs(comp_levels.get("imports_comp", 1))  # imports stored negative
    
    # Get nowcasts in decimal form
    c_growth = nowcasts.get("consumption", 0)
    i_growth = nowcasts.get("investment", 0)
    g_growth = nowcasts.get("government", 0)
    x_growth = nowcasts.get("exports_comp", 0)
    gdp_growth = nowcasts.get("dfm", 0)  # main GDP nowcast
    
    if all(v is not None for v in [c_growth, i_growth, g_growth, x_growth, gdp_growth, c_level, i_level, g_level, x_level, m_level_abs]):
        # Convert to decimal
        c_g = c_growth / 100
        i_g = i_growth / 100
        g_g = g_growth / 100
        x_g = x_growth / 100
        gdp_g = gdp_growth / 100
        
        # GDP identity: GDP = C + I + G + X - M
        # In growth terms: GDP*GDP_g = C*C_g + I*I_g + G*G_g + X*X_g - M*M_g
        # => M*M_g = C*C_g + I*I_g + G*G_g + X*X_g - GDP*GDP_g
        m_g = (c_level * c_g + i_level * i_g + g_level * g_g + x_level * x_g - (c_level + i_level + g_level + x_level - m_level_abs) * gdp_g) / m_level_abs
        nowcasts["imports_identity"] = round(m_g * 100, 2)
except Exception as e:
    print(f"GDP identity derivation failed: {e}")
    nowcasts["imports_identity"] = None

# Add actual YoY growth for components
for ck in ["consumption", "investment", "government", "exports_comp", "imports_comp"]:
    nowcasts[ck + "_actual"] = comp_levels_yoy.get(ck)

# ---------------------------------------------------------------------------
# 3.7 Component AR(1) benchmarks (simple momentum for each component)
# ---------------------------------------------------------------------------
COMP_AR1 = {}
if not df_demand.empty:
    for comp_key, comp_type, _ in COMPONENTS:
        try:
            # Get component YoY growth series
            comp_yoy = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == "growth_yoy")].copy()
            if len(comp_yoy) < 5:
                continue
            comp_yoy["date"] = pd.to_datetime(comp_yoy["date"])
            comp_yoy = comp_yoy.sort_values("date")
            y_vals = comp_yoy["value"].values  # already in %
            y_lag = y_vals[:-1]
            y_curr = y_vals[1:]
            valid = ~np.isnan(y_lag) & ~np.isnan(y_curr)
            if np.sum(valid) >= 4:
                X_ar = np.column_stack([np.ones(np.sum(valid)), y_lag[valid]])
                ar_coeffs = np.linalg.lstsq(X_ar, y_curr[valid], rcond=None)[0]
                ar_fc = ar_coeffs[0] + ar_coeffs[1] * y_vals[-1]
                COMP_AR1[comp_key] = round(ar_fc, 2)
        except Exception as e:
            print(f"  AR(1) {comp_key}: {e}")

# Merge component AR(1) into nowcasts
for ck, val in COMP_AR1.items():
    nowcasts[ck + "_ar1"] = val

# Naive forecast = last quarter actual for each component
for ck in ["consumption", "investment", "government", "exports_comp", "imports_comp"]:
    nowcasts[ck + "_naive"] = comp_levels_yoy.get(ck)  # same as _actual

# Latest actual GDP
actual_pct = None
for i in range(len(X_est)-1, -1, -1):
    if not np.isnan(X_est[i, -1]):
        actual_pct = float(X_est[i, -1] * sigma[-1] + mu[-1]) * 100
        break

nowcasts["date"] = today_str
nowcasts["actual_gdp_pct"] = round(actual_pct, 2) if actual_pct else None
nowcasts["naive"] = nowcasts["actual_gdp_pct"]  # naive = last quarter actual

# ---------------------------------------------------------------------------
# 4. Append to daily log
# ---------------------------------------------------------------------------
log_path = Path("docs/daily_log.csv")
new_row = pd.DataFrame([nowcasts])
if log_path.exists():
    log = pd.read_csv(log_path)
    log = pd.concat([log, new_row], ignore_index=True).drop_duplicates(subset=["date"], keep="last")
else:
    log = new_row
log.to_csv(log_path, index=False)
print(f"[{datetime.now().isoformat()}] Daily log written to {log_path} ({log_path.stat().st_size} bytes, {len(log)} rows)")

# ---------------------------------------------------------------------------
# 5. Compute rolling leaderboard from daily log
# ---------------------------------------------------------------------------
if len(log) >= 3:
    lb_rows = []
    for model in ["dfm", "bvar", "beq", "ensemble"]:
        col = model
        sub = log[[col, "actual_gdp_pct"]].dropna()
        if len(sub) < 3:
            continue
        pred = sub[col].values
        act = sub["actual_gdp_pct"].values
        lb_rows.append({
            "model": model.upper(),
            "MAE (pp)": round(compute_mae(act, pred), 3),
            "RMSE (pp)": round(compute_rmse(act, pred), 3),
            "FDA (%)": round(compute_fda(act, pred) * 100, 1),
            "N": len(sub),
            "last_nowcast": nowcasts[model],
        })

    lb_df = pd.DataFrame(lb_rows)
    lb_df.to_csv(Path("docs/leaderboard.csv"), index=False)

# -------------------------------------------------------------------
# 6. Generate markdown leaderboard with AR(1) + DOSM advance + timing labels
# -------------------------------------------------------------------
# Determine reference: DOSM advance if available for current quarter, else latest actual
adv_q_label = f"{current_year}-Q{current_quarter}"
adv_reference = None
adv_reference_source = ""
if dosm_advance is not None:
    adv_reference = dosm_advance.get("overall_yoy")
    adv_reference_source = f"DOSM Advance ({dosm_advance.get('release_date', '?')})"
elif actual_pct is not None:
    adv_reference = actual_pct
    adv_reference_source = f"DOSM Actual (latest: {backcast_label}) — advance for {nowcast_label} pending"

md = f"# Malaysia GDP Nowcasting — Live Leaderboard\n\n"
md += f"**Updated:** {today_str} | **Nowcasting:** {nowcast_label} | **Reference:** {adv_reference_source}\n\n"

md += "## Current Quarter Nowcast (QoQ SA %)\n\n"
md += f"*Nowcasting GDP for **{nowcast_label}**. Advance estimate expected ~mid-{(current_quarter*3+1)%12 or 12}.*\n\n"

all_models = ["DFM", "BVAR", "BEQ", "AR(1)", "NAIVE", "ENSEMBLE"]
model_errors = {}
for model in all_models:
    col = model.lower()
    val = nowcasts.get(col)
    if val is not None:
        err = abs(val - adv_reference) if adv_reference is not None else None
        model_errors[model] = err
        md += f"- **{model}:** `{val:+.2f}%`\n"

if adv_reference is not None:
    md += f"\n*Reference (best available): `{adv_reference:+.1f}%` — {adv_reference_source}*\n"
    # Highlight closest model(s)
    if model_errors:
        min_err = min(model_errors.values())
        best_models = [m for m, e in model_errors.items() if e == min_err]
        md += f"\n**Closest to reference:** {', '.join(best_models)} ({min_err:+.2f}pp err)\n"

md += f"\n## Backcast: {backcast_label} (QoQ SA %)\n\n"
md += f"*Model estimate for the most recent quarter with released GDP.*\n\n"
for model in ["DFM", "BVAR", "BEQ"]:
    bc = nowcasts.get(f"{model.lower()}_backcast")
    if bc is not None:
        md += f"- **{model}:** `{bc:+.2f}%`\n"
if actual_pct:
    md += f"\n*DOSM official: `{actual_pct:+.1f}%`*\n"

md += f"\n## 1-Quarter-Ahead Forecast: {forecast_label} (QoQ SA %)\n\n"
for model in ["DFM", "BVAR", "BEQ"]:
    fc = nowcasts.get(f"{model.lower()}_forecast")
    if fc is not None:
        md += f"- **{model}:** `{fc:+.2f}%`\n"

md += "\n## Model Leaderboard\n\n"
md += "*Daily nowcast accuracy vs best available reference. Metrics appear after 3+ days.*\n\n"
if len(log) >= 3:
    lb_rows = []
    for model in ["dfm", "bvar", "beq", "ar1", "naive", "ensemble"]:
        col = model
        if col not in log.columns:
            continue
        sub = log[[col, "actual_gdp_pct"]].dropna()
        if len(sub) < 3:
            continue
        pred = sub[col].values
        act = sub["actual_gdp_pct"].values
        lb_rows.append({
            "model": model.upper(),
            "MAE (pp)": round(compute_mae(act, pred), 3),
            "RMSE (pp)": round(compute_rmse(act, pred), 3),
            "FDA (%)": round(compute_fda(act, pred) * 100, 1),
            "N": len(sub),
            "last_nowcast": nowcasts.get(model),
        })
    lb_df = pd.DataFrame(lb_rows)
    lb_df.to_csv(Path("docs/leaderboard.csv"), index=False)

    md += "| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |\n"
    md += "|-------|----------|-----------|---------|---|--------|\n"
    for _, r in lb_df.iterrows():
        latest = r.get("last_nowcast", "—")
        latest_str = f"{latest:+.1f}%" if isinstance(latest, (int, float)) else "—"
        style_note = ""
        if r["model"] == "AR(1)":
            style_note = " *(baseline)*"
        elif r["model"] == "NAIVE":
            style_note = " *(last Q)*"
        elif r["model"] == "ENSEMBLE":
            style_note = " *(combined)*"
        md += f"| {r['model']}{style_note} | {r['MAE (pp)']:.3f} | {r['RMSE (pp)']:.3f} | {r['FDA (%)']:.1f}% | {int(r['N'])} | {latest_str} |\n"
else:
    md += f"*Leaderboard requires 3+ daily observations. Currently: {len(log)}. First metrics expected soon.*\n\n"
    md += "| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |\n"
    md += "|-------|----------|-----------|---------|---|--------|\n"
    for model in ["DFM", "BVAR", "BEQ", "AR(1)", "NAIVE", "ENSEMBLE"]:
        col = model.lower()
        val = nowcasts.get(col)
        latest_str = f"{val:+.1f}%" if val is not None else "—"
        style_note = " *(baseline)*" if model == "AR(1)" else " *(last Q)*" if model == "NAIVE" else " *(combined)*" if model == "ENSEMBLE" else ""
        md += f"| {model}{style_note} | — | — | — | {len(log)} | {latest_str} |\n"

md += f"\n## Recent Nowcasts ({min(30, len(log))} days)\n\n"
md += "| Date | DFM | BVAR | BEQ | AR(1) | NAIVE | ENSEMBLE | Reference |\n"
md += "|------|-----|------|-----|-------|-------|----------|----------|\n"
ref_str = f"{adv_reference:+.1f}%" if adv_reference is not None else "—"
for _, row in log.tail(30).iterrows():
    vals = []
    for m in ["dfm", "bvar", "beq", "ar1", "naive", "ensemble"]:
        v = row.get(m)
        vals.append(f"{v:+.1f}%" if pd.notna(v) else "—")
    md += f"| {row['date']} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} | {vals[4]} | {ref_str} |\n"

    md += f"\n## Component Leaderboard (YoY %)\n\n"
md += f"*DFM nowcast vs AR(1) baseline for each expenditure component. Actual values are the latest from DOSM API (Q1 2026, released May 15).*\n\n"

comp_labels = {
    "consumption": ("Consumption (Private)", "C"),
    "government": ("Government Spending", "G"),
    "investment": ("Investment (GFCF)", "I"),
    "exports_comp": ("Exports", "X"),
    "imports_comp": ("Imports", "M"),
}

for ck, (clabel, ccode) in comp_labels.items():
    # BVAR is primary for components, DFM is comparison
    bvar_val = nowcasts.get(ck)           # primary (BVAR)
    dfm_val = nowcasts.get(ck + "_dfm")   # comparison (DFM)
    beq_val = nowcasts.get(ck + "_beq")
    beq_val = None if beq_val is not None and (isinstance(beq_val, float) and np.isnan(beq_val)) else beq_val
    ar1_val = nowcasts.get(ck + "_ar1")
    naive_val = nowcasts.get(ck + "_naive")
    act_val = nowcasts.get(ck + "_actual")
    
    dfm_f = f"{dfm_val:+.1f}%" if dfm_val is not None else "—"
    bvar_f = f"{bvar_val:+.1f}%" if bvar_val is not None else "—"
    beq_f = f"{beq_val:+.1f}%" if beq_val is not None else "—"
    ar1_f = f"{ar1_val:+.1f}%" if ar1_val is not None else "—"
    naive_f = f"{naive_val:+.1f}%" if naive_val is not None else "—"
    act_f = f"`{act_val:+.1f}%`" if act_val is not None else "—"
    
    # Errors vs reference
    def err(v):
        return abs(v - act_val) if (v is not None and act_val is not None) else None
    
    dfm_err = err(dfm_val)
    bvar_err = err(bvar_val)
    beq_err = err(beq_val)
    ar1_err = err(ar1_val)
    naive_err = 0.0 if (naive_val is not None and act_val is not None) else None
    
    # 5-tier rank emoji: 🟢=1st 🟡=2nd 🟠=3rd 🟤=4th 🔴=5th
    rank_emojis = [" 🟢", " 🟡", " 🟠", " 🟤", " 🔴"]
    model_rows = []
    
    if act_val is not None:
        pairs = [("DFM", dfm_val, dfm_err, dfm_f),
                 ("BVAR", bvar_val, bvar_err, bvar_f),
                 ("BEQ", beq_val, beq_err, beq_f),
                 ("AR(1)", ar1_val, ar1_err, ar1_f),
                 ("NAIVE", naive_val, naive_err, naive_f)]
        valid = [(m, v, e, f) for m, v, e, f in pairs if v is not None and e is not None]
        if len(valid) >= 2:
            valid.sort(key=lambda x: x[2])
            for rank, (m, v, e, f) in enumerate(valid):
                emoji = rank_emojis[rank] if rank < 5 else " " + str(rank + 1)
                note = ""
                if m == "AR(1)": note = " *(baseline)*"
                elif m == "NAIVE": note = " *(last Q)*"
                model_rows.append(f"| {m}{note} | {emoji} {f} ({e:+.1f}pp) | {act_f} |")
    if not model_rows:
        for m, f, note in [("DFM", dfm_f, ""), ("BVAR", bvar_f, ""), ("BEQ", beq_f, ""),
                           ("AR(1)", ar1_f, " *(baseline)*"), ("NAIVE", naive_f, " *(last Q)*")]:
            model_rows.append(f"| {m}{note} | `{f}` | {act_f} |")
    
    md += f"### {clabel} ({ccode})\n\n"
    md += "| Model | Nowcast | Reference (Actual) |\n"
    md += "|-------|---------|--------------------|\n"
    for row in model_rows:
        md += row + "\n"
    md += "\n"

# Show GDP-identity derived imports separately
imp_id = nowcasts.get("imports_identity")
imp_dir = nowcasts.get("imports_comp")
imp_act = nowcasts.get("imports_comp_actual")
if imp_id is not None:
    act_str = f"`{imp_act:+.1f}%`" if imp_act is not None else "—"
    dir_str = f"`{imp_dir:+.1f}%`" if imp_dir is not None else "—"
    md += f"#### GDP-Identity Derived Imports\n"
    md += f"- **Imports (identity):** nowcast `{imp_id:+.1f}%` vs actual {act_str}\n"
    md += f"- *Derived from C+I+G+X-GDP. Direct DFM was {dir_str}.*\n"

md += f"\n## Ground Truth Definition\n\n"
md += f"- **Main GDP:** QoQ SA growth from DOSM `gdp_qtr_real_sa` (seasonally adjusted, constant 2015 prices)\n"
md += f"- **Components:** YoY growth from DOSM `gdp_qtr_real_demand` (expenditure approach, non-SA)\n"
md += f"- **Source:** [OpenDOSM API](https://open.dosm.gov.my) — live data, fetched fresh each run\n"
md += f"- **Latest vintage:** {today_str}\n\n"
md += f"---\n*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*\n"
leaderboard_path = Path("docs") / "leaderboard.md"
leaderboard_path.write_text(md, encoding="utf-8")
print(f"[{datetime.now().isoformat()}] Leaderboard written to {leaderboard_path} ({leaderboard_path.stat().st_size} bytes)")

print(f"[{datetime.now().isoformat()}] Daily update complete.")
print(json.dumps(nowcasts, indent=2))
