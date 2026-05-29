"""Daily update: fetch live data, run all 3 models, append to history, update leaderboard.

Runs in GitHub Actions on schedule. No local cache needed — fetches fresh each time.
"""
import sys; sys.path.insert(0, "src")

import json
import traceback
import logging
import numpy as np
import pandas as pd
from datetime import datetime, date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("daily_update")

try:
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
    "klci":   ("^KLSE", "global_equity"),      # KLCI — Malaysian stock sentiment
    "sti":    ("^STI", "global_equity"),        # Straits Times — Singapore (#1 trade partner)
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
    dfm = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
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
        valid = np.where(~np.isnan(col))[0]
        if len(valid) < 2:
            continue
        last_valid = valid[-1]
        # Only interpolate BEFORE the last valid observation (no future leakage)
        for i in range(last_valid):
            if np.isnan(col[i]):
                prev_valid = valid[valid < i]
                next_valid = valid[valid > i]
                if len(prev_valid) > 0 and len(next_valid) > 0:
                    pv, nv = prev_valid[-1], next_valid[0]
                    col[i] = col[pv] + (col[nv] - col[pv]) * (i - pv) / (nv - pv)
                elif len(prev_valid) > 0:
                    col[i] = col[prev_valid[-1]]
        X_filled[:, j] = col
    # MASK backcast quarter for true out-of-sample forecast
    X_bvar = X_filled.copy()
    if last_actual_idx >= 0 and last_actual_idx < X_bvar.shape[0]:
        X_bvar[last_actual_idx, -1] = np.nan
    bvar = BVAR(BVARParams(bvar_lags=3, bvar_thresh=1e-5, bvar_max_iter=15))
    res_b = bvar.fit(X_bvar, datet[ff:])
    nowcasts["bvar"] = _extract(res_b, current_q_idx, sigma, mu)
    nowcasts["bvar_backcast"] = _extract(res_b, last_actual_idx, sigma, mu)
    nowcasts["bvar_forecast"] = _extract(res_b, next_q_idx, sigma, mu)

    # Fan chart from BVAR posterior draws
    if res_b.B_draws is not None and res_b.Sigma_draws is not None:
        from nowcasting_toolbox.fan_chart import bvar_fan_chart
        lags = 3
        N = X_filled.shape[1]
        # Last observation vector for forecasting
        x_last = X_filled[current_q_idx - lags + 1:current_q_idx + 1].flatten()
        if len(x_last) == N * lags:
            fc = bvar_fan_chart(
                res_b.B_draws, res_b.Sigma_draws, x_last,
                n_forecast=1, lags=lags, target_idx=-1,
                sigma_y=sigma[-1], mu_y=mu[-1],
            )
            nowcasts["bvar_ci_10"] = round(float(fc["percentiles"][10][0]) * 100, 2)
            nowcasts["bvar_ci_90"] = round(float(fc["percentiles"][90][0]) * 100, 2)
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

# Weighted ensemble (inverse MAE² weighting, falls back to simple median)
log_path_ens = Path("docs/daily_log.csv")
if log_path_ens.exists():
    log_ens = pd.read_csv(log_path_ens)
    if len(log_ens) >= 3:
        weights = {}
        for m in ["dfm", "bvar", "beq"]:
            if m in log_ens.columns:
                sub = log_ens[[m, "actual_gdp_pct"]].dropna()
                if len(sub) >= 3:
                    mae = compute_mae(sub["actual_gdp_pct"].values, sub[m].values)
                    weights[m] = 1.0 / (mae ** 2 + 0.01)  # +0.01 prevents divide by zero
        if weights:
            total_w = sum(weights.values())
            ensemble_val = sum(nowcasts.get(m, 0) * weights.get(m, 0) / total_w
                              for m in ["dfm", "bvar", "beq"] if nowcasts.get(m) is not None)
            nowcasts["ensemble"] = round(ensemble_val, 2)
        else:
            vals = [v for v in [nowcasts.get("dfm"), nowcasts.get("bvar"), nowcasts.get("beq")] if v is not None]
            nowcasts["ensemble"] = round(np.median(vals), 2) if vals else None
    else:
        vals = [v for v in [nowcasts.get("dfm"), nowcasts.get("bvar"), nowcasts.get("beq")] if v is not None]
        nowcasts["ensemble"] = round(np.median(vals), 2) if vals else None
