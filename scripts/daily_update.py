"""Daily update: fetch live data, run all 3 models, append to history, score.

Runs in GitHub Actions on schedule. No local cache needed — fetches fresh each time.

This version is quarter-matched, vintage-frozen, and horizon-stratified:
  * Every model nowcast is pinned to the CURRENT quarter (not the last grid row).
  * Each daily nowcast is stamped with the target quarter it predicts.
  * A frozen-vintage actuals table records the FIRST published value for each
    quarter (and tracks later revisions separately), so historical accuracy
    never silently rewrites itself when DOSM revises GDP.
  * Leaderboard scoring joins nowcasts to actuals ON TARGET QUARTER and is
    stratified by forecast horizon (months-to-quarter).

CI-safety: all new reads use safe_read_csv, all writes are atomic, all new
files are created on first run, and every new block is wrapped so a failure
degrades to a warning rather than crashing the Action.
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

# Bump this when DOSM rebases the constant-price series (currently 2015).
CURRENT_BASE_YEAR = 2015

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
# 0. Helpers — hardened I/O
# ---------------------------------------------------------------------------
def safe_fetch(dataset_id, limit=20000):
    """Fetch an OpenDOSM dataset, returning an empty DataFrame on ANY failure."""
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
    """Write a CSV atomically: temp file then rename (crash-safe)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)


def interpolate_no_leak(col):
    """Linear-interpolate interior NaNs only — never fill past last valid obs."""
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
    """NaN-safe standardisation; all-NaN columns collapse to mu=0, sigma=1."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        mu = np.nanmean(arr, axis=0)
        sigma = np.nanstd(arr, axis=0)
    mu = np.nan_to_num(mu, nan=0.0)
    sigma = np.nan_to_num(sigma, nan=1.0)
    sigma[sigma < 1e-10] = 1.0
    return (arr - mu) / sigma, mu, sigma


# ---------------------------------------------------------------------------
# 0b. Helpers — quarter math, vintage table, horizon, scoring
# ---------------------------------------------------------------------------
def date_to_quarter(ts):
    """Timestamp/date -> 'YYYY-Qn'."""
    ts = pd.Timestamp(ts)
    return f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"


def parse_quarter(q):
    """'YYYY-Qn' -> (year, quarter). Raises on malformed input."""
    y, qq = str(q).split("-Q")
    return int(y), int(qq)


def horizon_bucket(row_date, target_q):
    """Forecast horizon of a nowcast made on row_date for target quarter target_q.

    forecast = before the quarter starts; m1/m2/m3 = which month within the
    quarter; backcast = after the quarter ended (but actual not yet published).
    """
    try:
        d = pd.Timestamp(row_date)
        ty, tq = parse_quarter(target_q)
        q_start = (tq - 1) * 3 + 1
        months = (d.year - ty) * 12 + (d.month - q_start)
        if months < 0:
            return "forecast"
        if months in (0, 1, 2):
            return f"m{months + 1}"
        return "backcast"
    except Exception:
        return "unknown"


def update_vintage(vintage_df, quarter, metric, value, today_str, base_year):
    """Insert a first-release value or update the latest (revised) value.

    Long format keyed by (quarter, metric). first_value is FROZEN at first sight;
    latest_value tracks revisions. Returns the (possibly modified) DataFrame.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return vintage_df
    value = round(float(value), 3)
    mask = (vintage_df["quarter"] == quarter) & (vintage_df["metric"] == metric)
    if mask.any():
        idx = vintage_df.index[mask][0]
        vintage_df.at[idx, "latest_value"] = value
        vintage_df.at[idx, "last_update_date"] = today_str
        # Record a base change without overwriting the frozen first_value.
        if int(vintage_df.at[idx, "base_year"]) != int(base_year):
            logger.warning("Base year change for %s/%s: %s -> %s",
                           quarter, metric, vintage_df.at[idx, "base_year"], base_year)
    else:
        vintage_df.loc[len(vintage_df)] = {
            "quarter": quarter, "metric": metric,
            "first_release_date": today_str, "first_value": value,
            "latest_value": value, "last_update_date": today_str,
            "base_year": int(base_year),
        }
    return vintage_df


def empty_vintage():
    return pd.DataFrame(columns=[
        "quarter", "metric", "first_release_date", "first_value",
        "latest_value", "last_update_date", "base_year",
    ])


def vintage_first_map(vintage_df, metric):
    """quarter -> frozen first-release value, for one metric."""
    if vintage_df is None or vintage_df.empty:
        return {}
    sub = vintage_df[vintage_df["metric"] == metric]
    return dict(zip(sub["quarter"], pd.to_numeric(sub["first_value"], errors="coerce")))


def resolve_target_quarter(row):
    """Target quarter for a daily_log row: stamped if present, else inferred
    from the run date (which equals the current quarter at run time)."""
    tq = row.get("target_quarter")
    if isinstance(tq, str) and "-Q" in tq:
        return tq
    try:
        return date_to_quarter(row["date"])
    except Exception:
        return None


