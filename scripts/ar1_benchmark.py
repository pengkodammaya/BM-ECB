"""Compare DFM vs AR(1) baseline for investment, exports, imports."""
import sys; sys.path.insert(0,"src")
import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache
from nowcasting_toolbox.data.calendar import generate_dates
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams
from nowcasting_toolbox.eval.metrics import compute_mae, compute_fda, compute_rmse

console = Console()

# ---------------------------------------------------------------------------
# 1. Load demand-side GDP data
# ---------------------------------------------------------------------------
COMPONENTS = {
    "Investment (e3)": ("gdp_qtr_real_demand", "e3"),
    "Exports (e5)":    ("gdp_qtr_real_demand", "e5"),
    "Imports (e6)":    ("gdp_qtr_real_demand", "e6"),
    "GDP (e0)":        ("gdp_qtr_real_demand", "e0"),
}

cache = DataCache(ttl_hours=24)
client = OpenDOSMClient()

component_data = {}
for label, (did, tcode) in COMPONENTS.items():
    df_demand = cache.get(did)
    if df_demand is None:
        df_demand = client.fetch(did, limit=20000)
        if df_demand is not None and not df_demand.empty:
            cache.put(did, df_demand)

    sub = df_demand[(df_demand["type"] == tcode) & (df_demand["series"] == "growth_yoy")].copy()
    sub = sub[["date", "value"]].rename(columns={"value": label})
    sub["date"] = pd.to_datetime(sub["date"])
    sub = sub.sort_values("date").dropna()
    component_data[label] = sub

client.close()

# ---------------------------------------------------------------------------
# 2. AR(1) expanding window benchmark
# ---------------------------------------------------------------------------
console.print("[cyan]AR(1) Expanding Window Forecast[/cyan]")

ar1_results = {}
for label, df in component_data.items():
    y = df[label].values  # YoY growth in %
    dates = df["date"].values
    T = len(y)

    forecasts = np.full(T, np.nan)
    for t in range(12, T):  # start after 12 quarters (3 years of training)
        y_train = y[:t]
        # Fit AR(1): y_t = c + phi * y_{t-1} + e_t
        y_lag = y_train[:-1]
        y_curr = y_train[1:]
        valid = ~np.isnan(y_lag) & ~np.isnan(y_curr)
        if np.sum(valid) < 4:
            continue
        try:
            X = np.column_stack([np.ones(np.sum(valid)), y_lag[valid]])
            coeffs = np.linalg.lstsq(X, y_curr[valid], rcond=None)[0]
            forecasts[t] = coeffs[0] + coeffs[1] * y[t-1]
        except:
            pass

    # Compute errors
    valid_idx = ~np.isnan(forecasts)
    if np.sum(valid_idx) < 3:
        ar1_results[label] = {"mae": np.nan, "rmse": np.nan, "fda": np.nan, "n": 0}
        continue

    pred = forecasts[valid_idx]
    act = y[valid_idx]
    ar1_results[label] = {
        "mae": compute_mae(act, pred),
        "rmse": compute_rmse(act, pred),
        "fda": compute_fda(act, pred),
        "n": int(np.sum(valid_idx)),
    }

# ---------------------------------------------------------------------------
# 3. DFM nowcast (using same monthly indicators as main pipeline)
# ---------------------------------------------------------------------------
console.print("[cyan]DFM Nowcast[/cyan]")

MONTHLY = {
    "ipi": ("ipi", "index", 0, {"series": "growth_mom"}),
    "cpi_headline": ("cpi_headline", "index", 1, {"division": "overall"}),
    "cpi_core": ("cpi_core", "index", 1, {"division": "overall"}),
    "ppi": ("ppi", "index", 1, {"series": "abs"}),
    "u_rate": ("lfs_month", "u_rate", 0, {}),
    "p_rate": ("lfs_month", "p_rate", 0, {}),
    "leading": ("economic_indicators", "leading", 1, {}),
    "coincident": ("economic_indicators", "coincident", 1, {}),
    "exports": ("trade_headline", "exports", 1, {"series": "abs"}),
    "imports": ("trade_headline", "imports", 1, {"series": "abs"}),
    "wrt": ("iowrt", "sales", 1, {"series": "abs"}),
}

client2 = OpenDOSMClient()
filtered = {}
for name, (did, col, tcode, filters) in MONTHLY.items():
    df = cache.get(did)
    if df is None:
        df = client2.fetch(did, limit=20000)
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

monthly_names = sorted(filtered.keys())