else:
    vals = [v for v in [nowcasts.get("dfm"), nowcasts.get("bvar"), nowcasts.get("beq")] if v is not None]
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
# 3a. Fetch YoY GDP and sector data for DOSM-comparable metrics
# ---------------------------------------------------------------------------
client_yoy = OpenDOSMClient()

# Overall YoY GDP
df_gdp_yoy = client_yoy.fetch("gdp_qtr_real", limit=20000)
actual_yoy_gdp = None
if df_gdp_yoy is not None and not df_gdp_yoy.empty:
    yoy_rows = df_gdp_yoy[df_gdp_yoy["series"] == "growth_yoy"].copy()
    if not yoy_rows.empty:
        yoy_rows["date"] = pd.to_datetime(yoy_rows["date"])
        yoy_rows = yoy_rows.sort_values("date")
        actual_yoy_gdp = yoy_rows.iloc[-1]["value"]
        nowcasts["actual_yoy_gdp"] = round(actual_yoy_gdp, 2)

# Sector breakdowns (supply-side)
SECTOR_MAP = {
    "p1": "agriculture", "p2": "mining", "p3": "manufacturing",
    "p4": "construction", "p5": "services",
}
sector_actuals = {}
df_supply = client_yoy.fetch("gdp_qtr_real_supply", limit=20000)
if df_supply is not None and not df_supply.empty:
    for sector_code, sector_name in SECTOR_MAP.items():
        try:
            sector_rows = df_supply[
                (df_supply["sector"] == sector_code) & (df_supply["series"] == "growth_yoy")
            ].copy()
            if not sector_rows.empty:
                sector_rows["date"] = pd.to_datetime(sector_rows["date"])
                sector_rows = sector_rows.sort_values("date")
                sector_actuals[sector_name] = round(sector_rows.iloc[-1]["value"], 2)
        except Exception:
            pass

