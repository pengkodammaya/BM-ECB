"""Generate markdown dashboard resembling DOSM GDP style.

Run after daily_update.py to create docs/dashboard.md
"""
import sys; sys.path.insert(0, "src")

import json
import pandas as pd
from pathlib import Path
from datetime import datetime

from nowcasting_toolbox.eval.metrics import compute_mae, compute_fda, compute_rmse

# Load daily log
log_path = Path("docs/daily_log.csv")
if not log_path.exists():
    print("No daily_log.csv found. Run daily_update.py first.")
    sys.exit(1)

log = pd.read_csv(log_path)
latest = log.iloc[-1]

# Load leaderboard if exists
lb_path = Path("docs/leaderboard.csv")
leaderboard = []
if lb_path.exists():
    lb = pd.read_csv(lb_path)
    for _, row in lb.iterrows():
        leaderboard.append({
            "model": row["model"],
            "mae": round(row["MAE (pp)"], 3),
            "rmse": round(row["RMSE (pp)"], 3),
            "fda": round(row["FDA (%)"], 1),
            "n": int(row["N"]),
            "latest": round(float(row.get("last_nowcast", 0)), 1),
        })

# Extract values
today_str = str(latest["date"])
actual_yoy = 5.4  # Q1 2026 actual
actual_quarter = "Q1 2026"
nowcast_quarter = "Q2 2026"

dfm_yoy = round(float(latest.get("dfm_yoy", 0)), 1) if pd.notna(latest.get("dfm_yoy")) else None
bvar_yoy = round(float(latest.get("bvar_yoy", 0)), 1) if pd.notna(latest.get("bvar_yoy")) else None
ensemble_yoy = round(float(latest.get("ensemble_yoy", 0)), 1) if pd.notna(latest.get("ensemble_yoy")) else None

# Components
components = {
    "consumption": {
        "bvar": round(float(latest.get("consumption", 0)), 1) if pd.notna(latest.get("consumption")) else None,
        "actual": round(float(latest.get("consumption_actual", 0)), 1) if pd.notna(latest.get("consumption_actual")) else None,
    },
    "investment": {
        "bvar": round(float(latest.get("investment", 0)), 1) if pd.notna(latest.get("investment")) else None,
        "actual": round(float(latest.get("investment_actual", 0)), 1) if pd.notna(latest.get("investment_actual")) else None,
    },
    "government": {
        "bvar": round(float(latest.get("government", 0)), 1) if pd.notna(latest.get("government")) else None,
        "actual": round(float(latest.get("government_actual", 0)), 1) if pd.notna(latest.get("government_actual")) else None,
    },
    "exports": {
        "bvar": round(float(latest.get("exports_comp", 0)), 1) if pd.notna(latest.get("exports_comp")) else None,
        "actual": round(float(latest.get("exports_comp_actual", 0)), 1) if pd.notna(latest.get("exports_comp_actual")) else None,
    },
    "imports": {
        "bvar": round(float(latest.get("imports_comp", 0)), 1) if pd.notna(latest.get("imports_comp")) else None,
        "actual": round(float(latest.get("imports_comp_actual", 0)), 1) if pd.notna(latest.get("imports_comp_actual")) else None,
    },
}

# Compute errors
for k, v in components.items():
    if v["bvar"] is not None and v["actual"] is not None:
        v["error"] = round(abs(v["bvar"] - v["actual"]), 1)
    else:
        v["error"] = None

# Sectors (hardcoded from latest DOSM data)
sectors = {
    "Agriculture": 2.6,
    "Mining & Quarrying": -2.1,
    "Manufacturing": 5.9,
    "Construction": 7.7,
    "Services": 5.6,
}

# Helper functions
def fmt_pct(val):
    if val is None:
        return "—"
    return f"{val:+.1f}%"

def fmt_err(val):
    if val is None:
        return "—"
    return f"{val:.1f}pp"

def accuracy_badge(err):
    if err is None:
        return "—"
    if err < 1:
        return "🟢 Excellent"
    elif err < 2:
        return "🟡 Good"
    else:
        return "🔴 Fair"

def sign(val):
    if val is None:
        return "—"
    return f"{val:+.1f}%"

