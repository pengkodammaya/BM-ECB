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
nowcasts["ensemble"] = round(np.median(vals), 2) if vals else None

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
    # 6. Generate HTML dashboard
    # -------------------------------------------------------------------
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Malaysia GDP Nowcasting — Live Dashboard</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #f5f5f5; }}
.card {{ background: white; border-radius: 8px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
h1 {{ color: #1a1a2e; margin: 0 0 8px 0; }}
h2 {{ color: #16213e; margin: 0 0 16px 0; font-size: 1.2em; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 10px 14px; text-align: right; border-bottom: 1px solid #eee; }}
th {{ background: #f8f9fa; color: #555; font-weight: 600; text-transform: uppercase; font-size: 0.8em; }}
th:first-child, td:first-child {{ text-align: left; }}
tr:hover {{ background: #f8f9ff; }}
.nowcast-badge {{ font-size: 2em; font-weight: bold; color: #16213e; }}
.meta {{ color: #888; font-size: 0.85em; margin-top: 8px; }}
.updated {{ color: #28a745; }}
.stale {{ color: #dc3545; }}
.best {{ background: #d4edda !important; }}
</style>
</head>
<body>
<div class="card">
<h1>Malaysia GDP Nowcasting Dashboard</h1>
<p class="meta">Live nowcast updated daily via GitHub Actions | Last update: {today_str}</p>
</div>
<div class="card">
<h2>Latest Nowcast</h2>
"""
    for model in ["DFM", "BVAR", "BEQ", "ENSEMBLE"]:
        col = model.lower()
        val = nowcasts.get(col)
        if val is not None:
            html += f'<p><strong>{model}:</strong> <span class="nowcast-badge">{val:+.2f}%</span> QoQ SA</p>'
    if actual_pct:
        html += f'<p class="meta">Latest actual GDP: {actual_pct:+.1f}%</p>'

    html += '</div><div class="card"><h2>Model Leaderboard</h2><table><tr><th>Model</th><th>MAE (pp)</th><th>RMSE (pp)</th><th>FDA (%)</th><th>N</th><th>Latest</th></tr>'
    for _, r in lb_df.iterrows():
        style = ' class="best"' if r["model"] == "ENSEMBLE" else ""
        latest = r.get("last_nowcast", "—")
        latest_str = f"{latest:+.1f}%" if isinstance(latest, (int, float)) else "—"
        html += f'<tr{style}><td>{r["model"]}</td><td>{r["MAE (pp)"]:.3f}</td><td>{r["RMSE (pp)"]:.3f}</td><td>{r["FDA (%)"]:.1f}%</td><td>{int(r["N"])}</td><td>{latest_str}</td></tr>'
    html += '</table></div>'

    # Add daily log chart (last 30 days)
    if len(log) >= 2:
        recent = log.tail(30)
        html += '<div class="card"><h2>Recent Nowcasts (30 days)</h2><table><tr><th>Date</th><th>DFM</th><th>BVAR</th><th>BEQ</th><th>ENSEMBLE</th><th>Actual</th></tr>'
        for _, row in recent.iterrows():
            html += '<tr>'
            html += f'<td>{row["date"]}</td>'
            for m in ["dfm", "bvar", "beq", "ensemble", "actual_gdp_pct"]:
                v = row.get(m)
                v_str = f'{v:+.1f}%' if pd.notna(v) else '—'
                html += f'<td>{v_str}</td>'
            html += '</tr>'
        html += '</table></div>'

    html += f'<div class="card"><p class="meta">Source: <a href="https://open.dosm.gov.my">OpenDOSM</a> + <a href="https://apikijangportal.bnm.gov.my">BNM</a> | Port of <a href="https://github.com/baptiste-meunier/Nowcasting_toolbox">ECB Nowcasting Toolbox</a> | <a href="https://github.com/pengkodammaya/BM-ECB">GitHub</a></p></div>'
    html += '</body></html>'

    (Path("docs") / "index.html").write_text(html)
    print("Dashboard generated.")

print(f"[{datetime.now().isoformat()}] Daily update complete.")
print(json.dumps(nowcasts, indent=2))
