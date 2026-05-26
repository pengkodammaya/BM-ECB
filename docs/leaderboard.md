# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-05-26 | **Nowcasting:** Q2 2026 | **Reference:** DOSM Actual (latest: Q1 2026) — advance for Q2 2026 pending

## Current Quarter Nowcast (QoQ SA %)

*Nowcasting GDP for **Q2 2026**. Advance estimate expected ~mid-7.*

- **DFM:** `+1.81%`
- **BVAR:** `+0.07%`
- **BEQ:** `+1.10%`
- **ENSEMBLE:** `+1.10%`

*Reference (best available): `-0.0%` — DOSM Actual (latest: Q1 2026) — advance for Q2 2026 pending*

## Backcast: Q1 2026 (QoQ SA %)

*Model estimate for the most recent quarter with released GDP.*

- **DFM:** `-0.42%`
- **BVAR:** `+0.38%`
- **BEQ:** `+1.03%`

*DOSM official: `-0.0%`*

## 1-Quarter-Ahead Forecast: Q3 2026 (QoQ SA %)

- **DFM:** `+1.82%`
- **BVAR:** `-0.02%`
- **BEQ:** `+1.03%`

## Model Leaderboard

*Daily nowcast accuracy vs best available reference. Metrics appear after 3+ days.*

*Leaderboard requires 3+ daily observations. Currently: 1. First metrics expected soon.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | — | — | — | 1 | +1.8% |
| BVAR | — | — | — | 1 | +0.1% |
| BEQ | — | — | — | 1 | +1.1% |
| AR(1) *(baseline)* | — | — | — | 1 | — |
| ENSEMBLE *(combined)* | — | — | — | 1 | +1.1% |

## Recent Nowcasts (1 days)

| Date | DFM | BVAR | BEQ | AR(1) | ENSEMBLE | Reference |
|------|-----|------|-----|-------|----------|----------|
| 2026-05-26 | +1.8% | +0.1% | +1.1% | +1.5% | +1.1% | -0.0% |

## Component Nowcasts (YoY %)

- **Consumption (Private):** nowcast `+8.6%` | actual `+4.7%`
- **Government Spending:** nowcast `+4.2%` | actual `+4.1%`
- **Investment (GFCF):** nowcast `+10.1%` | actual `+7.3%`
- **Exports:** nowcast `+3.4%` | actual `+5.2%`
- **Imports (direct model):** nowcast `+3.3%` | actual `+4.6%`
- **Imports (GDP identity):** nowcast `+13.6%` | actual `+4.6%`
  *Derived from: C+I+G+X-GDP identity. Direct model nowcast was `+3.3%`.*

## Ground Truth Definition

- **Main GDP:** QoQ SA growth from DOSM `gdp_qtr_real_sa` (seasonally adjusted, constant 2015 prices)
- **Components:** YoY growth from DOSM `gdp_qtr_real_demand` (expenditure approach, non-SA)
- **Source:** [OpenDOSM API](https://open.dosm.gov.my) — live data, fetched fresh each run
- **Latest vintage:** 2026-05-26

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