def score_log(log, vintage, metric, models):
    """Score each model in `log` against FROZEN first-release actuals, joined on
    target quarter. Returns (overall_rows, horizon_rows). Pending quarters
    (actual not yet published) are skipped automatically."""
    overall, by_h = [], []
    if log is None or len(log) == 0:
        return overall, by_h
    vmap = vintage_first_map(vintage, metric)
    if not vmap:
        return overall, by_h

    work = log.copy()
    work["_tq"] = work.apply(resolve_target_quarter, axis=1)
    work["_actual"] = work["_tq"].map(vmap)
    work = work.dropna(subset=["_actual"])
    if work.empty:
        return overall, by_h
    work["_horizon"] = work.apply(lambda r: horizon_bucket(r["date"], r["_tq"]), axis=1)

    for model in models:
        if model not in work.columns:
            continue
        sub = work[[model, "_actual", "_horizon"]].dropna(subset=[model])
        pred = pd.to_numeric(sub[model], errors="coerce").values
        act = pd.to_numeric(sub["_actual"], errors="coerce").values
        ok = ~np.isnan(pred) & ~np.isnan(act)
        if ok.sum() >= 3:
            overall.append({
                "model": model.upper(),
                "MAE (pp)": round(compute_mae(act[ok], pred[ok]), 3),
                "RMSE (pp)": round(compute_rmse(act[ok], pred[ok]), 3),
                "FDA (%)": round(compute_fda(act[ok], pred[ok]) * 100, 1),
                "N": int(ok.sum()),
            })
        for h in ["forecast", "m1", "m2", "m3", "backcast"]:
            hs = sub[sub["_horizon"] == h]
            if len(hs) < 2:
                continue
            hp = pd.to_numeric(hs[model], errors="coerce").values
            ha = pd.to_numeric(hs["_actual"], errors="coerce").values
            hok = ~np.isnan(hp) & ~np.isnan(ha)
            if hok.sum() < 2:
                continue
            by_h.append({
                "model": model.upper(), "horizon": h,
                "MAE (pp)": round(compute_mae(ha[hok], hp[hok]), 3),
                "N": int(hok.sum()),
            })
    return overall, by_h


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
    "wrt_volume": ("iowrt", "volume", 1, "consumption", {"series": "abs"}),
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
    name, (did, col, tcode, group, filters) = args
    try:
        df = cache.get(did)
        if df is None:
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

from concurrent.futures import ThreadPoolExecutor, as_completed

logger.info("Fetching %d datasets in parallel...", len(DATASETS))
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(fetch_single_dataset, item): item[0]
               for item in DATASETS.items()}
    for future in as_completed(futures):
        name, df = future.result()
        if df is not None:
            filtered[name] = df

for var in ["ipi", "imports_capital", "imports_consumer"]:
    if var in filtered:
        filtered[var][var] = filtered[var][var] / 100.0

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

for k in ["interbank", "fx_usd"]:
    if k in filtered:
        DATASETS[k] = (k, k, 0, "financial", {})

# 1.5 Lagged FX features
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

# 1.6 Global indicators via yfinance
GLOBAL_INDICATORS = {
    "sp500": ("^GSPC", "global_equity"), "shcomp": ("000001.SS", "global_equity"),
    "sox": ("^SOX", "global_equity"), "klci": ("^KLSE", "global_equity"),
    "sti": ("^STI", "global_equity"), "brent": ("BZ=F", "global_commodity"),
    "cpo": ("CPO=F", "global_commodity"), "bdry": ("BDRY", "global_demand"),
}
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
                continue
            if isinstance(data.columns, pd.MultiIndex):
                close_col = ("Close", ticker) if ("Close", ticker) in data.columns else data.columns[0]
            else:
                close_col = "Close" if "Close" in data.columns else "Adj Close"
            monthly = data[close_col].resample("ME").last().dropna()
            if len(monthly) < 24:
                continue
            vals = monthly.values
            growth = np.full(len(vals), np.nan)
            for i in range(1, len(vals)):
                if vals[i-1] > 0:
                    growth[i] = np.log(vals[i]) - np.log(vals[i-1])
            df_out = pd.DataFrame({"date": monthly.index, label: growth}).dropna()
            filtered[label] = df_out
            DATASETS[label] = (label, label, 0, group, {})
            logger.info("yfinance %s: %d monthly obs", label, len(df_out))
        except Exception as e:
            logger.warning("yfinance %s failed: %s", label, e)

# 1.7 FRED
FRED_SERIES = {
    "us_ip": ("INDPRO", "global_demand"), "us_caputil": ("TCU", "global_demand"),
    "us_sentiment": ("UMCSENT", "global_demand"),
}
fred_key_path = Path(".fred_key")
if fred_key_path.exists():
    fred_key = fred_key_path.read_text().strip()
    for label, (sid, group) in FRED_SERIES.items():
        try:
            import httpx
            resp = httpx.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={"series_id": sid, "api_key": fred_key, "file_type": "json",
                        "observation_start": "2015-01-01"},
                timeout=15,
            )
            obs = resp.json().get("observations", [])
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
            filtered[label] = df_fred
            DATASETS[label] = (label, label, 0, group, {})
            logger.info("FRED %s: %d monthly obs", label, len(df_fred))
        except Exception as e:
            logger.warning("FRED %s failed: %s", label, e)

# 1.8 SITC
sitc_df = safe_fetch("trade_sitc_1d")
if not sitc_df.empty:
    for section, label in [("overall", "sitc_total"), ("7", "sitc_machinery")]:
        try:
            sub = sitc_df[sitc_df["section"] == section].copy()
            if len(sub) > 0:
                sub = sub[["date", "exports"]].dropna().rename(columns={"exports": label})
                sub["date"] = pd.to_datetime(sub["date"])
                sub = sub.sort_values("date").drop_duplicates("date")
                filtered[label] = sub
                DATASETS[label] = (label, label, 1, "external", {})
        except Exception as e:
            logger.warning("SITC %s failed: %s", label, e)

# FATAL GUARD
if "gdp" not in filtered or filtered["gdp"].empty:
    logger.error("GDP target fetch failed — cannot run nowcasts. Aborting.")
    sys.exit(1)

