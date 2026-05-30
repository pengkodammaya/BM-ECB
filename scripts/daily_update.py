"""Daily update: fetch live data, run all 3 models, append to history, update leaderboard.

Runs in GitHub Actions on schedule. No local cache needed — fetches fresh each time.

Corrected version: hardened network fetches, atomic CSV writes, guarded reads,
fixed dashboard injection, fixed GDP-identity basis mismatch and ensemble
normalisation, leak-free O(n) interpolation, and NaN-safe standardisation.
"""
import sys; sys.path.insert(0, "src")

import re
import json
import warnings
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
except ImportError as e:
    logger.error("Failed to import nowcasting_toolbox: %s", e)
    sys.exit(1)


# ---------------------------------------------------------------------------
# 0. Helpers (hardened I/O)
# ---------------------------------------------------------------------------
def safe_fetch(dataset_id, limit=20000):
    """Fetch an OpenDOSM dataset, returning an empty DataFrame on ANY failure.

    Wraps both the client construction and the network call so an exception
    (timeout, connection reset, 5xx, JSON decode error) never kills the run.
    Always closes the client, even on error.
    """
    client = None
    try:
        client = OpenDOSMClient()
        df = client.fetch(dataset_id, limit=limit)
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", dataset_id, e)
        return pd.DataFrame()
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def safe_read_csv(path):
    """Read a CSV, returning None if missing or corrupt (never raises)."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception as e:
        logger.warning("Could not read %s (corrupt?): %s", path, e)
        return None


def atomic_write_csv(df, path):
    """Write a CSV atomically: write to a temp file then rename.

    Prevents a crash mid-write from leaving a truncated file that breaks
    every subsequent run.
    """
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)


def interpolate_no_leak(col):
    """Linear-interpolate interior NaNs only — never fill past the last valid obs.

    O(n) replacement for the original nested-loop interpolation. Leading NaNs
    (before the first observation) and trailing NaNs (after the last observation)
    are left as NaN, so no future information leaks into the estimation window.
    """
    s = pd.Series(np.asarray(col, dtype="float64"))
    valid_idx = np.where(s.notna().values)[0]
    if len(valid_idx) < 2:
        return s.values
    last_valid = int(valid_idx[-1])
    s.iloc[: last_valid + 1] = (
        s.iloc[: last_valid + 1].interpolate(method="linear", limit_direction="forward")
    )
    return s.values


def standardize(arr):
    """NaN-safe standardisation. All-NaN columns collapse to mu=0, sigma=1
    instead of producing NaN-filled columns that destabilise the models.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        mu = np.nanmean(arr, axis=0)
        sigma = np.nanstd(arr, axis=0)
    mu = np.nan_to_num(mu, nan=0.0)
    sigma = np.nan_to_num(sigma, nan=1.0)
    sigma[sigma < 1e-10] = 1.0
    return (arr - mu) / sigma, mu, sigma


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
# 2. Fetch data (parallel)
# ---------------------------------------------------------------------------
logger.info("Daily update starting...")

cache = DataCache(ttl_hours=6)
filtered = {}

def fetch_single_dataset(args):
    """Fetch a single dataset (for parallel execution)."""
    name, (did, col, tcode, group, filters) = args
    try:
        df = cache.get(did)
        if df is None:
            # Create a new client for each call to avoid thread-safety issues
            local_client = OpenDOSMClient()
            try:
                df = local_client.fetch(did, limit=20000)
            finally:
                local_client.close()
            if df is not None and not df.empty:
                cache.put(did, df)
        if df is None or df.empty:
            return name, None
        df = df.copy()
        for fc, fv in filters.items():
            if fc in df.columns:
                df = df[df[fc] == fv]
        if col not in df.columns:
            return name, None
        df = df[["date", col]].dropna().rename(columns={col: name})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates("date")
        return name, df
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", name, e)
        return name, None

# Fetch OpenDOSM data in parallel
from concurrent.futures import ThreadPoolExecutor, as_completed

logger.info("Fetching %d datasets in parallel...", len(DATASETS))
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(fetch_single_dataset, item): item[0]
               for item in DATASETS.items()}
    for future in as_completed(futures):
        name, df = future.result()
        if df is not None:
            filtered[name] = df

# % to decimal
for var in ["ipi", "imports_capital", "imports_consumer"]:
    if var in filtered:
        filtered[var][var] = filtered[var][var] / 100.0

# BNM data (sequential - rate limited)
try:
    ir_df = fetch_interest_rate_history(start_year=2024, verbose=False)
    if not ir_df.empty:
        ir_df = ir_df.rename(columns={"value": "interbank"})
        filtered["interbank"] = ir_df[["date", "interbank"]]
except Exception as e:
    logger.warning("BNM interest rate failed (non-fatal): %s", e)
try:
    fx_df = fetch_exchange_rate_history(start_year=2024, currency_code="USD", verbose=False)
    if not fx_df.empty:
        fx_vals = fx_df["value"].values
        fx_growth = np.full(len(fx_vals), np.nan)
        for i in range(1, len(fx_vals)):
            if fx_vals[i-1] > 0:
                fx_growth[i] = np.log(fx_vals[i]) - np.log(fx_vals[i-1])
        fx_df["fx_usd"] = fx_growth
        fx_df = fx_df.dropna(subset=["fx_usd"])
        filtered["fx_usd"] = fx_df[["date", "fx_usd"]]
except Exception as e:
    logger.warning("BNM exchange rate failed (non-fatal): %s", e)

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

# Import yfinance once, outside the loop
try:
    import yfinance as yf
except Exception as e:
    yf = None
    logger.warning("yfinance unavailable: %s", e)

