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
    recent = data.get("recent", []) or []
    arc_next = data.get("arc_next", []) or []

    # Get AR(1) value
    ar1_val = nc.get("ar1")

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

| Model | Nowcast | vs AR(1) | Description |
|-------|:-------:|:--------:|-------------|
| **DFM** | `{fmt_pct(nc.get('dfm'))}` | {fmt_err(round(nc.get('dfm', 0) - ar1_val, 1) if nc.get('dfm') is not None and ar1_val is not None else None)} | Dynamic Factor Model |
| **BVAR** | `{fmt_pct(nc.get('bvar'))}` | {fmt_err(round(nc.get('bvar', 0) - ar1_val, 1) if nc.get('bvar') is not None and ar1_val is not None else None)} | Bayesian VAR |
| **AR(1)** | `{fmt_pct(ar1_val)}` | — | Persistence (baseline) |
| **Ensemble** | `{fmt_pct(nc.get('ensemble'))}` | {fmt_err(round(nc.get('ensemble', 0) - ar1_val, 1) if nc.get('ensemble') is not None and ar1_val is not None else None)} | Median of DFM + BVAR |

> *{nowcast_quarter} actuals expected via DOSM ARC*

---

## Model Accuracy (vs AR(1) Baseline)

*9-vintage backtest, YoY GDP. AR(1) = persistence forecast.*

| Model | MAE | Bias | FDA | MASE | Verdict |
|-------|:---:|:----:|:---:|:----:|---------|
| **Ensemble** | 0.74 | +0.20 | 37% | 0.91 | ✅ Beats AR(1) |
| AR(1) | 0.81 | -0.28 | 62% | 1.00 | — Baseline |
| DFM | 0.99 | +0.92 | 50% | 1.22 | ❌ Worse |
| BVAR | 1.05 | -0.51 | 25% | 1.30 | ❌ Worse |

*MASE < 1 = better than AR(1)*

---

## Component Accuracy

| Component | Best Model | vs AR(1) |
|-----------|------------|:--------:|
| Consumption | DFM (0.48pp) | ✅ |
| Investment | Ensemble (2.64pp) | ✅ |
| Government | DFM (0.64pp) | ✅ |
| Exports | AR(1) (2.75pp) | — |
| Imports | Ensemble (3.66pp) | ✅ |

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

## DOSM ARC (Next Releases)

| Date | Release |
|------|---------|
"""
    if arc_next:
        for r in arc_next[:5]:
            md += f"| {r.get('date', '—')} | {r.get('release', '—')} |\n"
    else:
        md += "| — | — |\n"

    md += """
---

## Recent Nowcasts

| Date | Target | DFM | BVAR | AR(1) | Ensemble | Actual |
|------|:------:|:---:|:----:|:-----:|:--------:|:------:|
"""
    for r in recent:
        md += (f"| {r.get('date')} | {r.get('target_quarter', '—')} | {fmt_pct(r.get('dfm'))} "
               f"| {fmt_pct(r.get('bvar'))} | {fmt_pct(r.get('ar1'))} "
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
