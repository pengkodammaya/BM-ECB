"""Daily update: fetch live data, run all 3 models, append to history, update leaderboard.

Runs in GitHub Actions on schedule. No local cache needed — fetches fresh each time.
"""
import sys; sys.path.insert(0, "src")

import json
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
    ir_df = fetch_interest_rate_history(start_year=2015, verbose=False)
    if not ir_df.empty:
        ir_df = ir_df.rename(columns={"value": "interbank"})
        filtered["interbank"] = ir_df[["date", "interbank"]]
except Exception:
    pass
try:
    fx_df = fetch_exchange_rate_history(start_year=2015, currency_code="USD", verbose=False)
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
datet = generate_dates(gd.year, gd.month, ed.year, ed.month)
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
# 3. Run all 3 models
# ---------------------------------------------------------------------------
nowcasts = {}
today_str = date.today().isoformat()

# DFM
try:
    dfm = DFM(DFMParams(r=3, p=2, max_iter=50, thresh=1e-5, idio=1))
    res = dfm.fit(X_est)
    nw = float(res.X_sm[-1, -1]) * sigma[-1] + mu[-1]
    nowcasts["dfm"] = round(nw * 100, 2)
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
    nw = float(res_b.X_sm[-1, -1]) * sigma[-1] + mu[-1]
    nowcasts["bvar"] = round(nw * 100, 2)
except Exception as e:
    print(f"BVAR failed: {e}")
    nowcasts["bvar"] = None

# BEQ
try:
    X_raw_beq = X_trans[ff:]
    beq = BEQ(BEQParams(lagM=1, lagQ=1, lagY=1, type=901))
    res_e = beq.fit(X_raw_beq, datet[ff:], AN)
    # Find last quarter-end with valid GDP
    gdp_col = -1
    for i in range(len(datet)-ff-1, -1, -1):
        if (datet[ff+i, 1] % 3 == 0) and not np.isnan(res_e.X_sm[i, gdp_col]):
            nw = float(res_e.X_sm[i, gdp_col])
            break
    nowcasts["beq"] = round(nw * 100, 2)
except Exception as e:
    print(f"BEQ failed: {e}")
    nowcasts["beq"] = None

# Ensemble
vals = [v for v in nowcasts.values() if v is not None]
# Ensemble
vals = [v for v in nowcasts.values() if v is not None]
nowcasts["ensemble"] = round(np.median(vals), 2) if vals else None

# ---------------------------------------------------------------------------
# 3b. Component-level nowcasts: Investment, Exports, Imports
# ---------------------------------------------------------------------------
client2 = OpenDOSMClient()
COMPONENTS = [
    ("investment", "gdp_qtr_real_demand", "e3", "growth_yoy"),
    ("exports_comp", "gdp_qtr_real_demand", "e5", "growth_yoy"),
    ("imports_comp", "gdp_qtr_real_demand", "e6", "growth_yoy"),
]