if yf is not None:
    for label, (ticker, group) in GLOBAL_INDICATORS.items():
        try:
            data = yf.download(ticker, start="2015-01-01", progress=False)
            if data is None or len(data) == 0:
                logger.info("yfinance %s: no data", label)
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
            df_out = pd.DataFrame({"date": monthly.index, label: growth}).dropna()
            filtered[label] = df_out
            DATASETS[label] = (label, label, 0, group, {})  # transform 0 = already growth
            logger.info("yfinance %s: %d monthly obs", label, len(df_out))
        except Exception as e:
            logger.warning("yfinance %s failed: %s", label, e)

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
            df_fred = df_fred.set_index("date").resample("ME").last().dropna().reset_index()
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
            logger.info("FRED %s: %d monthly obs", label, len(df_fred))
        except Exception as e:
            logger.warning("FRED %s failed: %s", label, e)

# ---------------------------------------------------------------------------
# 1.8 SITC trade sections
# ---------------------------------------------------------------------------
sitc_df = safe_fetch("trade_sitc_1d")
if not sitc_df.empty:
    for section, label in [("overall", "sitc_total"), ("7", "sitc_machinery")]:
        try:
            sub = sitc_df[(sitc_df["section"] == section)].copy()
            if len(sub) > 0:
                sub = sub[["date", "exports"]].dropna().rename(columns={"exports": label})
                sub["date"] = pd.to_datetime(sub["date"])
                sub = sub.sort_values("date").drop_duplicates("date")
                filtered[label] = sub
                DATASETS[label] = (label, label, 1, "external", {})  # dlog transform
        except Exception as e:
            logger.warning("SITC %s failed: %s", label, e)

# ---------------------------------------------------------------------------
# FATAL GUARD: GDP target is required to proceed
# ---------------------------------------------------------------------------
if "gdp" not in filtered or filtered["gdp"].empty:
    logger.error("GDP target fetch failed — cannot run nowcasts. Aborting.")
    sys.exit(1)

# Define component-specific indicator subsets
COMPONENT_INDICATORS = {
    "consumption": [n for n in DATASETS if n != "gdp"],
    "investment":  [n for n in DATASETS if DATASETS[n][3] in ("industry", "financial", "leading", "external") and n != "gdp"],
    "government":  [n for n in DATASETS if DATASETS[n][3] in ("labour", "financial") and n != "gdp"],
    "exports_comp":[n for n in DATASETS if DATASETS[n][3] in ("external", "financial", "industry", "global_equity", "global_commodity", "global_demand") and n != "gdp"],
    "imports_comp":[n for n in DATASETS if DATASETS[n][3] in ("external", "services", "prices", "global_commodity") and n != "gdp"],
}

# Sector-specific indicator subsets (supply-side)
SECTOR_INDICATORS = {
    "agriculture": [n for n in DATASETS if DATASETS[n][3] in ("industry", "prices", "leading", "external") and n != "gdp"],
    "mining": [n for n in DATASETS if DATASETS[n][3] in ("industry", "prices", "external") and n != "gdp"],
    "manufacturing": [n for n in DATASETS if DATASETS[n][3] in ("industry", "prices", "leading", "external", "global_equity") and n != "gdp"],
    "construction": [n for n in DATASETS if DATASETS[n][3] in ("industry", "leading", "financial") and n != "gdp"],
    "services": [n for n in DATASETS if DATASETS[n][3] in ("industry", "services", "coincident", "labour") and n != "gdp"],
}
# Fallback: if a subset is too small (<3 indicators), use all
for ck, indicators in COMPONENT_INDICATORS.items():
    if len(indicators) < 3:
        COMPONENT_INDICATORS[ck] = [n for n in DATASETS if n != "gdp"]

# Use optimized hyperparameters for each component
COMPONENT_PARAMS = {
    "consumption": (2, 4),
    "investment":  (3, 2),
    "government":  (2, 2),
    "exports_comp":(3, 2),
    "imports_comp":(3, 2),
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

X_std, mu, sigma = standardize(X_trans)

# Guard: at least one non-empty row must exist
non_empty_rows = np.where(~np.all(np.isnan(X_std), axis=1))[0]
if len(non_empty_rows) == 0:
    logger.error("No usable observations after transform/standardise. Aborting.")
    sys.exit(1)
ff = non_empty_rows[0]
X_est = X_std[ff:]

# ---------------------------------------------------------------------------
# 3. Run all 3 models — produce nowcasts at 3 horizons
# ---------------------------------------------------------------------------
nowcasts = {}
today_str = date.today().isoformat()

today_dt = date.today()
current_quarter = (today_dt.month - 1) // 3 + 1
current_year = today_dt.year

# Find the last row with actual GDP (index into X_est)
if np.any(~np.isnan(X_est[:, -1])):
    last_actual_idx = int(np.where(~np.isnan(X_est[:, -1]))[0][-1])
else:
    last_actual_idx = len(X_est) - 1

# Current quarter end month in the grid (the quarter we're NOWCASTING)
current_q_end_m = current_quarter * 3
current_q_idx = -1
for i in range(len(datet) - ff):
    if datet[ff + i, 0] == current_year and datet[ff + i, 1] == current_q_end_m:
        current_q_idx = i
        break

# Next quarter end month (1-quarter-ahead forecast)
next_q_end_m = current_q_end_m + 3
next_q_year = current_year + (1 if next_q_end_m > 12 else 0)
next_q_end_m = ((next_q_end_m - 1) % 12) + 1
next_q_idx = -1
for i in range(len(datet) - ff):
    if datet[ff + i, 0] == next_q_year and datet[ff + i, 1] == next_q_end_m:
        next_q_idx = i
        break

# Warn if the quarter we want to nowcast isn't in the grid (stale data)
if current_q_idx < 0:
    logger.warning("Current quarter (Q%d %d) not in grid — data may be stale.",
                   current_quarter, current_year)

# Label quarters
backcast_label = f"Q{((datet[ff + last_actual_idx, 1]) // 3)} {int(datet[ff + last_actual_idx, 0])}"
nowcast_label = f"Q{current_quarter} {current_year}" if current_q_idx >= 0 else "N/A"
forecast_label = f"Q{next_q_end_m // 3} {next_q_year}" if next_q_idx >= 0 else "N/A"


def _extract(res, idx, sigma_arr, mu_arr, gdp_col=-1):
    if idx is not None and idx >= 0 and idx < res.X_sm.shape[0]:
        return round((float(res.X_sm[idx, gdp_col]) * sigma_arr[gdp_col] + mu_arr[gdp_col]) * 100, 2)
    return None


# DFM
try:
    dfm = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
    res = dfm.fit(X_est)
    nowcasts["dfm"] = _extract(res, current_q_idx, sigma, mu)
    nowcasts["dfm_backcast"] = _extract(res, last_actual_idx, sigma, mu)
    nowcasts["dfm_forecast"] = _extract(res, next_q_idx, sigma, mu)
except Exception as e:
    logger.warning("DFM failed: %s", e)
    nowcasts["dfm"] = None

# BVAR
try:
    X_filled = X_est.copy()
    for j in range(X_filled.shape[1]):
        X_filled[:, j] = interpolate_no_leak(X_filled[:, j])
    # MASK backcast quarter for true out-of-sample forecast
    X_bvar = X_filled.copy()
    if 0 <= last_actual_idx < X_bvar.shape[0]:
        X_bvar[last_actual_idx, -1] = np.nan
    bvar = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-5, bvar_max_iter=10, bvar_n_draws=50, bvar_burn_in=15))
    res_b = bvar.fit(X_bvar, datet[ff:])
    nowcasts["bvar"] = _extract(res_b, current_q_idx, sigma, mu)
    nowcasts["bvar_backcast"] = _extract(res_b, last_actual_idx, sigma, mu)
    nowcasts["bvar_forecast"] = _extract(res_b, next_q_idx, sigma, mu)

    # Fan chart from BVAR posterior draws
    if res_b.B_draws is not None and res_b.Sigma_draws is not None and current_q_idx >= 0:
        from nowcasting_toolbox.fan_chart import bvar_fan_chart
        lags = 3
        N = X_filled.shape[1]
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
    logger.warning("BVAR failed: %s", e)
    nowcasts["bvar"] = None

