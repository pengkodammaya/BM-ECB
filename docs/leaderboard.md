# Malaysia GDP Nowcasting — Live Leaderboard

**Last updated:** 2026-05-26 | **Nowcast quarter:** Q2 2026 | **Source:** [OpenDOSM](https://open.dosm.gov.my) + [BNM](https://apikijangportal.bnm.gov.my)

## Current Quarter Nowcast (QoQ SA %)

*Nowcasting GDP for **Q2 2026**. GDP for this quarter is not yet released.*

- **DFM:** `+1.76%`
- **BVAR:** `+0.06%`
- **BEQ:** `+1.10%`
- **ENSEMBLE:** `+1.10%`

## Backcast: Q1 2026 (QoQ SA %)

*Model estimate for the most recent quarter with released GDP.*

- **DFM:** `-0.42%`
- **BVAR:** `+0.39%`
- **BEQ:** `+1.03%`

*DOSM official (ground truth): `-0.0%`*

## 1-Quarter-Ahead Forecast: Q3 2026 (QoQ SA %)

- **DFM:** `+1.79%`
- **BVAR:** `-0.02%`
- **BEQ:** `+1.03%`

## Model Leaderboard

*Leaderboard requires 3+ daily observations. Currently: 1. First metrics expected soon.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | — | — | — | 1 | +1.8% |
| BVAR | — | — | — | 1 | +0.1% |
| BEQ | — | — | — | 1 | +1.1% |
| ENSEMBLE | — | — | — | 1 | +1.1% |

## Recent Nowcasts (1 days)

| Date | DFM | BVAR | BEQ | ENSEMBLE | Actual |
|------|-----|------|-----|----------|--------|
| 2026-05-26 | +1.8% | +0.1% | +1.1% | +1.1% | -0.0% |

## Component Nowcasts (YoY %)

- **Consumption (Private):** nowcast `+8.6%` | actual `+4.7%`
- **Government Spending:** nowcast `+4.2%` | actual `+4.1%`
- **Investment (GFCF):** nowcast `+10.0%` | actual `+7.3%`
- **Exports:** nowcast `+3.4%` | actual `+5.2%`
- **Imports (direct model):** nowcast `+3.4%` | actual `+4.6%`
- **Imports (GDP identity):** nowcast `+13.6%` | actual `+4.6%`
  *Derived from: C+I+G+X-GDP identity. Direct model nowcast was `+3.4%`.*

## Ground Truth Definition

- **Main GDP:** QoQ SA growth from DOSM `gdp_qtr_real_sa` (seasonally adjusted, constant 2015 prices)
- **Components:** YoY growth from DOSM `gdp_qtr_real_demand` (expenditure approach, non-SA)
- **Source:** [OpenDOSM API](https://open.dosm.gov.my) — live data, fetched fresh each run
- **Latest vintage:** 2026-05-26

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