# Component / sector indicator subsets
COMPONENT_INDICATORS = {
    "consumption": [n for n in DATASETS if n != "gdp"],
    "investment":  [n for n in DATASETS if DATASETS[n][3] in ("industry", "financial", "leading", "external") and n != "gdp"],
    "government":  [n for n in DATASETS if DATASETS[n][3] in ("labour", "financial") and n != "gdp"],
    "exports_comp":[n for n in DATASETS if DATASETS[n][3] in ("external", "financial", "industry", "global_equity", "global_commodity", "global_demand") and n != "gdp"],
    "imports_comp":[n for n in DATASETS if DATASETS[n][3] in ("external", "services", "prices", "global_commodity") and n != "gdp"],
}
SECTOR_INDICATORS = {
    "agriculture": [n for n in DATASETS if DATASETS[n][3] in ("industry", "prices", "leading", "external") and n != "gdp"],
    "mining": [n for n in DATASETS if DATASETS[n][3] in ("industry", "prices", "external") and n != "gdp"],
    "manufacturing": [n for n in DATASETS if DATASETS[n][3] in ("industry", "prices", "leading", "external", "global_equity") and n != "gdp"],
    "construction": [n for n in DATASETS if DATASETS[n][3] in ("industry", "leading", "financial") and n != "gdp"],
    "services": [n for n in DATASETS if DATASETS[n][3] in ("industry", "services", "coincident", "labour") and n != "gdp"],
}
for ck, indicators in COMPONENT_INDICATORS.items():
    if len(indicators) < 3:
        COMPONENT_INDICATORS[ck] = [n for n in DATASETS if n != "gdp"]
COMPONENT_PARAMS = {
    "consumption": (2, 4), "investment": (3, 2), "government": (2, 2),
    "exports_comp": (3, 2), "imports_comp": (3, 2),
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
ed_extended = ed + pd.DateOffset(months=6)
datet = generate_dates(gd.year, gd.month, ed_extended.year, ed_extended.month)
T = len(datet)
nM = len(MN)
X = np.full((T, nM + 1), np.nan)

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
    tcode = DATASETS.get(name, (None, None, 0, None, {}))[2]
    freq = "quarterly" if name == "gdp" else "monthly"
    X_trans[:, j] = transform_series(X[:, j].copy(), tcode, freq)

X_std, mu, sigma = standardize(X_trans)
non_empty_rows = np.where(~np.all(np.isnan(X_std), axis=1))[0]
if len(non_empty_rows) == 0:
    logger.error("No usable observations after transform/standardise. Aborting.")
    sys.exit(1)
ff = non_empty_rows[0]
X_est = X_std[ff:]

# ---------------------------------------------------------------------------
# 3. Models — all pinned to the CURRENT quarter
# ---------------------------------------------------------------------------
nowcasts = {}
today_str = date.today().isoformat()
today_dt = date.today()
current_quarter = (today_dt.month - 1) // 3 + 1
current_year = today_dt.year
current_q_end_m = current_quarter * 3

# Stamp the target quarter every downstream score will join on.
nowcasts["target_quarter"] = f"{current_year}-Q{current_quarter}"

if np.any(~np.isnan(X_est[:, -1])):
    last_actual_idx = int(np.where(~np.isnan(X_est[:, -1]))[0][-1])
else:
    last_actual_idx = len(X_est) - 1


def grid_quarter_idx(first_row, year, qend_m):
    """Index into a grid that starts at datet[first_row], for a quarter-end."""
    for i in range(len(datet) - first_row):
        if datet[first_row + i, 0] == year and datet[first_row + i, 1] == qend_m:
            return i
    return -1


current_q_idx = grid_quarter_idx(ff, current_year, current_q_end_m)
next_q_end_m = current_q_end_m + 3
next_q_year = current_year + (1 if next_q_end_m > 12 else 0)
next_q_end_m = ((next_q_end_m - 1) % 12) + 1
next_q_idx = grid_quarter_idx(ff, next_q_year, next_q_end_m)

if current_q_idx < 0:
    logger.warning("Current quarter (Q%d %d) not in grid — data may be stale.",
                   current_quarter, current_year)

backcast_label = f"Q{((datet[ff + last_actual_idx, 1]) // 3)} {int(datet[ff + last_actual_idx, 0])}"
nowcast_label = f"Q{current_quarter} {current_year}" if current_q_idx >= 0 else "N/A"
forecast_label = f"Q{next_q_end_m // 3} {next_q_year}" if next_q_idx >= 0 else "N/A"


def _extract(res, idx, sigma_arr, mu_arr, gdp_col=-1):
    if idx is not None and idx >= 0 and idx < res.X_sm.shape[0]:
        return round((float(res.X_sm[idx, gdp_col]) * sigma_arr[gdp_col] + mu_arr[gdp_col]) * 100, 2)
    return None


try:
    dfm = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
    res = dfm.fit(X_est)
    nowcasts["dfm"] = _extract(res, current_q_idx, sigma, mu)
    nowcasts["dfm_backcast"] = _extract(res, last_actual_idx, sigma, mu)
    nowcasts["dfm_forecast"] = _extract(res, next_q_idx, sigma, mu)
except Exception as e:
    logger.warning("DFM failed: %s", e)
    nowcasts["dfm"] = None

try:
    X_filled = X_est.copy()
    for j in range(X_filled.shape[1]):
        X_filled[:, j] = interpolate_no_leak(X_filled[:, j])
    X_bvar = X_filled.copy()
    if 0 <= last_actual_idx < X_bvar.shape[0]:
        X_bvar[last_actual_idx, -1] = np.nan
    bvar = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-5, bvar_max_iter=10, bvar_n_draws=50, bvar_burn_in=15))
    res_b = bvar.fit(X_bvar, datet[ff:])
    nowcasts["bvar"] = _extract(res_b, current_q_idx, sigma, mu)
    nowcasts["bvar_backcast"] = _extract(res_b, last_actual_idx, sigma, mu)
    nowcasts["bvar_forecast"] = _extract(res_b, next_q_idx, sigma, mu)
    if res_b.B_draws is not None and res_b.Sigma_draws is not None and current_q_idx >= 0:
        from nowcasting_toolbox.fan_chart import bvar_fan_chart
        lags, N = 3, X_filled.shape[1]
        x_last = X_filled[current_q_idx - lags + 1:current_q_idx + 1].flatten()
        if len(x_last) == N * lags:
            fc = bvar_fan_chart(res_b.B_draws, res_b.Sigma_draws, x_last,
                                n_forecast=1, lags=lags, target_idx=-1,
                                sigma_y=sigma[-1], mu_y=mu[-1])
            nowcasts["bvar_ci_10"] = round(float(fc["percentiles"][10][0]) * 100, 2)
            nowcasts["bvar_ci_90"] = round(float(fc["percentiles"][90][0]) * 100, 2)