# BEQ
try:
    X_raw_beq = X_trans[ff:]
    beq = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
    res_e = beq.fit(X_raw_beq, datet[ff:], AN)
    gdp_col = -1
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
    logger.warning("BEQ failed: %s", e)
    nowcasts["beq"] = nowcasts["beq_backcast"] = nowcasts["beq_forecast"] = None

# Weighted ensemble (inverse MAE² weighting, falls back to median)
log_ens = safe_read_csv("docs/daily_log.csv")
ensemble_models = ["dfm", "bvar", "beq"]
weights = {}
if log_ens is not None and len(log_ens) >= 3:
    for m in ensemble_models:
        if m in log_ens.columns:
            sub = log_ens[[m, "actual_gdp_pct"]].dropna()
            if len(sub) >= 3:
                act_vals = pd.to_numeric(sub["actual_gdp_pct"], errors="coerce").values
                pred_vals = pd.to_numeric(sub[m], errors="coerce").values
                valid = ~np.isnan(act_vals) & ~np.isnan(pred_vals)
                if np.sum(valid) >= 3:
                    mae = compute_mae(act_vals[valid], pred_vals[valid])
                    weights[m] = 1.0 / (mae ** 2 + 0.01)

# Only normalise over models that have BOTH a weight and a current nowcast.
valid_ens = [m for m in ensemble_models
             if nowcasts.get(m) is not None and m in weights]
if valid_ens:
    total_w = sum(weights[m] for m in valid_ens)
    nowcasts["ensemble"] = (
        round(sum(nowcasts[m] * weights[m] / total_w for m in valid_ens), 2)
        if total_w > 0 else None
    )
else:
    vals = [nowcasts.get(m) for m in ensemble_models if nowcasts.get(m) is not None]
    nowcasts["ensemble"] = round(float(np.median(vals)), 2) if vals else None

# ---------------------------------------------------------------------------
# 3.5 AR(1) benchmark
# ---------------------------------------------------------------------------
try:
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
            ar_pct = (ar_std * sigma[-1] + mu[-1]) * 100
            nowcasts["ar1"] = round(ar_pct, 2)
except Exception as e:
    logger.warning("AR(1) failed: %s", e)
    nowcasts["ar1"] = None

# ---------------------------------------------------------------------------
# 3.6 DOSM Advance Estimate lookup
# ---------------------------------------------------------------------------
dosm_advance = None
adv_df = safe_read_csv("data/malaysia/dosm_advance_estimates.csv")
if adv_df is not None:
    try:
        adv_row = adv_df[adv_df["quarter"] == f"{current_year}-Q{current_quarter}"]
        if len(adv_row) > 0:
            dosm_advance = adv_row.iloc[0]
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 3a. Fetch YoY GDP and sector data for DOSM-comparable metrics
# ---------------------------------------------------------------------------
df_gdp_yoy = safe_fetch("gdp_qtr_real")
actual_yoy_gdp = None
if not df_gdp_yoy.empty:
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
df_supply = safe_fetch("gdp_qtr_real_supply")
if not df_supply.empty:
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

# ---------------------------------------------------------------------------
# 3b. Component-level nowcasts: C, I, G, X, M with GDP identity reconciliation
# ---------------------------------------------------------------------------
df_demand = safe_fetch("gdp_qtr_real_demand")

COMPONENTS = [
    ("consumption", "e1", "growth_yoy"),
    ("investment",  "e3", "growth_yoy"),
    ("government",  "e2", "growth_yoy"),
    ("exports_comp","e5", "growth_yoy"),
    ("imports_comp","e6", "growth_yoy"),
]

comp_levels = {}
comp_levels_yoy = {}

if df_demand.empty:
    logger.warning("df_demand fetch failed — skipping all component nowcasts.")