for comp_key, comp_did, comp_type, comp_series in COMPONENTS:
    try:
        df_comp = client2.fetch(comp_did, limit=20000)
        if df_comp is None or df_comp.empty:
            continue
        comp_val = df_comp[(df_comp["type"] == comp_type) & (df_comp["series"] == comp_series)].copy()
        if len(comp_val) == 0:
            continue
        comp_val = comp_val[["date", "value"]].rename(columns={"value": "target"})
        comp_val["date"] = pd.to_datetime(comp_val["date"])
        comp_val = comp_val.sort_values("date").dropna()
        comp_val["target"] = comp_val["target"] / 100.0

        # Reuse same monthly indicator grid, swap target
        Xc = np.full((T, nM + 1), np.nan)
        Xc[:, :nM] = X[:, :nM]  # copy monthly indicators
        for _, row in comp_val.iterrows():
            y, m = row["date"].year, row["date"].month
            qem = ((m - 1) // 3) * 3 + 3
            idx = np.where((datet[:, 0] == y) & (datet[:, 1] == qem))[0]
            if len(idx) > 0:
                Xc[idx[0], -1] = row["target"]

        Xc_trans = Xc.copy()
        for j, name in enumerate(AN):
            tcode = DATASETS.get(name, (None, None, 0, None, {}))[2]
            freq = "quarterly" if name == "gdp" else "monthly"
            Xc_trans[:, j] = transform_series(Xc[:, j].copy(), tcode, freq)

        muc = np.nanmean(Xc_trans, axis=0)
        sigmac = np.nanstd(Xc_trans, axis=0)
        sigmac[sigmac < 1e-10] = 1.0
        Xc_std = (Xc_trans - muc) / sigmac
        ffc = np.where(~np.all(np.isnan(Xc_std), axis=1))[0][0]
        Xc_est = Xc_std[ffc:]

        if np.sum(~np.isnan(Xc_est[:, -1])) < 5:
            continue

        dfm_c = DFM(DFMParams(r=3, p=2, max_iter=30, thresh=1e-5, idio=1))
        res_c = dfm_c.fit(Xc_est)
        nwc = float(res_c.X_sm[-1, -1]) * sigmac[-1] + muc[-1]
        nowcasts[comp_key] = round(nwc * 100, 2)

        # Also fetch actual latest value
        for i in range(len(Xc_est)-1, -1, -1):
            if not np.isnan(Xc_est[i, -1]):
                act_comp = (Xc_est[i, -1] * sigmac[-1] + muc[-1]) * 100
                nowcasts[comp_key + "_actual"] = round(act_comp, 2)
                break
    except Exception as e:
        print(f"  Component {comp_key}: {e}")
        nowcasts[comp_key] = None

client2.close()

# Latest actual GDP
actual_pct = None
for i in range(len(X_est)-1, -1, -1):
    if not np.isnan(X_est[i, -1]):
        actual_pct = float(X_est[i, -1] * sigma[-1] + mu[-1]) * 100
        break

nowcasts["date"] = today_str
nowcasts["actual_gdp_pct"] = round(actual_pct, 2) if actual_pct else None

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
# 6. Generate markdown leaderboard (always, even with <3 data points)
# -------------------------------------------------------------------
md = f"# Malaysia GDP Nowcasting — Live Leaderboard\n\n"
md += f"**Last updated:** {today_str} | **Source:** [OpenDOSM](https://open.dosm.gov.my) + [BNM](https://apikijangportal.bnm.gov.my)\n\n"
md += "## Latest Nowcast\n\n"
for model in ["DFM", "BVAR", "BEQ", "ENSEMBLE"]:
    col = model.lower()
    val = nowcasts.get(col)
    if val is not None:
        md += f"- **{model}:** `{val:+.2f}%` QoQ SA\n"
if actual_pct:
    md += f"\n*Latest actual GDP: {actual_pct:+.1f}%*\n"

md += "\n## Model Leaderboard\n\n"
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

    md += "| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |\n"
    md += "|-------|----------|-----------|---------|---|--------|\n"
    for _, r in lb_df.iterrows():
        latest = r.get("last_nowcast", "—")
        latest_str = f"{latest:+.1f}%" if isinstance(latest, (int, float)) else "—"
        md += f"| {r['model']} | {r['MAE (pp)']:.3f} | {r['RMSE (pp)']:.3f} | {r['FDA (%)']:.1f}% | {int(r['N'])} | {latest_str} |\n"
else:
    md += f"*Leaderboard requires 3+ daily observations. Currently: {len(log)}. First metrics expected soon.*\n\n"
    md += "| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |\n"
    md += "|-------|----------|-----------|---------|---|--------|\n"
    for model in ["DFM", "BVAR", "BEQ", "ENSEMBLE"]:
        col = model.lower()
        val = nowcasts.get(col)
        latest_str = f"{val:+.1f}%" if val is not None else "—"
        md += f"| {model} | — | — | — | {len(log)} | {latest_str} |\n"

md += f"\n## Recent Nowcasts ({min(30, len(log))} days)\n\n"
md += "| Date | DFM | BVAR | BEQ | ENSEMBLE | Actual |\n"
md += "|------|-----|------|-----|----------|--------|\n"
for _, row in log.tail(30).iterrows():
    vals = []
    for m in ["dfm", "bvar", "beq", "ensemble", "actual_gdp_pct"]:
        v = row.get(m)
        vals.append(f"{v:+.1f}%" if pd.notna(v) else "—")
    md += f"| {row['date']} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} | {vals[4]} |\n"

    md += f"\n## Component Nowcasts (YoY %)\n\n"
    comp_labels = {"investment": "Investment (GFCF)", "exports_comp": "Exports", "imports_comp": "Imports"}
    for ck, cl in comp_labels.items():
        v = nowcasts.get(ck)
        a = nowcasts.get(ck + "_actual")
        v_str = f"`{v:+.1f}%`" if v is not None else "—"
        a_str = f"`{a:+.1f}%`" if a is not None else "—"
        md += f"- **{cl}:** nowcast {v_str} | actual {a_str}\n"

md += f"\n## Ground Truth Definition\n\n"
md += f"- **Main GDP:** QoQ SA growth from DOSM `gdp_qtr_real_sa` (seasonally adjusted, constant 2015 prices)\n"
md += f"- **Components:** YoY growth from DOSM `gdp_qtr_real_demand` (expenditure approach, non-SA)\n"
md += f"- **Source:** [OpenDOSM API](https://open.dosm.gov.my) — live data, fetched fresh each run\n"
md += f"- **Latest vintage:** {today_str}\n\n"
md += f"---\n*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*\n"
(Path("docs") / "leaderboard.md").write_text(md)

print(f"[{datetime.now().isoformat()}] Daily update complete.")
print(json.dumps(nowcasts, indent=2))