client_yoy.close()

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
                # MASK current AND backcast quarter — true out-of-sample forecast
                # BVAR should not see the actual value for the quarter it's estimating
                if (y == current_year and qem == current_q_end_m) or \
                   (y == int(datet[ff + last_actual_idx, 0]) and qem == int(datet[ff + last_actual_idx, 1])):
                    continue
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
                valid = np.where(~np.isnan(col))[0]
                if len(valid) < 2:
                    continue
                last_valid = valid[-1]
                # Only interpolate BEFORE the last valid observation (no future leakage)
                for i in range(last_valid):
                    if np.isnan(col[i]):
                        # Find surrounding valid values
                        prev_valid = valid[valid < i]
                        next_valid = valid[valid > i]
                        if len(prev_valid) > 0 and len(next_valid) > 0:
                            pv, nv = prev_valid[-1], next_valid[0]
                            col[i] = col[pv] + (col[nv] - col[pv]) * (i - pv) / (nv - pv)
                        elif len(prev_valid) > 0:
                            col[i] = col[prev_valid[-1]]
                Xc_filled[:, j] = col
            # Leave future NaN as NaN — BVAR should handle missing data properly
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
# 3c. YoY GDP Nowcast (DOSM-comparable metric)
# ---------------------------------------------------------------------------
# Use the same indicators but target YoY GDP instead of QoQ SA
if df_gdp_yoy is not None and not df_gdp_yoy.empty:
    try:
        # Build YoY GDP series
        yoy_rows = df_gdp_yoy[df_gdp_yoy["series"] == "growth_yoy"].copy()
        yoy_rows["date"] = pd.to_datetime(yoy_rows["date"])
        yoy_rows = yoy_rows.sort_values("date")
        yoy_rows["gdp_yoy"] = yoy_rows["value"] / 100.0  # % to decimal

        # Build grid for YoY GDP
        Xy = np.full((T, nM + 1), np.nan)
        for j, name in enumerate(MN):
            if name in filtered:
                df = filtered[name]
                for _, row in df.iterrows():
                    y, m = row["date"].year, row["date"].month
                    idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
                    if len(idx) > 0:
                        Xy[idx[0], j] = row[name]
        # Fill YoY GDP at quarter-end months
        for _, row in yoy_rows.iterrows():
            y, m = row["date"].year, row["date"].month
            qem = ((m - 1) // 3) * 3 + 3
            idx = np.where((datet[:, 0] == y) & (datet[:, 1] == qem))[0]
            if len(idx) > 0:
                Xy[idx[0], -1] = row["gdp_yoy"]

        # Transform and standardize
        Xy_trans = Xy.copy()
        for j, name in enumerate(MN):
            tcode = DATASETS.get(name, (None, None, 0, None, {}))[2]
            Xy_trans[:, j] = transform_series(Xy[:, j].copy(), tcode, "monthly")
        Xy_trans[:, -1] = Xy[:, -1].copy()  # YoY already in decimal, no transform

        mu_y = np.nanmean(Xy_trans, axis=0)
        sigma_y = np.nanstd(Xy_trans, axis=0)
        sigma_y[sigma_y < 1e-10] = 1.0
        Xy_std = (Xy_trans - mu_y) / sigma_y
        ff_y = np.where(~np.all(np.isnan(Xy_std), axis=1))[0][0]
        Xy_est = Xy_std[ff_y:]

        # Find current quarter index for YoY
        current_q_idx_y = -1
        for i in range(len(datet) - ff_y):
            if datet[ff_y + i, 0] == current_year and datet[ff_y + i, 1] == current_q_end_m:
                current_q_idx_y = i
                break

        # DFM YoY nowcast
        dfm_y = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
        res_y = dfm_y.fit(Xy_est)
        if current_q_idx_y >= 0 and current_q_idx_y < res_y.X_sm.shape[0]:
            yoy_nw = float(res_y.X_sm[current_q_idx_y, -1]) * sigma_y[-1] + mu_y[-1]
            nowcasts["dfm_yoy"] = round(yoy_nw * 100, 2)

        # BVAR YoY nowcast
        try:
            Xy_filled = Xy_est.copy()
            for j in range(Xy_filled.shape[1]):
                col = Xy_filled[:, j]
                valid = np.where(~np.isnan(col))[0]
                if len(valid) < 2:
                    continue
                last_valid = valid[-1]
                # Only interpolate BEFORE the last valid observation (no future leakage)
                for i in range(last_valid):
                    if np.isnan(col[i]):
                        prev_valid = valid[valid < i]
                        next_valid = valid[valid > i]
                        if len(prev_valid) > 0 and len(next_valid) > 0:
                            pv, nv = prev_valid[-1], next_valid[0]
                            col[i] = col[pv] + (col[nv] - col[pv]) * (i - pv) / (nv - pv)
                        elif len(prev_valid) > 0:
                            col[i] = col[prev_valid[-1]]
                Xy_filled[:, j] = col
            bvar_y = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-3, bvar_max_iter=5))
            res_by = bvar_y.fit(Xy_filled, datet[ff_y:])
            if current_q_idx_y >= 0 and current_q_idx_y < res_by.X_sm.shape[0]:
                yoy_nw_bvar = float(res_by.X_sm[current_q_idx_y, -1]) * sigma_y[-1] + mu_y[-1]
                nowcasts["bvar_yoy"] = round(yoy_nw_bvar * 100, 2)
        except Exception:
            pass

        # Ensemble YoY
        yoy_vals = [v for v in [nowcasts.get("dfm_yoy"), nowcasts.get("bvar_yoy")] if v is not None]
        if yoy_vals:
            nowcasts["ensemble_yoy"] = round(np.median(yoy_vals), 2)

    except Exception as e:
        print(f"YoY GDP nowcast failed: {e}")

# Store sector actuals
nowcasts["sector_actuals"] = sector_actuals

# ---------------------------------------------------------------------------
# 3d. GDP Identity Reconciliation: derive imports from C+I+G+X-GDP
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
# 6. Generate markdown leaderboard (DOSM-comparable format)
# -------------------------------------------------------------------
# Determine latest actual quarter
latest_actual_label = backcast_label  # Q1 2026
latest_actual_yoy = actual_yoy_gdp  # +5.4%