except Exception as e:
    logger.warning("BVAR failed: %s", e)
    nowcasts["bvar"] = None

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

# Weighted ensemble — scored from the daily log (vintage-frozen, see section 5)
log_ens = safe_read_csv("docs/daily_log.csv")
ensemble_models = ["dfm", "bvar", "beq"]
weights = {}
vintage_for_weights = safe_read_csv("docs/actuals_vintage.csv")
if log_ens is not None and len(log_ens) >= 3 and vintage_for_weights is not None:
    qmap = vintage_first_map(vintage_for_weights, "gdp_qoq")
    if qmap:
        tmp = log_ens.copy()
        tmp["_tq"] = tmp.apply(resolve_target_quarter, axis=1)
        tmp["_actual"] = tmp["_tq"].map(qmap)
        tmp = tmp.dropna(subset=["_actual"])
        for m in ensemble_models:
            if m in tmp.columns:
                sub = tmp[[m, "_actual"]].dropna()
                if len(sub) >= 3:
                    p = pd.to_numeric(sub[m], errors="coerce").values
                    a = pd.to_numeric(sub["_actual"], errors="coerce").values
                    ok = ~np.isnan(p) & ~np.isnan(a)
                    if ok.sum() >= 3:
                        weights[m] = 1.0 / (compute_mae(a[ok], p[ok]) ** 2 + 0.01)

valid_ens = [m for m in ensemble_models if nowcasts.get(m) is not None and m in weights]
if valid_ens:
    total_w = sum(weights[m] for m in valid_ens)
    nowcasts["ensemble"] = (round(sum(nowcasts[m] * weights[m] / total_w for m in valid_ens), 2)
                            if total_w > 0 else None)
else:
    vals = [nowcasts.get(m) for m in ensemble_models if nowcasts.get(m) is not None]
    nowcasts["ensemble"] = round(float(np.median(vals)), 2) if vals else None

# 3.5 AR(1)
try:
    gdp_qoq = X_est[:, -1]
    q_end_mask = np.array([datet[ff + i, 1] % 3 == 0 for i in range(len(X_est))])
    gdp_vals = gdp_qoq[q_end_mask & ~np.isnan(gdp_qoq)]
    if len(gdp_vals) >= 4:
        y_lag, y_curr = gdp_vals[:-1], gdp_vals[1:]
        valid = ~np.isnan(y_lag) & ~np.isnan(y_curr)
        if np.sum(valid) >= 4:
            X_ar = np.column_stack([np.ones(np.sum(valid)), y_lag[valid]])
            ar_coeffs = np.linalg.lstsq(X_ar, y_curr[valid], rcond=None)[0]
            last_gdp = gdp_vals[-1] if not np.isnan(gdp_vals[-1]) else gdp_vals[-2]
            nowcasts["ar1"] = round((ar_coeffs[0] + ar_coeffs[1] * last_gdp) * sigma[-1] + mu[-1]) * 100 \
                if False else round(((ar_coeffs[0] + ar_coeffs[1] * last_gdp) * sigma[-1] + mu[-1]) * 100, 2)
except Exception as e:
    logger.warning("AR(1) failed: %s", e)
    nowcasts["ar1"] = None

# ---------------------------------------------------------------------------
# 3a. YoY GDP + sector actuals
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

SECTOR_MAP = {"p1": "agriculture", "p2": "mining", "p3": "manufacturing",
              "p4": "construction", "p5": "services"}
sector_actuals = {}
df_supply = safe_fetch("gdp_qtr_real_supply")
if not df_supply.empty:
    for sc, sn in SECTOR_MAP.items():
        try:
            sr = df_supply[(df_supply["sector"] == sc) & (df_supply["series"] == "growth_yoy")].copy()
            if not sr.empty:
                sr["date"] = pd.to_datetime(sr["date"])
                sector_actuals[sn] = round(sr.sort_values("date").iloc[-1]["value"], 2)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# 3b. Component nowcasts — pinned to current quarter
