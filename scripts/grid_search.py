"""Grid search over DFM hyperparameters (r, p) for lowest MAE."""
import sys; sys.path.insert(0,"src")
import numpy as np
import pandas as pd
from pathlib import Path
from rich.console import Console
from rich.table import Table

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.eval.vintage import ARCVintageBuilder, generate_vintage_dates
from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule
from nowcasting_toolbox.eval.metrics import compute_mae, compute_fda
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams

console = Console()

# Load full data once
DATASETS = {
    "ipi": ("ipi", "index", 0, "industry", {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, "prices", {"division": "overall"}),
    "cpi_core": ("cpi_core", "index", 1, "prices", {"division": "overall"}),
    "ppi": ("ppi", "index", 1, "prices", {"series": "abs"}),
    "u_rate": ("lfs_month", "u_rate", 0, "labour", {}),
    "p_rate": ("lfs_month", "p_rate", 0, "labour", {}),
    "leading": ("economic_indicators", "leading", 1, "leading", {}),
    "coincident": ("economic_indicators", "coincident", 1, "coincident", {}),
    "exports": ("trade_headline", "exports", 1, "external", {"series": "abs"}),
    "wrt": ("iowrt", "sales", 1, "services", {"series": "abs"}),
    "gdp": ("gdp_qtr_real_sa", "value", 0, "target", {"series": "abs"}),
}
MN = [n for n in DATASETS if n != "gdp"]
AN = MN + ["gdp"]
GROUPS = [DATASETS[n][3] for n in AN]

cache = DataCache(ttl_hours=24)
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
gd = max(filtered["gdp"]["date"].min(), pd.Timestamp("2018-01-01"))
ed = max(Mx)
datet_full = generate_dates(gd.year, gd.month, ed.year, ed.month)
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

# Standardize
X_std = (X_raw - mu) / sigma

# Grid search
arc_schedule = build_publication_schedule(years=[2023, 2024, 2025, 2026], cache_dir=Path("data/malaysia"))
vb = ARCVintageBuilder(schedule=arc_schedule)
DID_MAP = ["ipi", "cpi_headline", "cpi_core", "ppi", "u_rate", "u_rate", "leading", "coincident", "exports", "wrt", "gdp"]
vintage_dates = generate_vintage_dates(2021, 2, 2025, 11, frequency="quarterly", day_of_month=15)

# Test combinations
r_values = [2, 3, 4, 5]
p_values = [1, 2, 3, 4]
gdp_idx = -1

console.print("[cyan]Grid Search: DFM (r, p) over {} vintages[/cyan]".format(len(vintage_dates)))

results = []
for r in r_values:
    for p in p_values:
        errors = []
        directions = []
        for vdate in vintage_dates:
            vmonth = vdate.month
            vyear = vdate.year
            q_end_m = ((vmonth - 1) // 3) * 3 + 3

            X_vint = vb.build(X_raw.copy(), datet, vdate, var_names=AN, dataset_ids=DID_MAP)
            vint_mu = np.nanmean(X_vint, axis=0)
            vint_sigma = np.nanstd(X_vint, axis=0)
            vint_sigma[vint_sigma < 1e-10] = 1.0
            X_vint_std = (X_vint - vint_mu) / vint_sigma

            valid_rows = ~np.all(np.isnan(X_vint_std), axis=1)
            if np.sum(valid_rows) < 24:
                continue
            first = np.where(valid_rows)[0][0]
            X_vint_std = X_vint_std[first:]
            datet_vint = datet[first:]

            try:
                dfm = DFM(DFMParams(r=r, p=p, max_iter=30, thresh=1e-5, idio=1))
                res = dfm.fit(X_vint_std)
                
                q_end_idx = -1
                for t in range(len(datet_vint)):
                    if datet_vint[t, 0] == vyear and datet_vint[t, 1] == q_end_m:
                        q_end_idx = t; break
                
                if q_end_idx >= 0:
                    nw = float(res.X_sm[q_end_idx, gdp_idx]) * vint_sigma[gdp_idx] + vint_mu[gdp_idx]
                    
                    act = np.nan
                    for t in range(len(datet)):
                        if datet[t, 0] == vyear and datet[t, 1] == q_end_m:
                            if not np.isnan(X_raw[t, gdp_idx]):
                                act = X_raw[t, gdp_idx]
                            break
                    
                    if not np.isnan(nw) and not np.isnan(act):
                        errors.append(abs(nw - act) * 100)
                        directions.append(np.sign(nw) == np.sign(act) or (nw == 0 and act == 0))
            except Exception:
                pass

        if len(errors) >= 3:
            mae = np.mean(errors)
            fda = np.mean(directions) if directions else 0
            results.append({"r": r, "p": p, "mae": mae, "fda": fda, "n": len(errors)})
            console.print(f"  [dim]r={r}, p={p}: MAE={mae:.3f} pp, FDA={fda:.1%}, N={len(errors)}[/dim]")

# Best
if results:
    best_mae = min(results, key=lambda x: x["mae"])
    best_fda = max(results, key=lambda x: x["fda"])
    
    table = Table(title="DFM Grid Search Results")
    table.add_column("r", justify="right")
    table.add_column("p", justify="right")
    table.add_column("MAE (pp)", justify="right")
    table.add_column("FDA (%)", justify="right")
    table.add_column("N", justify="right")
    
    for r in sorted(set(x["r"] for x in results)):
        for res in sorted([x for x in results if x["r"] == r], key=lambda x: x["mae"]):
            style = "green" if res == best_mae else ""
            table.add_row(str(res["r"]), str(res["p"]), f"{res['mae']:.3f}", f"{res['fda']:.1%}", str(res["n"]), style=style)
    
    console.print()
    console.print(table)
    console.print(f"\n[green]Best MAE: r={best_mae['r']}, p={best_mae['p']} ({best_mae['mae']:.3f} pp)[/green]")
    console.print(f"[green]Best FDA: r={best_fda['r']}, p={best_fda['p']} ({best_fda['fda']:.1%})[/green]")
