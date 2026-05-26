"""Trace how expanding window + ragged edge interact in our backtest."""
import sys; sys.path.insert(0,"src")
import numpy as np
import pandas as pd
from datetime import date
from rich.console import Console
from rich.table import Table

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.eval.vintage import ARCVintageBuilder
from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams

console = Console()

# Load full dataset (once)
DATASETS = {
    "ipi": ("ipi", "index", 0, {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, {"division": "overall"}),
    "cpi_core": ("cpi_core", "index", 1, {"division": "overall"}),
    "ppi": ("ppi", "index", 1, {"series": "abs"}),
    "u_rate": ("lfs_month", "u_rate", 0, {}),
    "p_rate": ("lfs_month", "p_rate", 0, {}),
    "leading": ("economic_indicators", "leading", 1, {}),
    "coincident": ("economic_indicators", "coincident", 1, {}),
    "exports": ("trade_headline", "exports", 1, {"series": "abs"}),
    "wrt": ("iowrt", "sales", 1, {"series": "abs"}),
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

# Build common grid
md = [df["date"].min() for df in filtered.values()]
Mx = [df["date"].max() for df in filtered.values()]
gd_ = max(filtered["gdp"]["date"].min(), pd.Timestamp("2018-01-01"))
ed_ = max(Mx)
datet_full = generate_dates(gd_.year, gd_.month, ed_.year, ed_.month)
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
DID_MAP = ["ipi", "cpi_headline", "cpi_core", "ppi", "u_rate", "u_rate", "leading", "coincident", "exports", "wrt", "gdp"]

# ---------------------------------------------------------------------------
# Trace: 3 vintages at different points in time
# ---------------------------------------------------------------------------
test_vintages = [
    ("Early COVID", date(2020, 8, 15)),    # Aug 2020 — limited data, no COVID precedent
    ("Mid Recovery", date(2022, 5, 15)),   # May 2022 — has COVID data now
    ("Late Period", date(2025, 2, 15)),    # Feb 2025 — full history including COVID
]

table = Table(title="Expanding Window + Ragged Edge Interaction")
table.add_column("Vintage")
table.add_column("Date Range\n(available data)", style="dim")
table.add_column("GDP Obs\n(quarterly)", justify="right")
table.add_column("Complete\nMonthly Rows", justify="right")
table.add_column("Nowcast\n(Q1 GDP)", justify="right")
table.add_column("Actual\n(Q1 GDP)", justify="right")

for label, vdate in test_vintages:
    # Build vintage with ragged edge
    X_vint = vb.build(X_raw.copy(), datet, vdate, var_names=AN, dataset_ids=DID_MAP)

    # Trim leading NaN
    valid_rows = ~np.all(np.isnan(X_vint), axis=1)
    first = np.where(valid_rows)[0][0]
    X_vint_trim = X_vint[first:]
    datet_vint = datet[first:]

    # Stats
    T_vint = X_vint_trim.shape[0]
    gdp_obs = int(np.sum(~np.isnan(X_vint_trim[:, -1])))
    complete_rows = int(np.sum(~np.any(np.isnan(X_vint_trim), axis=1)))

    date_start = f"{int(datet_vint[0,0])}-{int(datet_vint[0,1]):02d}"
    date_end = f"{int(datet_vint[-1,0])}-{int(datet_vint[-1,1]):02d}"

    # What quarters are nowcastable?
    q1_year = vdate.year
    q1_end_m = 3
    # Find Q1 GDP row
    q1_idx = None
    for t in range(len(datet_vint)):
        if datet_vint[t, 0] == q1_year and datet_vint[t, 1] == q1_end_m:
            q1_idx = t
            break

    # Run DFM on this vintage
    vint_mu = np.nanmean(X_vint_trim, axis=0)
    vint_sigma = np.nanstd(X_vint_trim, axis=0)
    vint_sigma[vint_sigma < 1e-10] = 1.0
    X_vint_std = (X_vint_trim - vint_mu) / vint_sigma

    nowcast_str = "—"
    actual_str = "—"
    try:
        dfm = DFM(DFMParams(r=3, p=2, max_iter=30, thresh=1e-5, idio=1))
        res = dfm.fit(X_vint_std)
        if q1_idx is not None and q1_idx < res.X_sm.shape[0]:
            nw_std = float(res.X_sm[q1_idx, -1])
            nw_pct = (nw_std * vint_sigma[-1] + vint_mu[-1]) * 100
            nowcast_str = f"{nw_pct:+.1f}%"

            # Actual (from full data, post-standardization for comparison)
            if not np.isnan(X_vint_std[q1_idx, -1]):
                act_pct = (X_vint_std[q1_idx, -1] * vint_sigma[-1] + vint_mu[-1]) * 100
                actual_str = f"{act_pct:+.1f}% (in-sample)"
            else:
                actual_str = "(not yet released)"
    except:
        pass

    table.add_row(
        f"{label}\n({vdate})",
        f"{date_start} — {date_end}\n{T_vint} months",
        str(gdp_obs),
        str(complete_rows),
        nowcast_str,
        actual_str,
    )

console.print(table)

console.print()
console.print("[bold]Key points:[/bold]")
console.print("  1. Early COVID (2020): Only ~6 quarters of GDP data, no COVID precedent → model relies on pre-COVID patterns")
console.print("  2. Mid Recovery (2022): COVID period (2020-2021) now in training set → model 'learned' pandemic dynamics")
console.print("  3. Late Period (2025): Full 2018-2024 history → model has seen a complete business cycle")
console.print()
console.print("  [bold]The ragged edge ensures:[/bold]")
console.print("  - Trailing months are NaN (data not yet published)")
console.print("  - But EARLIER months get FILLED IN as vintages advance")
console.print("  - The Kalman filter handles the ragged edge naturally")
console.print("  - The EM uses ALL available data at each vintage to estimate factors")
