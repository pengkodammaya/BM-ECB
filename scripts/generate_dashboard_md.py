"""Generate markdown dashboard (DOSM-style) from docs/data.json.

data.json is the single source of truth, written by daily_update.py. Reading
from it guarantees dashboard.md never drifts from dashboard.html, and that
quarter labels / actuals roll forward automatically — nothing is hardcoded.

CI-safe: if data.json is missing or malformed, this exits 0 with a warning
instead of failing the GitHub Action.
"""
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dashboard_md")

DATA_PATH = Path("docs/data.json")
OUT_PATH = Path("docs/dashboard.md")


def fmt_pct(v):
    return "—" if v is None else f"{v:+.1f}%"


def fmt_err(v):
    return "—" if v is None else f"{v:.1f}pp"


def badge(err):
    if err is None:
        return "—"
    if err < 1:
        return "🟢 Excellent"
    if err < 2:
        return "🟡 Good"
    return "🔴 Fair"


def main():
    if not DATA_PATH.exists():
        logger.warning("No data.json found — run daily_update.py first. Skipping.")
        return
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("data.json malformed (%s) — skipping dashboard.md.", e)
        return

    today = data.get("lastUpdated", "—")
    target_q = data.get("targetQuarter", "—")
    la = data.get("latestActual", {}) or {}
    actual_quarter = la.get("quarter", "—")
    actual_yoy = la.get("yoy")
    nc = data.get("nowcast", {}) or {}
    nowcast_quarter = nc.get("quarter", "—")
    bc = data.get("backcast", {}) or {}
    components = data.get("components", {}) or {}
    sectors = data.get("sectors", {}) or {}
    sector_nc = data.get("sectorNowcast", {}) or {}
    leaderboard = data.get("leaderboard", []) or []
    by_h = data.get("byHorizon", []) or []
    recent = data.get("recent", []) or []

    ci10, ci90 = nc.get("bvar_ci_10"), nc.get("bvar_ci_90")
    band = f"[{fmt_pct(ci10)}, {fmt_pct(ci90)}]" if (ci10 is not None and ci90 is not None) else "—"

    md = f"""# Malaysia GDP Nowcasting — Dashboard

> *Comparable to [OpenDOSM GDP Dashboard](https://open.dosm.gov.my/dashboard/gdp)*

**Last updated:** {today} | **Latest actual:** {actual_quarter} | **Nowcasting:** {nowcast_quarter}

---

## How is GDP trending?

### {actual_quarter} Actual (YoY)

| | Value | Source |
|---|:---:|---|
| **GDP Growth** | **`{fmt_pct(actual_yoy)}`** | DOSM Official |

### {nowcast_quarter} Nowcast (YoY) — No ground truth yet

| Model | Nowcast | 90% Confidence Band | Description |
|-------|:-------:|:-------------------:|-------------|
| **DFM** | `{fmt_pct(nc.get('dfm'))}` | — | Dynamic Factor Model (r=2, p=4) |
| **BVAR** | `{fmt_pct(nc.get('bvar'))}` | `{band}` | Bayesian VAR with Minnesota prior |
| **Ensemble** | `{fmt_pct(nc.get('ensemble'))}` | — | Median of DFM + BVAR |

> *{nowcast_quarter} actual releases the quarter after it ends; scored once published.*

---

## Backcast Accuracy — {actual_quarter}

*Nowcasts made for {actual_quarter}, scored against its QoQ SA actual.*

| Model | Estimate (QoQ SA) | Error | Accuracy |
|-------|:-----------------:|:-----:|----------|
"""
    for label, key in [("DFM", "dfm"), ("BVAR", "bvar"), ("Ensemble", "ensemble")]:
        d = bc.get(key, {}) or {}
        est, err = d.get("estimate"), d.get("error")
        md += f"| **{label}** | {fmt_pct(est)} | {fmt_err(err)} | {badge(err)} |\n"

    md += f"""
---

## A deeper look at GDP by economic sector

*{actual_quarter} | YoY Growth | Source: DOSM `gdp_qtr_real_supply`*

| Sector | Actual | Nowcast | Error |
|--------|:------:|:-------:|:-----:|
"""
    sector_names = {"agriculture": "Agriculture", "mining": "Mining & Quarrying",
                    "manufacturing": "Manufacturing", "construction": "Construction",
                    "services": "Services"}
    for key, name in sector_names.items():
        act = sectors.get(key)
        ncv = sector_nc.get(key)
        err = round(abs(ncv - act), 1) if (act is not None and ncv is not None) else None
        md += f"| {name} | `{fmt_pct(act)}` | `{fmt_pct(ncv)}` | `{fmt_err(err)}` |\n"
    md += f"| **Overall GDP** | **`{fmt_pct(actual_yoy)}`** | **`{fmt_pct(bc.get('bvar', {}).get('estimate'))}`** | {fmt_err(bc.get('bvar', {}).get('error'))} |\n"

    md += f"""
---

## A deeper look at GDP by expenditure category

*{actual_quarter} | YoY Growth | BVAR primary model*

| Component | BVAR | Actual | Error |
|-----------|:----:|:------:|:-----:|
"""
    comp_names = {"consumption": "Consumption (C)", "investment": "Investment (I)",
                  "government": "Government (G)", "exports": "Exports (X)", "imports": "Imports (M)"}
    for key, name in comp_names.items():
        d = components.get(key, {}) or {}
        md += f"| **{name}** | {fmt_pct(d.get('bvar'))} | {fmt_pct(d.get('actual'))} | {fmt_err(d.get('error'))} |\n"

    md += """
---

## Model Accuracy (vintage-frozen, quarter-matched)

*MAE/RMSE/FDA vs FIRST-RELEASE actuals, joined on target quarter. Lower MAE = better.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|:--------:|:---------:|:-------:|:-:|:------:|
"""
    if leaderboard:
        for r in leaderboard:
            note = {"AR1": " *(baseline)*", "NAIVE": " *(last Q)*",
                    "ENSEMBLE": " *(combined)*"}.get(r.get("model"), "")
            md += (f"| {r.get('model')}{note} | {r.get('mae', 0):.3f} | {r.get('rmse', 0):.3f} "
                   f"| {r.get('fda', 0):.1f}% | {r.get('n', 0)} | {fmt_pct(r.get('latest'))} |\n")
    else:
        md += "| — | — | — | — | 0 | — |\n"

    md += """
---

## Accuracy by Horizon (QoQ)

*forecast = before quarter; m1/m2/m3 = month within quarter; backcast = after quarter, pre-release.*

| Model | Horizon | MAE (pp) | N |
|-------|:-------:|:--------:|:-:|
"""
    if by_h:
        for r in sorted(by_h, key=lambda x: (x.get("model", ""), x.get("horizon", ""))):
            md += f"| {r.get('model')} | {r.get('horizon')} | {r.get('MAE (pp)', 0):.3f} | {r.get('N', 0)} |\n"
    else:
        md += "| — | — | — | — |\n"

    md += """
---

## Recent Nowcasts

| Date | Target Q | DFM | BVAR | BEQ | Ensemble | Actual |
|------|:--------:|:---:|:----:|:---:|:--------:|:------:|
"""
    for r in recent:
        md += (f"| {r.get('date')} | {r.get('target_quarter', '—')} | {fmt_pct(r.get('dfm'))} "
               f"| {fmt_pct(r.get('bvar'))} | {fmt_pct(r.get('beq'))} "
               f"| {fmt_pct(r.get('ensemble'))} | {fmt_pct(r.get('actual'))} |\n")

    md += f"""
---

## Data Sources

| Dataset | Description |
|---------|-------------|
| GDP (YoY) | DOSM `gdp_qtr_real` — non-SA, constant 2015 prices |
| Sectors | DOSM `gdp_qtr_real_supply` — supply-side breakdown |
| Expenditure | DOSM `gdp_qtr_real_demand` — demand-side breakdown |
| Vintages | `docs/actuals_vintage.csv` — first-release frozen, revisions tracked |

**Dashboard:** [OpenDOSM GDP](https://open.dosm.gov.my/dashboard/gdp) | **API:** [Developer Docs](https://developer.data.gov.my/static-api/opendosm) | **Source:** [GitHub](https://github.com/pengkodammaya/BM-ECB)

---

*Auto-generated daily via GitHub Actions.*
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".md.tmp")
    tmp.write_text(md, encoding="utf-8")
    tmp.replace(OUT_PATH)
    logger.info("dashboard.md written (%d bytes).", len(md))


if __name__ == "__main__":
    main()