else:
    # Extract absolute levels and actual YoY
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

    # Run component-level nowcasts using targeted indicator subsets
    for comp_key, comp_type, comp_series in COMPONENTS:
        try:
            target_indicators = COMPONENT_INDICATORS.get(comp_key, MN)
            target_names = [n for n in target_indicators if n in filtered]
            n_comp = len(target_names)

            comp_val = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == comp_series)].copy()
            if len(comp_val) == 0:
                continue
            comp_val = comp_val[["date", "value"]].rename(columns={"value": "target"})
            comp_val["date"] = pd.to_datetime(comp_val["date"])
            comp_val = comp_val.sort_values("date").dropna()
            comp_val["target"] = comp_val["target"] / 100.0

            Xc = np.full((T, n_comp + 1), np.nan)
            for j, name in enumerate(target_names):
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
                    # MASK current AND backcast quarter — true out-of-sample
                    if (y == current_year and qem == current_q_end_m) or \
                       (y == int(datet[ff + last_actual_idx, 0]) and qem == int(datet[ff + last_actual_idx, 1])):
                        continue
                    Xc[idx[0], -1] = row["target"]

            Xc_trans = Xc.copy()
            for j, name in enumerate(target_names):
                tcode = DATASETS.get(name, (None, None, 0, None, {}))[2]
                Xc_trans[:, j] = transform_series(Xc[:, j].copy(), tcode, "monthly")
            Xc_trans[:, -1] = Xc[:, -1].copy()

            Xc_std, muc, sigmac = standardize(Xc_trans)
            non_empty_c = np.where(~np.all(np.isnan(Xc_std), axis=1))[0]
            if len(non_empty_c) == 0:
                continue
            ffc = non_empty_c[0]
            Xc_est = Xc_std[ffc:]

            if np.sum(~np.isnan(Xc_est[:, -1])) < 5:
                continue

            cr, cp = COMPONENT_PARAMS.get(comp_key, (3, 2))
            dfm_c = DFM(DFMParams(r=cr, p=cp, max_iter=30, thresh=1e-5, idio=1))
            res_c = dfm_c.fit(Xc_est)
            nwc = float(res_c.X_sm[-1, -1]) * sigmac[-1] + muc[-1]
            nowcasts[comp_key + "_dfm"] = round(nwc * 100, 2)

            # --- BVAR for component (PRIMARY) ---
            try:
                Xc_filled = Xc_est.copy()
                for j in range(Xc_filled.shape[1]):
                    Xc_filled[:, j] = interpolate_no_leak(Xc_filled[:, j])
                bvar_c = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-3, bvar_max_iter=5))
                res_bc = bvar_c.fit(Xc_filled, datet[ffc:])
                nwb = float(res_bc.X_sm[-1, -1]) * sigmac[-1] + muc[-1]
                nowcasts[comp_key] = round(nwb * 100, 2)
            except Exception as e:
                logger.warning("Component BVAR %s failed: %s", comp_key, e)
                nowcasts[comp_key] = nowcasts.get(comp_key + "_dfm")

            # --- BEQ for component ---
            try:
                beq_c = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
                res_e = beq_c.fit(Xc_trans, datet[ffc:], target_names)
                if res_e.X_sm is not None and res_e.X_sm.shape[0] > 0:
                    q_end_idx = -1
                    for t in range(len(datet[ffc:])):
                        if datet[ffc + t, 0] == current_year and datet[ffc + t, 1] == current_q_end_m:
                            q_end_idx = t
                            break
                    if 0 <= q_end_idx < res_e.X_sm.shape[0]:
                        nw_e = float(res_e.X_sm[q_end_idx, -1])
                        nowcasts[comp_key + "_beq"] = round(nw_e * 100, 2) if not np.isnan(nw_e) else None
                    else:
                        nowcasts[comp_key + "_beq"] = None
                else:
                    nowcasts[comp_key + "_beq"] = None
            except Exception as e:
                logger.warning("Component BEQ %s failed: %s", comp_key, e)
                nowcasts[comp_key + "_beq"] = None
        except Exception as e:
            logger.warning("Component %s: %s", comp_key, e)
            nowcasts[comp_key] = None

# ---------------------------------------------------------------------------
# 3b2. Sector-level nowcasts
# ---------------------------------------------------------------------------
logger.info("Running sector nowcasts...")
df_sector_gdp = safe_fetch("gdp_qtr_real_supply")

