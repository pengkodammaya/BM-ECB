# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-05-26 | **Nowcasting:** Q2 2026 | **Reference:** DOSM Actual (latest: Q1 2026) — advance for Q2 2026 pending

## Current Quarter Nowcast (QoQ SA %)

*Nowcasting GDP for **Q2 2026**. Advance estimate expected ~mid-7.*

- **DFM:** `+1.72%`
- **BVAR:** `+0.91%`
- **BEQ:** `+1.09%`
- **ENSEMBLE:** `+1.09%`

*Reference (best available): `-0.0%` — DOSM Actual (latest: Q1 2026) — advance for Q2 2026 pending*

## Backcast: Q1 2026 (QoQ SA %)

*Model estimate for the most recent quarter with released GDP.*

- **DFM:** `-0.49%`
- **BVAR:** `+0.98%`
- **BEQ:** `+1.04%`

*DOSM official: `-0.0%`*

## 1-Quarter-Ahead Forecast: Q3 2026 (QoQ SA %)

- **DFM:** `+1.99%`
- **BVAR:** `+0.52%`
- **BEQ:** `+1.05%`

## Model Leaderboard

*Daily nowcast accuracy vs best available reference. Metrics appear after 3+ days.*

*Leaderboard requires 3+ daily observations. Currently: 1. First metrics expected soon.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | — | — | — | 1 | +1.7% |
| BVAR | — | — | — | 1 | +0.9% |
| BEQ | — | — | — | 1 | +1.1% |
| AR(1) *(baseline)* | — | — | — | 1 | — |
| ENSEMBLE *(combined)* | — | — | — | 1 | +1.1% |

## Recent Nowcasts (1 days)

| Date | DFM | BVAR | BEQ | AR(1) | ENSEMBLE | Reference |
|------|-----|------|-----|-------|----------|----------|
| 2026-05-26 | +1.7% | +0.9% | +1.1% | +1.5% | +1.1% | -0.0% |

## Component Leaderboard (YoY %)

*DFM nowcast vs AR(1) baseline for each expenditure component. Actual values are the latest from DOSM API (Q1 2026, released May 15).*

### Consumption (Private) (C)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| DFM | `+10.2%` | `+4.7%` |
| AR(1) *(baseline)* | `+5.1%` | `+4.7%` |

### Government Spending (G)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| DFM | `+4.7%` | `+4.1%` |
| AR(1) *(baseline)* | `+4.3%` | `+4.1%` |

### Investment (GFCF) (I)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| DFM | `+5.2%` | `+7.3%` |
| AR(1) *(baseline)* | `+5.4%` | `+7.3%` |

### Exports (X)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| DFM | `+3.5%` | `+5.2%` |
| AR(1) *(baseline)* | `+4.9%` | `+5.2%` |

### Imports (M)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| DFM | `+4.5%` | `+4.6%` |
| AR(1) *(baseline)* | `+4.8%` | `+4.6%` |

#### GDP-Identity Derived Imports
- **Imports (identity):** nowcast `+13.8%` vs actual `+4.6%`
- *Derived from C+I+G+X-GDP. Direct DFM was `+4.5%`.*

## Ground Truth Definition

- **Main GDP:** QoQ SA growth from DOSM `gdp_qtr_real_sa` (seasonally adjusted, constant 2015 prices)
- **Components:** YoY growth from DOSM `gdp_qtr_real_demand` (expenditure approach, non-SA)
- **Source:** [OpenDOSM API](https://open.dosm.gov.my) — live data, fetched fresh each run
- **Latest vintage:** 2026-05-26

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