# ---------------------------------------------------------------------------
df_demand = safe_fetch("gdp_qtr_real_demand")
COMPONENTS = [
    ("consumption", "e1", "growth_yoy"), ("investment", "e3", "growth_yoy"),
    ("government", "e2", "growth_yoy"), ("exports_comp", "e5", "growth_yoy"),
    ("imports_comp", "e6", "growth_yoy"),
]
comp_levels, comp_levels_yoy = {}, {}

if df_demand.empty:
    logger.warning("df_demand fetch failed — skipping all component nowcasts.")
else:
    for comp_key, comp_type, _ in COMPONENTS:
        try:
            abs_data = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == "abs")]
            if len(abs_data) > 0:
                abs_data = abs_data.copy(); abs_data["date"] = pd.to_datetime(abs_data["date"])
                comp_levels[comp_key] = abs_data.sort_values("date").iloc[-1]["value"]
            yoy_data = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == "growth_yoy")]
            if len(yoy_data) > 0:
                yoy_data = yoy_data.copy(); yoy_data["date"] = pd.to_datetime(yoy_data["date"])
                comp_levels_yoy[comp_key] = yoy_data.sort_values("date").iloc[-1]["value"]
        except Exception:
            pass

    for comp_key, comp_type, comp_series in COMPONENTS:
        try:
            target_names = [n for n in COMPONENT_INDICATORS.get(comp_key, MN) if n in filtered]
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

            # Current-quarter index within this component grid (fallback: last row)
            comp_q_idx = grid_quarter_idx(ffc, current_year, current_q_end_m)
            if comp_q_idx < 0 or comp_q_idx >= Xc_est.shape[0]:
                comp_q_idx = Xc_est.shape[0] - 1

            cr, cp = COMPONENT_PARAMS.get(comp_key, (3, 2))
            dfm_c = DFM(DFMParams(r=cr, p=cp, max_iter=30, thresh=1e-5, idio=1))
            res_c = dfm_c.fit(Xc_est)
            nowcasts[comp_key + "_dfm"] = round((float(res_c.X_sm[comp_q_idx, -1]) * sigmac[-1] + muc[-1]) * 100, 2)

            try:
                Xc_filled = Xc_est.copy()
                for j in range(Xc_filled.shape[1]):
                    Xc_filled[:, j] = interpolate_no_leak(Xc_filled[:, j])
                bvar_c = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-3, bvar_max_iter=5))
                res_bc = bvar_c.fit(Xc_filled, datet[ffc:])
                nowcasts[comp_key] = round((float(res_bc.X_sm[comp_q_idx, -1]) * sigmac[-1] + muc[-1]) * 100, 2)
            except Exception as e:
                logger.warning("Component BVAR %s failed: %s", comp_key, e)
                nowcasts[comp_key] = nowcasts.get(comp_key + "_dfm")

            try:
                beq_c = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
                res_ec = beq_c.fit(Xc_trans, datet[ffc:], target_names)
                if res_ec.X_sm is not None and res_ec.X_sm.shape[0] > 0 and 0 <= comp_q_idx < res_ec.X_sm.shape[0]:
                    nw_e = float(res_ec.X_sm[comp_q_idx, -1])
                    nowcasts[comp_key + "_beq"] = round(nw_e * 100, 2) if not np.isnan(nw_e) else None
                else:
                    nowcasts[comp_key + "_beq"] = None
            except Exception as e:
                logger.warning("Component BEQ %s failed: %s", comp_key, e)
                nowcasts[comp_key + "_beq"] = None
        except Exception as e:
            logger.warning("Component %s: %s", comp_key, e)
            nowcasts[comp_key] = None