for sector_code, sector_name in SECTOR_MAP.items():
    try:
        if df_sector_gdp.empty:
            nowcasts[f"sector_{sector_name}"] = None
            continue

        sector_rows = df_sector_gdp[
            (df_sector_gdp["sector"] == sector_code) & (df_sector_gdp["series"] == "growth_yoy")
        ].copy()
        if sector_rows.empty:
            nowcasts[f"sector_{sector_name}"] = None
            continue

        sector_rows["date"] = pd.to_datetime(sector_rows["date"])
        sector_rows = sector_rows.sort_values("date")
        sector_gdp_vals = sector_rows["value"].values / 100.0
        sector_gdp_dates = sector_rows["date"].values

        X_sector_target = np.full(T, np.nan)
        for i, d in enumerate(sector_gdp_dates):
            dt = pd.Timestamp(d)
            y, m = dt.year, dt.month
            qem = ((m - 1) // 3) * 3 + 3
            idx = np.where((datet[:, 0] == y) & (datet[:, 1] == qem))[0]
            if len(idx) > 0 and i < len(sector_gdp_vals):
                X_sector_target[idx[0]] = sector_gdp_vals[i]

        sector_indicators = SECTOR_INDICATORS.get(sector_name, [])
        if len(sector_indicators) < 3:
            sector_indicators = [n for n in DATASETS if n != "gdp"]

        valid_sector_indicators = [n for n in sector_indicators if n in filtered]
        n_sector_m = len(valid_sector_indicators)
        if n_sector_m < 2:
            nowcasts[f"sector_{sector_name}"] = None
            continue

        X_sector = np.full((T, n_sector_m + 1), np.nan)
        for j, name in enumerate(valid_sector_indicators):
            df = filtered[name]
            for _, row in df.iterrows():
                y, m = row["date"].year, row["date"].month
                idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
                if len(idx) > 0:
                    X_sector[idx[0], j] = row[name]
        X_sector[:, -1] = X_sector_target

        X_sector_trans = X_sector.copy()
        for j, name in enumerate(valid_sector_indicators):
            tcode = DATASETS.get(name, (None, None, 0, None, {}))[2]
            X_sector_trans[:, j] = transform_series(X_sector[:, j].copy(), tcode, "monthly")
        X_sector_trans[:, -1] = X_sector[:, -1].copy()

        X_sector_std, mu_s, sigma_s = standardize(X_sector_trans)
        non_empty_s = np.where(~np.all(np.isnan(X_sector_std), axis=1))[0]
        if len(non_empty_s) == 0:
            nowcasts[f"sector_{sector_name}"] = None
            continue
        ffs = non_empty_s[0]
        X_sector_est = X_sector_std[ffs:]

        if np.sum(~np.isnan(X_sector_est[:, -1])) < 3:
            nowcasts[f"sector_{sector_name}"] = None
            continue

        try:
            dfm_s = DFM(DFMParams(r=2, p=1, max_iter=15, thresh=1e-4, idio=1))
            res_s = dfm_s.fit(X_sector_est)
            sector_q_idx = -1
            for i in range(len(datet) - ffs):
                if datet[ffs + i, 0] == current_year and datet[ffs + i, 1] == current_q_end_m:
                    sector_q_idx = i
                    break
            if 0 <= sector_q_idx < res_s.X_sm.shape[0]:
                nws = float(res_s.X_sm[sector_q_idx, -1]) * sigma_s[-1] + mu_s[-1]
            else:
                nws = float(res_s.X_sm[-1, -1]) * sigma_s[-1] + mu_s[-1]
            nowcasts[f"sector_{sector_name}"] = round(nws * 100, 2)
        except Exception:
            nowcasts[f"sector_{sector_name}"] = None
    except Exception as e:
        logger.warning("Sector %s: %s", sector_name, e)
        nowcasts[f"sector_{sector_name}"] = None

# ---------------------------------------------------------------------------
# 3c. YoY GDP Nowcast (DOSM-comparable metric)
# ---------------------------------------------------------------------------
if not df_gdp_yoy.empty:
    try:
        yoy_rows = df_gdp_yoy[df_gdp_yoy["series"] == "growth_yoy"].copy()
        yoy_rows["date"] = pd.to_datetime(yoy_rows["date"])
        yoy_rows = yoy_rows.sort_values("date")
        yoy_rows["gdp_yoy"] = yoy_rows["value"] / 100.0

        Xy = np.full((T, nM + 1), np.nan)
        for j, name in enumerate(MN):
            if name in filtered:
                df = filtered[name]
                for _, row in df.iterrows():
                    y, m = row["date"].year, row["date"].month
                    idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
                    if len(idx) > 0:
                        Xy[idx[0], j] = row[name]
        for _, row in yoy_rows.iterrows():
            y, m = row["date"].year, row["date"].month
            qem = ((m - 1) // 3) * 3 + 3
            idx = np.where((datet[:, 0] == y) & (datet[:, 1] == qem))[0]
            if len(idx) > 0:
                Xy[idx[0], -1] = row["gdp_yoy"]

        Xy_trans = Xy.copy()
        for j, name in enumerate(MN):
            tcode = DATASETS.get(name, (None, None, 0, None, {}))[2]
            Xy_trans[:, j] = transform_series(Xy[:, j].copy(), tcode, "monthly")
        Xy_trans[:, -1] = Xy[:, -1].copy()

        Xy_std, mu_y, sigma_y = standardize(Xy_trans)
        non_empty_y = np.where(~np.all(np.isnan(Xy_std), axis=1))[0]
        if len(non_empty_y) > 0:
            ff_y = non_empty_y[0]
            Xy_est = Xy_std[ff_y:]

            current_q_idx_y = -1
            for i in range(len(datet) - ff_y):
                if datet[ff_y + i, 0] == current_year and datet[ff_y + i, 1] == current_q_end_m:
                    current_q_idx_y = i
                    break

            dfm_y = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
            res_y = dfm_y.fit(Xy_est)
            if 0 <= current_q_idx_y < res_y.X_sm.shape[0]:
                yoy_nw = float(res_y.X_sm[current_q_idx_y, -1]) * sigma_y[-1] + mu_y[-1]
                nowcasts["dfm_yoy"] = round(yoy_nw * 100, 2)

            try:
                Xy_filled = Xy_est.copy()
                for j in range(Xy_filled.shape[1]):
                    Xy_filled[:, j] = interpolate_no_leak(Xy_filled[:, j])
                bvar_y = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-3, bvar_max_iter=5))
                res_by = bvar_y.fit(Xy_filled, datet[ff_y:])
                if 0 <= current_q_idx_y < res_by.X_sm.shape[0]:
                    yoy_nw_bvar = float(res_by.X_sm[current_q_idx_y, -1]) * sigma_y[-1] + mu_y[-1]
                    nowcasts["bvar_yoy"] = round(yoy_nw_bvar * 100, 2)
            except Exception as e:
                logger.warning("YoY BVAR failed: %s", e)

            yoy_vals = [v for v in [nowcasts.get("dfm_yoy"), nowcasts.get("bvar_yoy")] if v is not None]
            if yoy_vals:
                nowcasts["ensemble_yoy"] = round(float(np.median(yoy_vals)), 2)
    except Exception as e:
        logger.warning("YoY GDP nowcast failed: %s", e)

# Store sector actuals as JSON (avoids dict-repr leaking into CSV cells)
nowcasts["sector_actuals"] = json.dumps(sector_actuals)