md = f"# Malaysia GDP Nowcasting — Live Leaderboard\n\n"
md += f"**Updated:** {today_str} | **Latest actual:** {latest_actual_label} | **Nowcasting:** {nowcast_label}\n\n"

# --- Section 1: Current Nowcast (YoY %) ---
# Show forward-looking nowcast (no ground truth yet)
md += "## GDP Nowcast (YoY %)\n\n"
md += f"*Nowcasting {nowcast_label} — no ground truth available yet (releases ~mid-{(current_quarter*3+2)%12 or 12}).*\n\n"

md += "| Model | Nowcast |\n"
md += "|-------|--------|\n"
for model_name, model_key in [("DFM", "dfm_yoy"), ("BVAR", "bvar_yoy"), ("ENSEMBLE", "ensemble_yoy")]:
    val = nowcasts.get(model_key)
    val_str = f"`{val:+.1f}%`" if val is not None else "—"
    md += f"| {model_name} | {val_str} |\n"

# --- Section 2: Backcast Accuracy (vs latest actual) ---
# Show how well models estimated the latest known quarter
md += f"\n## Backcast Accuracy ({latest_actual_label}, YoY %)\n\n"
md += f"*How well models estimated {latest_actual_label}. DOSM actual: `{latest_actual_yoy:+.1f}%`.*\n\n"

md += "| Model | Estimate | Error |\n"
md += "|-------|----------|-------|\n"

# Use YoY backcast if available, otherwise approximate from QoQ
for model_name, model_key in [("DFM", "dfm_yoy"), ("BVAR", "bvar_yoy"), ("ENSEMBLE", "ensemble_yoy")]:
    val = nowcasts.get(model_key)
    val_str = f"`{val:+.1f}%`" if val is not None else "—"
    err_str = "—"
    if val is not None and latest_actual_yoy is not None:
        err_val = abs(val - latest_actual_yoy)
        err_str = f"{err_val:.1f}pp"
    md += f"| {model_name} | {val_str} | {err_str} |\n"

# --- Section 3: Economic Sectors (DOSM supply-side) ---
md += "\n## GDP by Economic Sector (YoY %)\n\n"
md += '*Comparable to DOSM "A deeper look at GDP by economic sector". Actual values from `gdp_qtr_real_supply`.*\n\n'

sector_labels = {
    "agriculture": "Agriculture",
    "mining": "Mining & Quarrying",
    "manufacturing": "Manufacturing",
    "construction": "Construction",
    "services": "Services",
}

md += "| Sector | Latest Actual |\n"
md += "|--------|---------------|\n"
for sector_key, sector_name in sector_labels.items():
    act = sector_actuals.get(sector_key)
    act_str = f"`{act:+.1f}%`" if act is not None else "—"
    md += f"| {sector_name} | {act_str} |\n"

if actual_yoy_gdp is not None:
    md += f"| **Overall GDP** | `{actual_yoy_gdp:+.1f}%` |\n"

# --- Section 4: Expenditure Components (DOSM demand-side) ---
md += "\n## GDP by Expenditure Category (YoY %)\n\n"
md += '*Comparable to DOSM "A deeper look at GDP by expenditure category". BVAR primary, DFM comparison.*\n\n'

comp_labels = {
    "consumption": ("Private Consumption", "C"),
    "investment": ("Gross Fixed Capital Formation", "I"),
    "government": ("Government Consumption", "G"),
    "exports_comp": ("Exports", "X"),
    "imports_comp": ("Imports", "M"),
}

md += "| Component | BVAR | DFM | Actual | Error (BVAR) |\n"
md += "|-----------|------|-----|--------|--------------|\n"

for ck, (clabel, ccode) in comp_labels.items():
    bvar_val = nowcasts.get(ck)
    dfm_val = nowcasts.get(ck + "_dfm")
    act_val = nowcasts.get(ck + "_actual")

    bvar_str = f"{bvar_val:+.1f}%" if bvar_val is not None else "—"
    dfm_str = f"{dfm_val:+.1f}%" if dfm_val is not None else "—"
    act_str = f"{act_val:+.1f}%" if act_val is not None else "—"
    err_str = "—"
    if bvar_val is not None and act_val is not None:
        err_val = abs(bvar_val - act_val)
        err_str = f"{err_val:.1f}pp"

    md += f"| **{clabel}** ({ccode}) | {bvar_str} | {dfm_str} | {act_str} | {err_str} |\n"

