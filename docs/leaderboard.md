# Malaysia GDP Nowcasting — Live Leaderboard

**Last updated:** 2026-05-26 | **Nowcast quarter:** Q2 2026 | **Source:** [OpenDOSM](https://open.dosm.gov.my) + [BNM](https://apikijangportal.bnm.gov.my)

## Current Quarter Nowcast (QoQ SA %)

*Nowcasting GDP for **Q2 2026**. GDP for this quarter is not yet released.*

- **DFM:** `+3.36%`
- **BVAR:** `+0.07%`
- **BEQ:** `+0.99%`
- **ENSEMBLE:** `+0.99%`

## Backcast: Q1 2026 (QoQ SA %)

*Model estimate for the most recent quarter with released GDP.*

- **DFM:** `+1.25%`
- **BVAR:** `+0.47%`
- **BEQ:** `+0.99%`

*DOSM official (ground truth): `-0.0%`*

## 1-Quarter-Ahead Forecast: Q3 2026 (QoQ SA %)

- **DFM:** `+2.48%`
- **BVAR:** `-0.00%`
- **BEQ:** `+0.99%`

## Model Leaderboard

*Leaderboard requires 3+ daily observations. Currently: 1. First metrics expected soon.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | — | — | — | 1 | +3.4% |
| BVAR | — | — | — | 1 | +0.1% |
| BEQ | — | — | — | 1 | +1.0% |
| ENSEMBLE | — | — | — | 1 | +1.0% |

## Recent Nowcasts (1 days)

| Date | DFM | BVAR | BEQ | ENSEMBLE | Actual |
|------|-----|------|-----|----------|--------|
| 2026-05-26 | +3.4% | +0.1% | +1.0% | +1.0% | -0.0% |

## Component Nowcasts (YoY %)

- **Investment (GFCF):** nowcast `+10.0%` | actual `+7.3%`
- **Exports:** nowcast `+2.8%` | actual `+5.2%`
- **Imports:** nowcast `+2.6%` | actual `+4.6%`

## Ground Truth Definition

- **Main GDP:** QoQ SA growth from DOSM `gdp_qtr_real_sa` (seasonally adjusted, constant 2015 prices)
- **Components:** YoY growth from DOSM `gdp_qtr_real_demand` (expenditure approach, non-SA)
- **Source:** [OpenDOSM API](https://open.dosm.gov.my) — live data, fetched fresh each run
- **Latest vintage:** 2026-05-26

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