dfm_results = {}
for label, df in component_data.items():
    demand_col = df.copy()
    demand_col[label] = demand_col[label] / 100.0

    all_dfs = list(filtered.values()) + [demand_col]
    max_dates = [d["date"].max() for d in all_dfs]
    gdp_start = max(demand_col["date"].min(), pd.Timestamp("2018-01-01"))
    end_dt = max(max_dates)
    datet = generate_dates(gdp_start.year, gdp_start.month, end_dt.year, end_dt.month)
    T = len(datet)
    nM = len(monthly_names)
    X = np.full((T, nM + 1), np.nan)

    for j, name in enumerate(monthly_names):
        df_m = filtered[name]
        for _, row in df_m.iterrows():
            y, m = row["date"].year, row["date"].month
            idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
            if len(idx) > 0:
                X[idx[0], j] = row[name]

    for _, row in demand_col.iterrows():
        y, m = row["date"].year, row["date"].month
        q_end_m = ((m - 1) // 3) * 3 + 3
        idx = np.where((datet[:, 0] == y) & (datet[:, 1] == q_end_m))[0]
        if len(idx) > 0:
            X[idx[0], -1] = row[label]

    X_trans = X.copy()
    for j, name in enumerate(monthly_names):
        tcode = MONTHLY[name][2]
        X_trans[:, j] = transform_series(X[:, j].copy(), tcode, "monthly")
    X_trans[:, -1] = X[:, -1].copy()

    mu = np.nanmean(X_trans, axis=0)
    sigma = np.nanstd(X_trans, axis=0)
    sigma[sigma < 1e-10] = 1.0
    X_std = (X_trans - mu) / sigma
    ff = np.where(~np.all(np.isnan(X_std), axis=1))[0][0]
    X_est = X_std[ff:]

    try:
        dfm = DFM(DFMParams(r=3, p=2, max_iter=50, thresh=1e-5, idio=1))
        res = dfm.fit(X_est)
        gdp_smoothed = res.X_sm[:, -1] * sigma[-1] + mu[-1]

        # Extract quarterly forecasts (at quarter-end months)
        y_actual = []
        y_dfm = []
        for i in range(len(X_est)):
            if datet[ff + i, 1] % 3 == 0:  # quarter-end
                if not np.isnan(X_est[i, -1]):
                    y_actual.append((X_est[i, -1] * sigma[-1] + mu[-1]) * 100)  # unstandardize to %
                    y_dfm.append(gdp_smoothed[i] * 100)

        if len(y_actual) >= 5:
            ya = np.array(y_actual)
            yd = np.array(y_dfm)
            dfm_results[label] = {
                "mae": compute_mae(ya, yd),
                "rmse": compute_rmse(ya, yd),
                "fda": compute_fda(ya, yd),
                "n": len(ya),
            }
        else:
            dfm_results[label] = {"mae": np.nan, "rmse": np.nan, "fda": np.nan, "n": 0}
    except Exception as e:
        dfm_results[label] = {"mae": np.nan, "rmse": np.nan, "fda": np.nan, "n": 0}

client2.close()

# ---------------------------------------------------------------------------
# 4. Comparison table
# ---------------------------------------------------------------------------
console.print()
table = Table(title="DFM vs AR(1) — GDP Component Nowcasting (YoY %)")
table.add_column("Component", style="bold")
table.add_column("AR(1) MAE (pp)", justify="right")
table.add_column("AR(1) FDA (%)", justify="right")
table.add_column("DFM MAE (pp)", justify="right")
table.add_column("DFM FDA (%)", justify="right")
table.add_column("Winner", justify="center")

for label in COMPONENTS:
    a = ar1_results.get(label, {})
    d = dfm_results.get(label, {})

    ar1_mae = f"{a['mae']:.1f}" if not np.isnan(a.get('mae', np.nan)) else "—"
    ar1_fda = f"{a['fda']:.0%}" if not np.isnan(a.get('fda', np.nan)) else "—"
    dfm_mae = f"{d['mae']:.1f}" if not np.isnan(d.get('mae', np.nan)) else "—"
    dfm_fda = f"{d['fda']:.0%}" if not np.isnan(d.get('fda', np.nan)) else "—"

    am = a.get('mae', 99)
    dm = d.get('mae', 99)
    if np.isnan(am) or np.isnan(dm):
        winner = "—"
    elif dm < am:
        winner = "DFM"
    elif am < dm:
        winner = "AR(1)"
    else:
        winner = "Tie"

    style = "green" if winner == "DFM" else "yellow" if winner == "AR(1)" else ""

    table.add_row(label, ar1_mae, ar1_fda, dfm_mae, dfm_fda, winner, style=style)

console.print(table)

# Summary
console.print()
console.print("[bold]Interpretation:[/bold]")
console.print("  DFM wins = the 14 monthly indicators add value beyond simple trend extrapolation")
console.print("  AR(1) wins = the component is mostly momentum-driven; monthly data adds noise")
console.print(f"  AR(1) evaluation uses expanding window from Q12 onward ({ar1_results.get('GDP (e0)', {}).get('n', '?')} forecast periods)")