# --- Section 5: Model Accuracy Leaderboard ---
md += "\n## Model Accuracy (Rolling)\n\n"
md += "*Daily nowcast accuracy vs DOSM actuals. Metrics appear after 3+ days.*\n\n"

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
    md += f"*Requires 3+ daily observations. Currently: {len(log)}.*\n\n"
    md += "| Model | MAE | RMSE | FDA | N | Latest |\n"
    md += "|-------|-----|------|-----|---|--------|\n"
    for model in ["DFM", "BVAR", "BEQ", "AR(1)", "NAIVE", "ENSEMBLE"]:
        col = model.lower()
        val = nowcasts.get(col)
        latest_str = f"{val:+.1f}%" if val is not None else "—"
        style_note = " *(baseline)*" if model == "AR(1)" else " *(last Q)*" if model == "NAIVE" else " *(combined)*" if model == "ENSEMBLE" else ""
        md += f"| {model}{style_note} | — | — | — | {len(log)} | {latest_str} |\n"

# --- Section 6: Recent Nowcasts ---
md += f"\n## Recent Nowcasts ({min(30, len(log))} days)\n\n"
md += "| Date | DFM | BVAR | BEQ | AR(1) | NAIVE | ENSEMBLE | Actual |\n"
md += "|------|-----|------|-----|-------|-------|----------|--------|\n"
for _, row in log.tail(30).iterrows():
    vals = []
    for m in ["dfm", "bvar", "beq", "ar1", "naive", "ensemble"]:
        v = row.get(m)
        vals.append(f"{v:+.1f}%" if pd.notna(v) else "—")
    actual_v = row.get("actual_gdp_pct")
    actual_str = f"{actual_v:+.1f}%" if pd.notna(actual_v) else "—"
    md += f"| {row['date']} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} | {vals[4]} | {vals[5]} | {actual_str} |\n"

# --- Section 7: Data Sources ---
md += "\n## Data Sources\n\n"
md += "- **GDP (YoY):** DOSM `gdp_qtr_real` — non-SA, constant 2015 prices\n"
md += "- **Sectors:** DOSM `gdp_qtr_real_supply` — supply-side breakdown\n"
md += "- **Expenditure:** DOSM `gdp_qtr_real_demand` — demand-side breakdown\n"
md += "- **Dashboard:** [OpenDOSM GDP](https://open.dosm.gov.my/dashboard/gdp)\n"
md += "- **API:** [OpenDOSM Developer](https://developer.data.gov.my/static-api/opendosm)\n"
md += f"- **Last updated:** {today_str}\n\n"
md += f"---\n*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*\n"
leaderboard_path = Path("docs") / "leaderboard.md"
leaderboard_path.write_text(md, encoding="utf-8")
print(f"[{datetime.now().isoformat()}] Leaderboard written to {leaderboard_path} ({leaderboard_path.stat().st_size} bytes)")