# ---------------------------------------------------------------------------
# 3b2. Sector nowcasts
# ---------------------------------------------------------------------------
logger.info("Running sector nowcasts...")
df_sector_gdp = safe_fetch("gdp_qtr_real_supply")
for sector_code, sector_name in SECTOR_MAP.items():
    try:
        if df_sector_gdp.empty:
            nowcasts[f"sector_{sector_name}"] = None
            continue
        sr = df_sector_gdp[(df_sector_gdp["sector"] == sector_code) & (df_sector_gdp["series"] == "growth_yoy")].copy()
        if sr.empty:
            nowcasts[f"sector_{sector_name}"] = None
            continue
        sr["date"] = pd.to_datetime(sr["date"]); sr = sr.sort_values("date")
        sgv, sgd = sr["value"].values / 100.0, sr["date"].values
        X_sector_target = np.full(T, np.nan)
        for i, d in enumerate(sgd):
            dt = pd.Timestamp(d); qem = ((dt.month - 1) // 3) * 3 + 3
            idx = np.where((datet[:, 0] == dt.year) & (datet[:, 1] == qem))[0]
            if len(idx) > 0 and i < len(sgv):
                X_sector_target[idx[0]] = sgv[i]

        si = SECTOR_INDICATORS.get(sector_name, [])
        if len(si) < 3:
            si = [n for n in DATASETS if n != "gdp"]
        vsi = [n for n in si if n in filtered]
        if len(vsi) < 2:
            nowcasts[f"sector_{sector_name}"] = None
            continue

        X_sector = np.full((T, len(vsi) + 1), np.nan)
        for j, name in enumerate(vsi):
            df = filtered[name]
            for _, row in df.iterrows():
                y, m = row["date"].year, row["date"].month
                idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
                if len(idx) > 0:
                    X_sector[idx[0], j] = row[name]
        X_sector[:, -1] = X_sector_target

        X_sector_trans = X_sector.copy()
        for j, name in enumerate(vsi):
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
            sqi = grid_quarter_idx(ffs, current_year, current_q_end_m)
            if not (0 <= sqi < res_s.X_sm.shape[0]):
                sqi = res_s.X_sm.shape[0] - 1
            nowcasts[f"sector_{sector_name}"] = round((float(res_s.X_sm[sqi, -1]) * sigma_s[-1] + mu_s[-1]) * 100, 2)
        except Exception:
            nowcasts[f"sector_{sector_name}"] = None
    except Exception as e:
        logger.warning("Sector %s: %s", sector_name, e)
        nowcasts[f"sector_{sector_name}"] = None

# ---------------------------------------------------------------------------
# 3c. YoY GDP nowcast
# ---------------------------------------------------------------------------
if not df_gdp_yoy.empty:
    try:
        yoy_rows = df_gdp_yoy[df_gdp_yoy["series"] == "growth_yoy"].copy()
        yoy_rows["date"] = pd.to_datetime(yoy_rows["date"]); yoy_rows = yoy_rows.sort_values("date")
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
            cqy = grid_quarter_idx(ff_y, current_year, current_q_end_m)
            dfm_y = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
            res_y = dfm_y.fit(Xy_est)
            if 0 <= cqy < res_y.X_sm.shape[0]:
                nowcasts["dfm_yoy"] = round((float(res_y.X_sm[cqy, -1]) * sigma_y[-1] + mu_y[-1]) * 100, 2)
            try:
                Xy_filled = Xy_est.copy()
                for j in range(Xy_filled.shape[1]):
                    Xy_filled[:, j] = interpolate_no_leak(Xy_filled[:, j])
                bvar_y = BVAR(BVARParams(bvar_lags=2, bvar_thresh=1e-3, bvar_max_iter=5))
                res_by = bvar_y.fit(Xy_filled, datet[ff_y:])
                if 0 <= cqy < res_by.X_sm.shape[0]:
                    nowcasts["bvar_yoy"] = round((float(res_by.X_sm[cqy, -1]) * sigma_y[-1] + mu_y[-1]) * 100, 2)
            except Exception as e:
                logger.warning("YoY BVAR failed: %s", e)
            yv = [v for v in [nowcasts.get("dfm_yoy"), nowcasts.get("bvar_yoy")] if v is not None]
            if yv:
                nowcasts["ensemble_yoy"] = round(float(np.median(yv)), 2)
    except Exception as e:
        logger.warning("YoY GDP nowcast failed: %s", e)

nowcasts["sector_actuals"] = json.dumps(sector_actuals)

# 3d. GDP identity (all YoY)
try:
    c_level = comp_levels.get("consumption", 0); i_level = comp_levels.get("investment", 0)
    g_level = comp_levels.get("government", 0); x_level = comp_levels.get("exports_comp", 0)
    m_level_abs = abs(comp_levels.get("imports_comp", 0)) or 1.0
    cg, ig, gg, xg, gdpg = (nowcasts.get("consumption"), nowcasts.get("investment"),
                            nowcasts.get("government"), nowcasts.get("exports_comp"),
                            nowcasts.get("dfm_yoy"))
    if all(v is not None for v in [cg, ig, gg, xg, gdpg, c_level, i_level, g_level, x_level]):
        cg, ig, gg, xg, gdpg = cg/100, ig/100, gg/100, xg/100, gdpg/100
        m_g = (c_level*cg + i_level*ig + g_level*gg + x_level*xg
               - (c_level + i_level + g_level + x_level - m_level_abs) * gdpg) / m_level_abs
        nowcasts["imports_identity"] = round(m_g * 100, 2)
    else:
        nowcasts["imports_identity"] = None
except Exception as e:
    logger.warning("GDP identity derivation failed: %s", e)
    nowcasts["imports_identity"] = None

for ck in ["consumption", "investment", "government", "exports_comp", "imports_comp"]:
    nowcasts[ck + "_actual"] = comp_levels_yoy.get(ck)

# 3.7 Component AR(1)
if not df_demand.empty:
    for comp_key, comp_type, _ in COMPONENTS:
        try:
            cy = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == "growth_yoy")].copy()
            if len(cy) < 5:
                continue
            cy["date"] = pd.to_datetime(cy["date"]); cy = cy.sort_values("date")
            yv = cy["value"].values
            yl, yc = yv[:-1], yv[1:]
            valid = ~np.isnan(yl) & ~np.isnan(yc)
            if np.sum(valid) >= 4:
                Xar = np.column_stack([np.ones(np.sum(valid)), yl[valid]])
                coeffs = np.linalg.lstsq(Xar, yc[valid], rcond=None)[0]
                nowcasts[comp_key + "_ar1"] = round(coeffs[0] + coeffs[1] * yv[-1], 2)
        except Exception as e:
            logger.warning("AR(1) %s: %s", comp_key, e)
for ck in ["consumption", "investment", "government", "exports_comp", "imports_comp"]:
    nowcasts[ck + "_naive"] = comp_levels_yoy.get(ck)

# Latest actual QoQ (for continuity in the log; NOT used for scoring)
actual_pct = None
for i in range(len(X_est)-1, -1, -1):
    if not np.isnan(X_est[i, -1]):
        actual_pct = float(X_est[i, -1] * sigma[-1] + mu[-1]) * 100
        break
nowcasts["date"] = today_str
nowcasts["actual_gdp_pct"] = round(actual_pct, 2) if actual_pct is not None else None
nowcasts["naive"] = nowcasts["actual_gdp_pct"]

# ---------------------------------------------------------------------------
# 4. Vintage-frozen actuals table (first release frozen; revisions tracked)
# ---------------------------------------------------------------------------
vintage_path = Path("docs/actuals_vintage.csv")
vintage = safe_read_csv(vintage_path)
if vintage is None or vintage.empty or "metric" not in (vintage.columns if vintage is not None else []):
    vintage = empty_vintage()