# Build markdown
md = f"""# Malaysia GDP Nowcasting — Dashboard

> *Comparable to [OpenDOSM GDP Dashboard](https://open.dosm.gov.my/dashboard/gdp)*

**Last updated:** {today_str} | **Latest actual:** {actual_quarter} | **Nowcasting:** {nowcast_quarter}

---

## How is GDP trending?

### Q1 2026 Actual (YoY)

| | Value | Source |
|---|:---:|---|
| **GDP Growth** | **`{fmt_pct(actual_yoy)}`** | DOSM Official |

### Q2 2026 Nowcast (YoY) — No ground truth yet

| Model | Nowcast | 90% Confidence Band | Description |
|-------|:-------:|:-------------------:|-------------|
| **DFM** | `{sign(dfm_yoy)}` | — | Dynamic Factor Model (r=2, p=4) |
| **BVAR** | `{sign(bvar_yoy)}` | `[{sign(round(float(latest.get('bvar_ci_10', 0)) * 100, 1) if pd.notna(latest.get('bvar_ci_10')) else None)}, {sign(round(float(latest.get('bvar_ci_90', 0)) * 100, 1) if pd.notna(latest.get('bvar_ci_90')) else None)}]` | Bayesian VAR with Minnesota prior |
| **Ensemble** | `{sign(ensemble_yoy)}` | — | Median of DFM + BVAR |

> *Q2 2026 actual releases ~August 2026. Nowcasts cannot be validated yet.*
> *BVAR confidence band computed from posterior draws (10th/90th percentiles).*

---

## Backcast Accuracy — {actual_quarter}

*How well models estimated {actual_quarter}. Actual: `{fmt_pct(actual_yoy)}` YoY.*

| Model | Estimate | Error | Accuracy |
|-------|:--------:|:-----:|----------|
| **DFM** | {sign(dfm_yoy)} | {fmt_err(abs(dfm_yoy - actual_yoy) if dfm_yoy else None)} | {accuracy_badge(abs(dfm_yoy - actual_yoy) if dfm_yoy else None)} |
| **BVAR** | {sign(bvar_yoy)} | {fmt_err(abs(bvar_yoy - actual_yoy) if bvar_yoy else None)} | {accuracy_badge(abs(bvar_yoy - actual_yoy) if bvar_yoy else None)} |
| **Ensemble** | {sign(ensemble_yoy)} | {fmt_err(abs(ensemble_yoy - actual_yoy) if ensemble_yoy else None)} | {accuracy_badge(abs(ensemble_yoy - actual_yoy) if ensemble_yoy else None)} |

---

## A deeper look at GDP by economic sector

*{actual_quarter} | YoY Growth | Source: DOSM `gdp_qtr_real_supply`*

| Sector | YoY % |
|--------|:-----:|
| Agriculture | `{sign(sectors['Agriculture'])}` |
| Mining & Quarrying | `{sign(sectors['Mining & Quarrying'])}` |
| Manufacturing | `{sign(sectors['Manufacturing'])}` |
| Construction | `{sign(sectors['Construction'])}` |
| Services | `{sign(sectors['Services'])}` |
| **Overall GDP** | **`{sign(actual_yoy)}`** |

---

## A deeper look at GDP by expenditure category

*{actual_quarter} | YoY Growth | BVAR primary model*

| Component | BVAR | Actual | Error |
|-----------|:----:|:------:|:-----:|
| **Consumption** (C) | {sign(components['consumption']['bvar'])} | {sign(components['consumption']['actual'])} | {fmt_err(components['consumption']['error'])} |
| **Investment** (I) | {sign(components['investment']['bvar'])} | {sign(components['investment']['actual'])} | {fmt_err(components['investment']['error'])} |
| **Government** (G) | {sign(components['government']['bvar'])} | {sign(components['government']['actual'])} | {fmt_err(components['government']['error'])} |
| **Exports** (X) | {sign(components['exports']['bvar'])} | {sign(components['exports']['actual'])} | {fmt_err(components['exports']['error'])} |
| **Imports** (M) | {sign(components['imports']['bvar'])} | {sign(components['imports']['actual'])} | {fmt_err(components['imports']['error'])} |

---

## Model Accuracy (Rolling)

*Daily nowcast accuracy vs DOSM actuals. Lower MAE = better. Higher FDA = better.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|:--------:|:---------:|:-------:|:-:|:------:|
"""

for r in leaderboard:
    model = r["model"]
    note = ""
    if model == "AR1":
        note = " *(baseline)*"
    elif model == "NAIVE":
        note = " *(last Q)*"
    elif model == "ENSEMBLE":
        note = " *(combined)*"
    md += f"| {model}{note} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['fda']:.1f}% | {r['n']} | {sign(r['latest'])} |\n"

md += f"""
---

## Recent Nowcasts

| Date | DFM | BVAR | 90% Band | BEQ | Ensemble | Actual |
|------|:---:|:----:|:--------:|:---:|:--------:|:------:|
"""

for _, row in log.tail(30).iterrows():
    dfm = round(float(row["dfm"]), 1) if pd.notna(row.get("dfm")) else None
    bvar = round(float(row["bvar"]), 1) if pd.notna(row.get("bvar")) else None
    beq = round(float(row["beq"]), 1) if pd.notna(row.get("beq")) else None
    ens = round(float(row["ensemble"]), 1) if pd.notna(row.get("ensemble")) else None
    act = round(float(row["actual_gdp_pct"]), 1) if pd.notna(row.get("actual_gdp_pct")) else None
    ci_10 = round(float(row["bvar_ci_10"]) * 100, 1) if pd.notna(row.get("bvar_ci_10")) else None
    ci_90 = round(float(row["bvar_ci_90"]) * 100, 1) if pd.notna(row.get("bvar_ci_90")) else None
    band = f"[{sign(ci_10)}, {sign(ci_90)}]" if ci_10 is not None and ci_90 is not None else "—"
    md += f"| {row['date']} | {sign(dfm)} | {sign(bvar)} | {band} | {sign(beq)} | {sign(ens)} | {sign(act)} |\n"

md += f"""
---

## Data Sources

| Dataset | Description |
|---------|-------------|
| GDP (YoY) | DOSM `gdp_qtr_real` — non-SA, constant 2015 prices |
| Sectors | DOSM `gdp_qtr_real_supply` — supply-side breakdown |
| Expenditure | DOSM `gdp_qtr_real_demand` — demand-side breakdown |
| Indicators | OpenDOSM, BNM, yfinance (23 monthly indicators) |

**Dashboard:** [OpenDOSM GDP](https://open.dosm.gov.my/dashboard/gdp) | **API:** [Developer Docs](https://developer.data.gov.my/static-api/opendosm) | **Source:** [GitHub](https://github.com/pengkodammaya/BM-ECB)

---

*Auto-generated daily at 8am MYT via GitHub Actions.*
"""

# Write markdown
dashboard_path = Path("docs") / "dashboard.md"
dashboard_path.write_text(md, encoding="utf-8")
print(f"Dashboard written to {dashboard_path} ({len(md)} bytes)")
