"""News decomposition: show how new data releases change the GDP nowcast."""
import sys; sys.path.insert(0,"src")
import numpy as np
import pandas as pd
from datetime import date
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.eval.vintage import ARCVintageBuilder
from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams
from nowcasting_toolbox.news.base import compute_news

console = Console(force_terminal=True)

# Force UTF-8
import os; os.environ["PYTHONIOENCODING"] = "utf-8"

# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------
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
GROUPS = [DATASETS[n][3] for n in MN] + ["target"]

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
X_std = (X_trans - mu) / sigma

ff = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
X_std = X_std[ff:]
X_raw = X_trans[ff:]
datet = datet_full[ff:]

client.close()

# ---------------------------------------------------------------------------
# 2. Vintage builder
# ---------------------------------------------------------------------------
arc_schedule = build_publication_schedule(
    years=[2023, 2024, 2025, 2026],
    cache_dir=Path("data/malaysia"),
)
vb = ARCVintageBuilder(schedule=arc_schedule)
DID_MAP = ["ipi", "cpi_headline", "cpi_core", "ppi", "u_rate", "u_rate",
           "leading", "coincident", "exports", "wrt", "gdp"]

# ---------------------------------------------------------------------------
# 3. Compare two recent vintages
# ---------------------------------------------------------------------------
vintage_old = date(2026, 5, 1)   # May 1 — CPI Apr not yet, IPI Mar not yet
vintage_new = date(2026, 5, 24)  # May 24 — CPI Apr, IPI Mar, Labour Mar, GDP Q1 released

console.print(Panel.fit("[bold cyan]NEWS DECOMPOSITION[/bold cyan]\n"
                         f"Comparing vintages: {vintage_old} -> {vintage_new}\n"
                         f"(What new data arrived and how did it change the GDP nowcast?)"))

# Build vintages
X_old_raw = vb.build(X_raw.copy(), datet, vintage_old, var_names=AN, dataset_ids=DID_MAP)
X_new_raw = vb.build(X_raw.copy(), datet, vintage_new, var_names=AN, dataset_ids=DID_MAP)

# Show what changed
console.print("\n[bold]New data received between vintages:[/bold]")
table_changes = Table()
table_changes.add_column("Variable")
table_changes.add_column("Old last value")
table_changes.add_column("New last value")
table_changes.add_column("Status")

for j, name in enumerate(AN):
    old_last = np.where(~np.isnan(X_old_raw[:, j]))[0]
    new_last = np.where(~np.isnan(X_new_raw[:, j]))[0]
    old_end = old_last[-1] if len(old_last) > 0 else -1
    new_end = new_last[-1] if len(new_last) > 0 else -1
    old_val = X_old_raw[old_end, j] if old_end >= 0 else np.nan
    new_val = X_new_raw[new_end, j] if new_end >= 0 else np.nan

    if old_end != new_end:
        status = "[green]NEW[/green]"
    else:
        status = "[dim]unchanged[/dim]"

    old_str = f"{old_val:+.3f}" if not np.isnan(old_val) else "NaN"
    new_str = f"{new_val:+.3f}" if not np.isnan(new_val) else "NaN"

    table_changes.add_row(name, old_str, new_str, status)

console.print(table_changes)

# Standardize both vintages using old vintage's parameters
vint_mu = np.nanmean(X_old_raw, axis=0)
vint_sigma = np.nanstd(X_old_raw, axis=0)
vint_sigma[vint_sigma < 1e-10] = 1.0
X_old_std = (X_old_raw - vint_mu) / vint_sigma
X_new_std = (X_new_raw - vint_mu) / vint_sigma

# Trim leading NaN
valid_rows = ~np.all(np.isnan(X_old_std), axis=1)
first = np.where(valid_rows)[0][0]
X_old_std = X_old_std[first:]
X_new_std = X_new_std[first:]
datet_est = datet[first:]

# Fit DFM on old data
console.print("\n[bold]Fitting DFM on old vintage...[/bold]")
dfm = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
res_old = dfm.fit(X_old_std)

# Compute news decomposition
# Target quarter: the last quarter with GDP data in the old vintage, or next quarter
gdp_col = -1
last_gdp_old = np.where(~np.isnan(X_old_std[:, gdp_col]))[0]
target_idx = len(X_old_std) - 1  # last row

console.print(f"\n[bold]Computing news decomposition...[/bold]")
news = compute_news(
    X_old_std,
    X_new_std,
    res_old.A,
    res_old.C,
    res_old.Q,
    res_old.R,
    var_names=AN,
    group_names=GROUPS,
    gdp_col=gdp_col,
    target_quarter_end_idx=target_idx,
)

# Display results
console.print(f"\n  Old nowcast: {news['old_nowcast_pct']:+.2f}%")
console.print(f"  New nowcast: {news['new_nowcast_pct']:+.2f}%")
console.print(f"  [bold]Total change: {news['total_change_pp']:+.3f} pp[/bold]")

# News table
console.print()
table_news = Table(title="News Decomposition — Contribution by Variable")
table_news.add_column("Variable", style="bold")
table_news.add_column("Group")
table_news.add_column("Contribution (pp)", justify="right")
table_news.add_column("% of Total", justify="right")
table_news.add_column("Direction")

for row in news["news_table"]:
    direction = "+" if row["direction"] == "up" else "-" if row["direction"] == "down" else "."
    style = "green" if row["direction"] == "up" else "red" if row["direction"] == "down" else ""
    table_news.add_row(
        row["series"],
        row["group"],
        f"{row['contribution_pp']:+.3f}",
        f"{row['pct_of_total']:.1f}%",
        direction,
        style=style,
    )

console.print(table_news)

# Group summary
console.print()
table_groups = Table(title="News by Category")
table_groups.add_column("Category", style="bold")
table_groups.add_column("Total Contribution (pp)", justify="right")
for grp, contrib in sorted(news["summary_by_group"].items(), key=lambda x: abs(x[1]), reverse=True):
    style = "green" if contrib > 0 else "red"
    table_groups.add_row(grp, f"{contrib:+.3f}", style=style)
console.print(table_groups)