# ---------------------------------------------------------------------------
# 3d. GDP Identity Reconciliation: derive imports from C+I+G+X-GDP
# ---------------------------------------------------------------------------
# All growth rates MUST be on the same basis. Components are YoY, so GDP must
# also be YoY here — use dfm_yoy, NOT the QoQ-SA dfm nowcast.
try:
    c_level = comp_levels.get("consumption", 0)
    i_level = comp_levels.get("investment", 0)
    g_level = comp_levels.get("government", 0)
    x_level = comp_levels.get("exports_comp", 0)
    m_level_abs = abs(comp_levels.get("imports_comp", 0)) or 1.0  # never 0

    c_growth = nowcasts.get("consumption")
    i_growth = nowcasts.get("investment")
    g_growth = nowcasts.get("government")
    x_growth = nowcasts.get("exports_comp")
    gdp_growth = nowcasts.get("dfm_yoy")  # YoY basis to match components

    required = [c_growth, i_growth, g_growth, x_growth, gdp_growth,
                c_level, i_level, g_level, x_level]
    if all(v is not None for v in required):
        c_g, i_g, g_g, x_g, gdp_g = (c_growth/100, i_growth/100, g_growth/100,
                                     x_growth/100, gdp_growth/100)
        m_g = (c_level*c_g + i_level*i_g + g_level*g_g + x_level*x_g
               - (c_level + i_level + g_level + x_level - m_level_abs) * gdp_g) / m_level_abs
        nowcasts["imports_identity"] = round(m_g * 100, 2)
    else:
        nowcasts["imports_identity"] = None
except Exception as e:
    logger.warning("GDP identity derivation failed: %s", e)
    nowcasts["imports_identity"] = None

# Actual YoY growth for components
for ck in ["consumption", "investment", "government", "exports_comp", "imports_comp"]:
    nowcasts[ck + "_actual"] = comp_levels_yoy.get(ck)

# ---------------------------------------------------------------------------
# 3.7 Component AR(1) benchmarks
# ---------------------------------------------------------------------------
COMP_AR1 = {}
if not df_demand.empty:
    for comp_key, comp_type, _ in COMPONENTS:
        try:
            comp_yoy = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == "growth_yoy")].copy()
            if len(comp_yoy) < 5:
                continue
            comp_yoy["date"] = pd.to_datetime(comp_yoy["date"])
            comp_yoy = comp_yoy.sort_values("date")
            y_vals = comp_yoy["value"].values
            y_lag = y_vals[:-1]
            y_curr = y_vals[1:]
            valid = ~np.isnan(y_lag) & ~np.isnan(y_curr)
            if np.sum(valid) >= 4:
                X_ar = np.column_stack([np.ones(np.sum(valid)), y_lag[valid]])
                ar_coeffs = np.linalg.lstsq(X_ar, y_curr[valid], rcond=None)[0]
                ar_fc = ar_coeffs[0] + ar_coeffs[1] * y_vals[-1]
                COMP_AR1[comp_key] = round(ar_fc, 2)
        except Exception as e:
            logger.warning("AR(1) %s: %s", comp_key, e)

for ck, val in COMP_AR1.items():
    nowcasts[ck + "_ar1"] = val
for ck in ["consumption", "investment", "government", "exports_comp", "imports_comp"]:
    nowcasts[ck + "_naive"] = comp_levels_yoy.get(ck)

# Latest actual GDP
actual_pct = None
for i in range(len(X_est)-1, -1, -1):
    if not np.isnan(X_est[i, -1]):
        actual_pct = float(X_est[i, -1] * sigma[-1] + mu[-1]) * 100
        break

nowcasts["date"] = today_str
nowcasts["actual_gdp_pct"] = round(actual_pct, 2) if actual_pct is not None else None
nowcasts["naive"] = nowcasts["actual_gdp_pct"]

# ---------------------------------------------------------------------------
# 4. Append to daily log (atomic write, guarded read)
# ---------------------------------------------------------------------------
log_path = Path("docs/daily_log.csv")
log_path.parent.mkdir(parents=True, exist_ok=True)
new_row = pd.DataFrame([nowcasts])
existing = safe_read_csv(log_path)
if existing is not None:
    log = pd.concat([existing, new_row], ignore_index=True).drop_duplicates(subset=["date"], keep="last")
else:
    log = new_row
atomic_write_csv(log, log_path)
logger.info("Daily log written to %s (%d rows)", log_path, len(log))

# ---------------------------------------------------------------------------
# 5. Compute rolling leaderboard from daily log
# ---------------------------------------------------------------------------
if len(log) >= 3:
    lb_rows = []
    for model in ["dfm", "bvar", "beq", "ensemble"]:
        if model not in log.columns:
            continue
        sub = log[[model, "actual_gdp_pct"]].dropna()
        if len(sub) < 3:
            continue
        pred = pd.to_numeric(sub[model], errors="coerce").values
        act = pd.to_numeric(sub["actual_gdp_pct"], errors="coerce").values
        valid = ~np.isnan(pred) & ~np.isnan(act)
        pred, act = pred[valid], act[valid]
        if len(pred) < 3:
            continue
        lb_rows.append({
            "model": model.upper(),
            "MAE (pp)": round(compute_mae(act, pred), 3),
            "RMSE (pp)": round(compute_rmse(act, pred), 3),
            "FDA (%)": round(compute_fda(act, pred) * 100, 1),
            "N": len(pred),
            "last_nowcast": nowcasts.get(model),
        })
    if lb_rows:
        atomic_write_csv(pd.DataFrame(lb_rows), Path("docs/leaderboard.csv"))

# -------------------------------------------------------------------
# 6. Generate markdown leaderboard (DOSM-comparable format)
# -------------------------------------------------------------------
latest_actual_label = backcast_label
latest_actual_yoy = actual_yoy_gdp

md_out = "# Malaysia GDP Nowcasting — Live Leaderboard\n\n"
md_out += f"**Updated:** {today_str} | **Latest actual:** {latest_actual_label} | **Nowcasting:** {nowcast_label}\n\n"