try:
    # GDP QoQ (matches the QoQ leaderboard basis)
    for _, row in filtered["gdp"].iterrows():
        q = date_to_quarter(row["date"])
        vintage = update_vintage(vintage, q, "gdp_qoq", row["gdp"] * 100, today_str, CURRENT_BASE_YEAR)
    # GDP YoY
    if not df_gdp_yoy.empty:
        for _, row in yoy_rows.iterrows():
            vintage = update_vintage(vintage, date_to_quarter(row["date"]), "gdp_yoy",
                                     row["value"], today_str, CURRENT_BASE_YEAR)
    # Component YoY
    if not df_demand.empty:
        for comp_key, comp_type, _ in COMPONENTS:
            cd = df_demand[(df_demand["type"] == comp_type) & (df_demand["series"] == "growth_yoy")].copy()
            if cd.empty:
                continue
            cd["date"] = pd.to_datetime(cd["date"])
            for _, row in cd.iterrows():
                vintage = update_vintage(vintage, date_to_quarter(row["date"]),
                                         f"{comp_key}_yoy", row["value"], today_str, CURRENT_BASE_YEAR)
    atomic_write_csv(vintage, vintage_path)
    logger.info("Vintage table updated (%d quarter-metric rows).", len(vintage))
except Exception as e:
    logger.warning("Vintage update failed (non-fatal): %s", e)

# ---------------------------------------------------------------------------
# 5. Append to daily log (atomic, target_quarter stamped)
# ---------------------------------------------------------------------------
log_path = Path("docs/daily_log.csv")
new_row = pd.DataFrame([nowcasts])
existing = safe_read_csv(log_path)
if existing is not None:
    log = pd.concat([existing, new_row], ignore_index=True).drop_duplicates(subset=["date"], keep="last")
else:
    log = new_row
atomic_write_csv(log, log_path)
logger.info("Daily log written (%d rows).", len(log))

# Vintage-frozen, quarter-matched, horizon-stratified scoring
qoq_overall, qoq_by_h = [], []
try:
    qoq_overall, qoq_by_h = score_log(
        log, vintage, "gdp_qoq", ["dfm", "bvar", "beq", "ar1", "naive", "ensemble"])
    if qoq_overall:
        atomic_write_csv(pd.DataFrame(qoq_overall), Path("docs/leaderboard.csv"))
    if qoq_by_h:
        atomic_write_csv(pd.DataFrame(qoq_by_h), Path("docs/leaderboard_by_horizon.csv"))
except Exception as e:
    logger.warning("Scoring failed (non-fatal): %s", e)

# ---------------------------------------------------------------------------
# 6. Markdown leaderboard
# ---------------------------------------------------------------------------
comp_qoq_map = vintage_first_map(vintage, "gdp_yoy")  # for current-quarter actual lookup
target_q = nowcasts["target_quarter"]

md_out = "# Malaysia GDP Nowcasting — Live Leaderboard\n\n"
md_out += f"**Updated:** {today_str} | **Latest actual:** {backcast_label} | **Nowcasting:** {nowcast_label}\n\n"

md_out += "## GDP Nowcast (YoY %)\n\n"
md_out += f"*Nowcasting {nowcast_label}. Actual releases ~mid-{(current_quarter*3+2) % 12 or 12}; scored once published.*\n\n"
md_out += "| Model | Nowcast |\n|-------|--------|\n"
for nm, key in [("DFM", "dfm_yoy"), ("BVAR", "bvar_yoy"), ("ENSEMBLE", "ensemble_yoy")]:
    v = nowcasts.get(key)
    md_out += f"| {nm} | {f'`{v:+.1f}%`' if v is not None else '—'} |\n"

md_out += "\n## GDP by Expenditure Category (YoY %)\n\n"
md_out += f'*Nowcasts target {nowcast_label}. "Actual" is the FROZEN first-release value once {nowcast_label} publishes; "pending" until then.*\n\n'
md_out += "| Component | BVAR | DFM | Actual (target Q) | Error |\n|-----------|------|-----|-------------------|-------|\n"
comp_labels = {"consumption": ("Private Consumption", "C"), "investment": ("Gross Fixed Capital Formation", "I"),
               "government": ("Government Consumption", "G"), "exports_comp": ("Exports", "X"),
               "imports_comp": ("Imports", "M")}
for ck, (clabel, ccode) in comp_labels.items():
    bv, dv = nowcasts.get(ck), nowcasts.get(ck + "_dfm")
    actual_target = vintage_first_map(vintage, f"{ck}_yoy").get(target_q)
    bs = f"{bv:+.1f}%" if bv is not None else "—"
    ds = f"{dv:+.1f}%" if dv is not None else "—"
    if actual_target is not None and not np.isnan(actual_target):
        as_, es = f"{actual_target:+.1f}%", (f"{abs(bv - actual_target):.1f}pp" if bv is not None else "—")
    else:
        as_, es = "pending", "pending"
    md_out += f"| **{clabel}** ({ccode}) | {bs} | {ds} | {as_} | {es} |\n"

md_out += "\n## GDP by Economic Sector (YoY %)\n\n"
md_out += "| Sector | Latest Actual |\n|--------|---------------|\n"
for sk, sn in {"agriculture": "Agriculture", "mining": "Mining & Quarrying", "manufacturing": "Manufacturing",
               "construction": "Construction", "services": "Services"}.items():
    a = sector_actuals.get(sk)
    md_out += f"| {sn} | {f'`{a:+.1f}%`' if a is not None else '—'} |\n"