# Generate dashboards
import subprocess
for script in ["generate_dashboard.py", "generate_dashboard_md.py"]:
    result = subprocess.run([sys.executable, f"scripts/{script}"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[{datetime.now().isoformat()}] {script} completed")
    else:
        print(f"[{datetime.now().isoformat()}] {script} failed: {result.stderr}")

# ---------------------------------------------------------------------------
# 7. Generate HTML dashboard (DOSM-style)
# ---------------------------------------------------------------------------
dashboard_data = {
    "lastUpdated": today_str,
    "latestActual": {"quarter": backcast_label, "yoy": actual_yoy_gdp},
    "nowcast": {
        "quarter": nowcast_label,
        "dfm": nowcasts.get("dfm_yoy"),
        "bvar": nowcasts.get("bvar_yoy"),
        "ensemble": nowcasts.get("ensemble_yoy"),
    },
    "backcast": {
        "dfm": {"estimate": nowcasts.get("dfm_yoy"), "error": None},
        "bvar": {"estimate": nowcasts.get("bvar_yoy"), "error": None},
        "ensemble": {"estimate": nowcasts.get("ensemble_yoy"), "error": None},
    },
    "components": {
        "consumption": {
            "bvar": nowcasts.get("consumption"),
            "actual": nowcasts.get("consumption_actual"),
            "error": round(abs(nowcasts.get("consumption", 0) - nowcasts.get("consumption_actual", 0)), 1) if nowcasts.get("consumption") and nowcasts.get("consumption_actual") else None,
        },
        "investment": {
            "bvar": nowcasts.get("investment"),
            "actual": nowcasts.get("investment_actual"),
            "error": round(abs(nowcasts.get("investment", 0) - nowcasts.get("investment_actual", 0)), 1) if nowcasts.get("investment") and nowcasts.get("investment_actual") else None,
        },
        "government": {
            "bvar": nowcasts.get("government"),
            "actual": nowcasts.get("government_actual"),
            "error": round(abs(nowcasts.get("government", 0) - nowcasts.get("government_actual", 0)), 1) if nowcasts.get("government") and nowcasts.get("government_actual") else None,
        },
        "exports": {
            "bvar": nowcasts.get("exports_comp"),
            "actual": nowcasts.get("exports_comp_actual"),
            "error": round(abs(nowcasts.get("exports_comp", 0) - nowcasts.get("exports_comp_actual", 0)), 1) if nowcasts.get("exports_comp") and nowcasts.get("exports_comp_actual") else None,
        },
        "imports": {
            "bvar": nowcasts.get("imports_comp"),
            "actual": nowcasts.get("imports_comp_actual"),
            "error": round(abs(nowcasts.get("imports_comp", 0) - nowcasts.get("imports_comp_actual", 0)), 1) if nowcasts.get("imports_comp") and nowcasts.get("imports_comp_actual") else None,
        },
    },
    "sectors": sector_actuals,
    "leaderboard": [],
    "recent": [],
}

# Compute backcast errors
if actual_yoy_gdp is not None:
    for model_key in ["dfm", "bvar", "ensemble"]:
        est = dashboard_data["backcast"][model_key]["estimate"]
        if est is not None:
            dashboard_data["backcast"][model_key]["error"] = round(abs(est - actual_yoy_gdp), 1)

# Build leaderboard rows
if len(log) >= 3:
    for model in ["dfm", "bvar", "beq", "ensemble"]:
        if model not in log.columns:
            continue
        sub = log[[model, "actual_gdp_pct"]].dropna()
        if len(sub) < 3:
            continue
        pred = sub[model].values
        act = sub["actual_gdp_pct"].values
        dashboard_data["leaderboard"].append({
            "model": model.upper(),
            "mae": round(compute_mae(act, pred), 3),
            "rmse": round(compute_rmse(act, pred), 3),
            "fda": round(compute_fda(act, pred) * 100, 1),
            "n": len(sub),
            "latest": round(float(nowcasts.get(model, 0)), 1),
        })

# Build recent rows
for _, row in log.tail(30).iterrows():
    recent_row = {"date": row["date"]}
    for m in ["dfm", "bvar", "beq", "ensemble"]:
        v = row.get(m)
        recent_row[m] = round(float(v), 1) if pd.notna(v) else None
    actual_v = row.get("actual_gdp_pct")
    recent_row["actual"] = round(float(actual_v), 1) if pd.notna(actual_v) else None
    dashboard_data["recent"].append(recent_row)

# Inject data into HTML template
dashboard_html_path = Path("docs") / "dashboard.html"
if dashboard_html_path.exists():
    html_template = dashboard_html_path.read_text(encoding="utf-8")
    
    # Replace the data object in the script
    data_json = json.dumps(dashboard_data, indent=2)
    html_new = html_template.replace(
        "const data = {",
        f"const data = {data_json};\n        // Original template below\n        const data_old = {{"
    )
    
    dashboard_html_path.write_text(html_new, encoding="utf-8")
    print(f"[{datetime.now().isoformat()}] Dashboard written to {dashboard_html_path}")

print(f"[{datetime.now().isoformat()}] Daily update complete.")
print(json.dumps(nowcasts, indent=2))

except Exception as e:
    logger.error("Daily update failed: %s", e)
    logger.error(traceback.format_exc())
    sys.exit(1)