md_out += "## GDP Nowcast (YoY %)\n\n"
md_out += f"*Nowcasting {nowcast_label} — no ground truth available yet (releases ~mid-{(current_quarter*3+2)%12 or 12}).*\n\n"
md_out += "| Model | Nowcast |\n|-------|--------|\n"
for model_name, model_key in [("DFM", "dfm_yoy"), ("BVAR", "bvar_yoy"), ("ENSEMBLE", "ensemble_yoy")]:
    val = nowcasts.get(model_key)
    md_out += f"| {model_name} | {f'`{val:+.1f}%`' if val is not None else '—'} |\n"

md_out += f"\n## Backcast Accuracy ({latest_actual_label}, YoY %)\n\n"
if latest_actual_yoy is not None:
    md_out += f"*How well models estimated {latest_actual_label}. DOSM actual: `{latest_actual_yoy:+.1f}%`.*\n\n"
else:
    md_out += f"*How well models estimated {latest_actual_label}. DOSM actual: unavailable.*\n\n"
md_out += "| Model | Estimate | Error |\n|-------|----------|-------|\n"
for model_name, model_key in [("DFM", "dfm_yoy"), ("BVAR", "bvar_yoy"), ("ENSEMBLE", "ensemble_yoy")]:
    val = nowcasts.get(model_key)
    val_str = f"`{val:+.1f}%`" if val is not None else "—"
    err_str = "—"
    if val is not None and latest_actual_yoy is not None:
        err_str = f"{abs(val - latest_actual_yoy):.1f}pp"
    md_out += f"| {model_name} | {val_str} | {err_str} |\n"

md_out += "\n## GDP by Economic Sector (YoY %)\n\n"
md_out += '*Comparable to DOSM "A deeper look at GDP by economic sector". Actual values from `gdp_qtr_real_supply`.*\n\n'
sector_labels = {
    "agriculture": "Agriculture", "mining": "Mining & Quarrying",
    "manufacturing": "Manufacturing", "construction": "Construction", "services": "Services",
}
md_out += "| Sector | Latest Actual |\n|--------|---------------|\n"
for sector_key, sector_name in sector_labels.items():
    act = sector_actuals.get(sector_key)
    md_out += f"| {sector_name} | {f'`{act:+.1f}%`' if act is not None else '—'} |\n"
if actual_yoy_gdp is not None:
    md_out += f"| **Overall GDP** | `{actual_yoy_gdp:+.1f}%` |\n"

md_out += "\n## GDP by Expenditure Category (YoY %)\n\n"
md_out += '*Comparable to DOSM "A deeper look at GDP by expenditure category". BVAR primary, DFM comparison.*\n\n'
comp_labels = {
    "consumption": ("Private Consumption", "C"),
    "investment": ("Gross Fixed Capital Formation", "I"),
    "government": ("Government Consumption", "G"),
    "exports_comp": ("Exports", "X"),
    "imports_comp": ("Imports", "M"),
}
md_out += "| Component | BVAR | DFM | Actual | Error (BVAR) |\n|-----------|------|-----|--------|--------------|\n"
for ck, (clabel, ccode) in comp_labels.items():
    bvar_val = nowcasts.get(ck)
    dfm_val = nowcasts.get(ck + "_dfm")
    act_val = nowcasts.get(ck + "_actual")
    bvar_str = f"{bvar_val:+.1f}%" if bvar_val is not None else "—"
    dfm_str = f"{dfm_val:+.1f}%" if dfm_val is not None else "—"
    act_str = f"{act_val:+.1f}%" if act_val is not None else "—"
    err_str = f"{abs(bvar_val - act_val):.1f}pp" if (bvar_val is not None and act_val is not None) else "—"
    md_out += f"| **{clabel}** ({ccode}) | {bvar_str} | {dfm_str} | {act_str} | {err_str} |\n"

md_out += "\n## Model Accuracy (Rolling)\n\n"
md_out += "*Daily nowcast accuracy vs DOSM actuals. Metrics appear after 3+ days.*\n\n"
if len(log) >= 3:
    lb_rows = []
    for model in ["dfm", "bvar", "beq", "ar1", "naive", "ensemble"]:
        if model not in log.columns:
            continue
        sub = log[[model, "actual_gdp_pct"]].dropna()
        if len(sub) < 3:
            continue
        pred = pd.to_numeric(sub[model], errors="coerce").values
        act = pd.to_numeric(sub["actual_gdp_pct"], errors="coerce").values
        valid = ~np.isnan(pred) & ~np.isnan(act)
        pred, act = pred[valid], act[valid]
        if len(pred) < 3:
            continue
        lb_rows.append({
            "model": model.upper(),
            "MAE (pp)": round(compute_mae(act, pred), 3),
            "RMSE (pp)": round(compute_rmse(act, pred), 3),
            "FDA (%)": round(compute_fda(act, pred) * 100, 1),
            "N": len(pred),
            "last_nowcast": nowcasts.get(model),
        })
    if lb_rows:
        lb_df = pd.DataFrame(lb_rows)
        atomic_write_csv(lb_df, Path("docs/leaderboard.csv"))
        md_out += "| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |\n"
        md_out += "|-------|----------|-----------|---------|---|--------|\n"
        for _, r in lb_df.iterrows():
            latest = r.get("last_nowcast", "—")
            latest_str = f"{latest:+.1f}%" if isinstance(latest, (int, float)) else "—"
            note = {"AR1": " *(baseline)*", "NAIVE": " *(last Q)*",
                    "ENSEMBLE": " *(combined)*"}.get(r["model"], "")
            md_out += f"| {r['model']}{note} | {r['MAE (pp)']:.3f} | {r['RMSE (pp)']:.3f} | {r['FDA (%)']:.1f}% | {int(r['N'])} | {latest_str} |\n"
    else:
        md_out += f"*Requires 3+ daily observations. Currently: {len(log)}.*\n\n"
else:
    md_out += f"*Requires 3+ daily observations. Currently: {len(log)}.*\n\n"
    md_out += "| Model | MAE | RMSE | FDA | N | Latest |\n|-------|-----|------|-----|---|--------|\n"
    for model in ["DFM", "BVAR", "BEQ", "AR1", "NAIVE", "ENSEMBLE"]:
        val = nowcasts.get(model.lower())
        latest_str = f"{val:+.1f}%" if val is not None else "—"
        note = {"AR1": " *(baseline)*", "NAIVE": " *(last Q)*",
                "ENSEMBLE": " *(combined)*"}.get(model, "")
        md_out += f"| {model}{note} | — | — | — | {len(log)} | {latest_str} |\n"