if actual_yoy_gdp is not None:
    md_out += f"| **Overall GDP** | `{actual_yoy_gdp:+.1f}%` |\n"

md_out += "\n## Model Accuracy (vintage-frozen, quarter-matched)\n\n"
md_out += "*MAE/RMSE/FDA vs FIRST-RELEASE actuals, joined on target quarter. Appears after 3+ scored quarters.*\n\n"
if qoq_overall:
    md_out += "| Model | MAE (pp) | RMSE (pp) | FDA (%) | N |\n|-------|----------|-----------|---------|---|\n"
    for r in qoq_overall:
        md_out += f"| {r['model']} | {r['MAE (pp)']:.3f} | {r['RMSE (pp)']:.3f} | {r['FDA (%)']:.1f}% | {r['N']} |\n"
else:
    md_out += "*No quarters scored yet — accumulating nowcasts until target quarters publish.*\n"

md_out += "\n## Accuracy by Horizon (QoQ)\n\n"
md_out += "*forecast = before quarter; m1/m2/m3 = month within quarter; backcast = after quarter end, pre-release.*\n\n"
if qoq_by_h:
    md_out += "| Model | Horizon | MAE (pp) | N |\n|-------|---------|----------|---|\n"
    for r in sorted(qoq_by_h, key=lambda x: (x["model"], x["horizon"])):
        md_out += f"| {r['model']} | {r['horizon']} | {r['MAE (pp)']:.3f} | {r['N']} |\n"
else:
    md_out += "*Not enough scored observations per horizon yet.*\n"

md_out += f"\n## Recent Nowcasts ({min(30, len(log))} days)\n\n"
md_out += "| Date | Target Q | DFM | BVAR | BEQ | ENSEMBLE |\n|------|----------|-----|------|-----|----------|\n"
for _, row in log.tail(30).iterrows():
    tq = resolve_target_quarter(row) or "—"
    vals = [f"{row.get(m):+.1f}%" if pd.notna(row.get(m)) else "—" for m in ["dfm", "bvar", "beq", "ensemble"]]
    md_out += f"| {row['date']} | {tq} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |\n"

md_out += "\n## Data Sources\n\n"
md_out += "- **GDP:** DOSM `gdp_qtr_real` (YoY), `gdp_qtr_real_sa` (QoQ)\n"
md_out += "- **Expenditure:** DOSM `gdp_qtr_real_demand`; **Sectors:** `gdp_qtr_real_supply`\n"
md_out += "- **Vintages:** `docs/actuals_vintage.csv` (first-release frozen, revisions tracked)\n"
md_out += f"- **Last updated:** {today_str}\n\n"
md_out += "---\n*Auto-generated daily via GitHub Actions. [Source](https://github.com/pengkodammaya/BM-ECB)*\n"

Path("docs").mkdir(parents=True, exist_ok=True)
(Path("docs") / "leaderboard.md").write_text(md_out, encoding="utf-8")
logger.info("Leaderboard written.")

# Dashboards (subprocess, guarded)
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
# 7. HTML dashboard data (idempotent injection)
# ---------------------------------------------------------------------------
dashboard_data = {
    "lastUpdated": today_str,
    "targetQuarter": target_q,
    "latestActual": {"quarter": backcast_label, "yoy": actual_yoy_gdp},
    "nowcast": {"quarter": nowcast_label, "dfm": nowcasts.get("dfm_yoy"),
                "bvar": nowcasts.get("bvar_yoy"), "ensemble": nowcasts.get("ensemble_yoy")},
    "components": {}, "sectors": sector_actuals,
    "leaderboard": qoq_overall, "byHorizon": qoq_by_h, "recent": [],
}
for out_key, ck in [("consumption", "consumption"), ("investment", "investment"),
                    ("government", "government"), ("exports", "exports_comp"), ("imports", "imports_comp")]:
    bv = nowcasts.get(ck)
    at = vintage_first_map(vintage, f"{ck}_yoy").get(target_q)
    at = None if (at is not None and np.isnan(at)) else at
    err = round(abs(bv - at), 1) if (bv is not None and at is not None) else None
    dashboard_data["components"][out_key] = {"bvar": bv, "actual": at, "error": err}

for _, row in log.tail(30).iterrows():
    rr = {"date": row["date"], "target_quarter": resolve_target_quarter(row)}
    for m in ["dfm", "bvar", "beq", "ensemble"]:
        v = row.get(m)
        rr[m] = round(float(v), 1) if pd.notna(v) else None
    dashboard_data["recent"].append(rr)

dashboard_html_path = Path("docs") / "dashboard.html"
if dashboard_html_path.exists():
    try:
        html_template = dashboard_html_path.read_text(encoding="utf-8")
        data_json = json.dumps(dashboard_data, indent=2)
        html_new, n_sub = re.subn(r"const data = \{.*?\};",
                                  lambda _m: f"const data = {data_json};",
                                  html_template, count=1, flags=re.DOTALL)
        if n_sub == 0:
            logger.warning("Dashboard marker 'const data = {...};' not found — skipping injection.")
        else:
            dashboard_html_path.write_text(html_new, encoding="utf-8")
            logger.info("Dashboard written.")
    except Exception as e:
        logger.warning("Dashboard injection failed (non-fatal): %s", e)

logger.info("Daily update complete. Target quarter: %s", target_q)
logger.info("Nowcasts: %s",
            json.dumps({k: v for k, v in nowcasts.items() if k != "sector_actuals"}, indent=2))
