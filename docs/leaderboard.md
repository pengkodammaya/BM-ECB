# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-05-27 | **Nowcasting:** Q2 2026 | **Reference:** DOSM Actual (latest: Q1 2026) — advance for Q2 2026 pending

## Current Quarter Nowcast (QoQ SA %)

*Nowcasting GDP for **Q2 2026**. Advance estimate expected ~mid-7.*

- **DFM:** `+2.39%`
- **BVAR:** `+0.91%` (CI: `-2.0%` to `-2.0%`)
- **BEQ:** `+1.07%`
- **NAIVE:** `-0.01%`
- **ENSEMBLE:** `+1.07%`

*Reference (best available): `-0.0%` — DOSM Actual (latest: Q1 2026) — advance for Q2 2026 pending*

**Closest to reference:** NAIVE (+0.00pp err)

## Backcast: Q1 2026 (QoQ SA %)

*Model estimate for the most recent quarter with released GDP.*

- **DFM:** `+2.06%`
- **BVAR:** `+0.95%`
- **BEQ:** `+1.06%`

*DOSM official: `-0.0%`*

## 1-Quarter-Ahead Forecast: Q3 2026 (QoQ SA %)

- **DFM:** `+1.12%`
- **BVAR:** `+0.53%`
- **BEQ:** `+1.06%`

## Model Leaderboard

*Daily nowcast accuracy vs best available reference. Metrics appear after 3+ days.*

*Leaderboard requires 3+ daily observations. Currently: 2. First metrics expected soon.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | — | — | — | 2 | +2.4% |
| BVAR | — | — | — | 2 | +0.9% |
| BEQ | — | — | — | 2 | +1.1% |
| AR(1) *(baseline)* | — | — | — | 2 | — |
| NAIVE *(last Q)* | — | — | — | 2 | -0.0% |
| ENSEMBLE *(combined)* | — | — | — | 2 | +1.1% |

## Recent Nowcasts (2 days)

| Date | DFM | BVAR | BEQ | AR(1) | NAIVE | ENSEMBLE | Reference |
|------|-----|------|-----|-------|-------|----------|----------|
| 2026-05-26 | +2.1% | +0.9% | +1.1% | +1.5% | — | -0.0% |

## Component Leaderboard (YoY %)

| 2026-05-27 | +2.4% | +0.9% | +1.1% | +1.5% | -0.0% | -0.0% |

## Component Leaderboard (YoY %)

*DFM nowcast vs AR(1) baseline for each expenditure component. Actual values are the latest from DOSM API (Q1 2026, released May 15).*

### Consumption (Private) (C)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| NAIVE *(last Q)* |  🟢 +4.7% (+0.0pp) | `+4.7%` |
| BVAR |  🟡 +4.7% (+0.0pp) | `+4.7%` |
| AR(1) *(baseline)* |  🟠 +5.1% (+0.4pp) | `+4.7%` |
| DFM |  🟤 +5.2% (+0.5pp) | `+4.7%` |

### Government Spending (G)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| NAIVE *(last Q)* |  🟢 +4.1% (+0.0pp) | `+4.1%` |
| BVAR |  🟡 +4.1% (+0.0pp) | `+4.1%` |
| AR(1) *(baseline)* |  🟠 +4.3% (+0.2pp) | `+4.1%` |
| DFM |  🟤 +4.7% (+0.6pp) | `+4.1%` |

### Investment (GFCF) (I)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| NAIVE *(last Q)* |  🟢 +7.3% (+0.0pp) | `+7.3%` |
| BVAR |  🟡 +7.3% (+0.0pp) | `+7.3%` |
| AR(1) *(baseline)* |  🟠 +5.4% (+1.9pp) | `+7.3%` |
| DFM |  🟤 +5.2% (+2.1pp) | `+7.3%` |

### Exports (X)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| NAIVE *(last Q)* |  🟢 +5.2% (+0.0pp) | `+5.2%` |
| BVAR |  🟡 +5.2% (+0.0pp) | `+5.2%` |
| AR(1) *(baseline)* |  🟠 +4.9% (+0.3pp) | `+5.2%` |
| DFM |  🟤 +4.1% (+1.1pp) | `+5.2%` |

### Imports (M)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| NAIVE *(last Q)* |  🟢 +4.6% (+0.0pp) | `+4.6%` |
| BVAR |  🟡 +4.6% (+0.0pp) | `+4.6%` |
| DFM |  🟠 +4.7% (+0.1pp) | `+4.6%` |
| AR(1) *(baseline)* |  🟤 +4.8% (+0.2pp) | `+4.6%` |

#### GDP-Identity Derived Imports
- **Imports (identity):** nowcast `+9.8%` vs actual `+4.6%`
- *Derived from C+I+G+X-GDP. Direct DFM was `+4.6%`.*

## Ground Truth Definition

- **Main GDP:** QoQ SA growth from DOSM `gdp_qtr_real_sa` (seasonally adjusted, constant 2015 prices)
- **Components:** YoY growth from DOSM `gdp_qtr_real_demand` (expenditure approach, non-SA)
- **Source:** [OpenDOSM API](https://open.dosm.gov.my) — live data, fetched fresh each run
- **Latest vintage:** 2026-05-27

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