md_out += f"\n## Recent Nowcasts ({min(30, len(log))} days)\n\n"
md_out += "| Date | DFM | BVAR | BEQ | AR(1) | NAIVE | ENSEMBLE | Actual |\n"
md_out += "|------|-----|------|-----|-------|-------|----------|--------|\n"
for _, row in log.tail(30).iterrows():
    vals = []
    for m in ["dfm", "bvar", "beq", "ar1", "naive", "ensemble"]:
        v = row.get(m)
        vals.append(f"{v:+.1f}%" if pd.notna(v) else "—")
    actual_v = row.get("actual_gdp_pct")
    actual_str = f"{actual_v:+.1f}%" if pd.notna(actual_v) else "—"
    md_out += f"| {row['date']} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} | {vals[4]} | {vals[5]} | {actual_str} |\n"

md_out += "\n## Data Sources\n\n"
md_out += "- **GDP (YoY):** DOSM `gdp_qtr_real` — non-SA, constant 2015 prices\n"
md_out += "- **Sectors:** DOSM `gdp_qtr_real_supply` — supply-side breakdown\n"
md_out += "- **Expenditure:** DOSM `gdp_qtr_real_demand` — demand-side breakdown\n"
md_out += "- **Dashboard:** [OpenDOSM GDP](https://open.dosm.gov.my/dashboard/gdp)\n"
md_out += "- **API:** [OpenDOSM Developer](https://developer.data.gov.my/static-api/opendosm)\n"
md_out += f"- **Last updated:** {today_str}\n\n"
md_out += "---\n*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*\n"

leaderboard_path = Path("docs") / "leaderboard.md"
leaderboard_path.write_text(md_out, encoding="utf-8")
logger.info("Leaderboard written to %s", leaderboard_path)

# Generate dashboards
import subprocess
for script in ["generate_dashboard.py", "generate_dashboard_md.py"]:
    try:
        result = subprocess.run([sys.executable, f"scripts/{script}"],
                                capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logger.info("%s completed", script)
        else:
            logger.warning("%s failed: %s", script, result.stderr)
    except Exception as e:
        logger.warning("%s could not run: %s", script, e)

# ---------------------------------------------------------------------------
# 7. Generate HTML dashboard data + inject (idempotent)
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
    "components": {},
    "sectors": sector_actuals,
    "leaderboard": [],
    "recent": [],
}

for comp_out, comp_key in [("consumption", "consumption"), ("investment", "investment"),
                           ("government", "government"), ("exports", "exports_comp"),
                           ("imports", "imports_comp")]:
    bvar_v = nowcasts.get(comp_key)
    act_v = nowcasts.get(comp_key + "_actual")
    err = round(abs(bvar_v - act_v), 1) if (bvar_v is not None and act_v is not None) else None
    dashboard_data["components"][comp_out] = {"bvar": bvar_v, "actual": act_v, "error": err}

# Backcast errors
if actual_yoy_gdp is not None:
    for model_key in ["dfm", "bvar", "ensemble"]:
        est = dashboard_data["backcast"][model_key]["estimate"]
        if est is not None:
            dashboard_data["backcast"][model_key]["error"] = round(abs(est - actual_yoy_gdp), 1)

# Leaderboard rows
if len(log) >= 3:
    for model in ["dfm", "bvar", "beq", "ensemble"]:
        if model not in log.columns:
            continue
        sub = log[[model, "actual_gdp_pct"]].dropna()
        if len(sub) < 3:
            continue
        pred = pd.to_numeric(sub[model], errors="coerce").values
        act = pd.to_numeric(sub["actual_gdp_pct"], errors="coerce").values
        valid = ~np.isnan(pred) & ~np.isnan(act)
        pred, act = pred[valid], act[valid]
        if len(pred) < 3:
            continue
        dashboard_data["leaderboard"].append({
            "model": model.upper(),
            "mae": round(compute_mae(act, pred), 3),
            "rmse": round(compute_rmse(act, pred), 3),
            "fda": round(compute_fda(act, pred) * 100, 1),
            "n": len(pred),
            "latest": round(float(nowcasts.get(model, 0)), 1) if nowcasts.get(model) is not None else None,
        })

for _, row in log.tail(30).iterrows():
    recent_row = {"date": row["date"]}
    for m in ["dfm", "bvar", "beq", "ensemble"]:
        v = row.get(m)
        recent_row[m] = round(float(v), 1) if pd.notna(v) else None
    actual_v = row.get("actual_gdp_pct")
    recent_row["actual"] = round(float(actual_v), 1) if pd.notna(actual_v) else None
    dashboard_data["recent"].append(recent_row)

# Inject data into HTML template — idempotent regex replace (count=1).
# Using a function replacement avoids backslashes in the JSON being treated
# as regex group references. subn lets us detect a missing marker.
dashboard_html_path = Path("docs") / "dashboard.html"
if dashboard_html_path.exists():
    html_template = dashboard_html_path.read_text(encoding="utf-8")
    data_json = json.dumps(dashboard_data, indent=2)
    html_new, n_sub = re.subn(
        r"const data = \{.*?\};",
        lambda _m: f"const data = {data_json};",
        html_template,
        count=1,
        flags=re.DOTALL,
    )
    if n_sub == 0:
        logger.warning("Dashboard marker 'const data = {...};' not found — skipping injection.")
    else:
        dashboard_html_path.write_text(html_new, encoding="utf-8")
        logger.info("Dashboard written to %s", dashboard_html_path)

logger.info("Daily update complete.")
logger.info("Nowcasts: %s", json.dumps({k: v for k, v in nowcasts.items() if k != "sector_actuals"}, indent=2))
