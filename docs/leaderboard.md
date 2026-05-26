# Malaysia GDP Nowcasting — Live Leaderboard

**Last updated:** 2026-05-26 | **Source:** [OpenDOSM](https://open.dosm.gov.my) + [BNM](https://apikijangportal.bnm.gov.my)

## Latest Nowcast

- **DFM:** `+2.23%` QoQ SA
- **BVAR:** `-0.29%` QoQ SA
- **BEQ:** `+1.00%` QoQ SA
- **ENSEMBLE:** `+1.00%` QoQ SA

*Latest actual GDP: -0.0%*

## Model Leaderboard

*Leaderboard requires 3+ daily observations. Currently: 1. First metrics expected soon.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | — | — | — | 1 | +2.2% |
| BVAR | — | — | — | 1 | -0.3% |
| BEQ | — | — | — | 1 | +1.0% |
| ENSEMBLE | — | — | — | 1 | +1.0% |

## Recent Nowcasts (1 days)

| Date | DFM | BVAR | BEQ | ENSEMBLE | Actual |
|------|-----|------|-----|----------|--------|
| 2026-05-26 | +2.2% | -0.3% | +1.0% | +1.0% | -0.0% |

## Component Nowcasts (YoY %)

- **Investment (GFCF):** nowcast `+9.3%` | actual `+7.3%`
- **Exports:** nowcast `+2.9%` | actual `+5.2%`
- **Imports:** nowcast `+6.6%` | actual `+4.6%`

## Ground Truth Definition

- **Main GDP:** QoQ SA growth from DOSM `gdp_qtr_real_sa` (seasonally adjusted, constant 2015 prices)
- **Components:** YoY growth from DOSM `gdp_qtr_real_demand` (expenditure approach, non-SA)
- **Source:** [OpenDOSM API](https://open.dosm.gov.my) — live data, fetched fresh each run
- **Latest vintage:** 2026-05-26

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
