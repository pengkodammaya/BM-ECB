# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-05-27 | **Nowcasting:** Q2 2026 | **Reference:** DOSM Actual (latest: Q1 2026) — advance for Q2 2026 pending

## Current Quarter Nowcast (QoQ SA %)

*Nowcasting GDP for **Q2 2026**.*

- **DFM:** `+2.14%`
- **BVAR:** `+0.92%`
- **BEQ:** `+1.09%`
- **ENSEMBLE:** `+1.09%`

*Reference (best available): `-0.0%` — DOSM Actual (latest: Q1 2026)*

**Closest to reference:** BVAR (+0.93pp err)

## Backcast: Q1 2026 (QoQ SA %)

- **DFM:** `+1.78%`
- **BVAR:** `+0.99%`
- **BEQ:** `+1.05%`

*DOSM official: `-0.0%`*

## 1-Quarter-Ahead Forecast: Q3 2026 (QoQ SA %)

- **DFM:** `+1.18%`
- **BVAR:** `+0.53%`
- **BEQ:** `+1.05%`

## Model Leaderboard

*Daily nowcast accuracy vs best available reference. Metrics appear after 3+ days.*

*Leaderboard requires 3+ daily observations. Currently: 1.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | — | — | — | 1 | +2.1% |
| BVAR | — | — | — | 1 | +0.9% |
| BEQ | — | — | — | 1 | +1.1% |
| AR(1) *(baseline)* | — | — | — | 1 | — |
| NAIVE *(last Q)* | — | — | — | 1 | — |
| ENSEMBLE *(combined)* | — | — | — | 1 | +1.1% |

## Recent Nowcasts (1 days)

| Date | DFM | BVAR | BEQ | AR(1) | NAIVE | ENSEMBLE | Reference |
|------|-----|------|-----|-------|-------|----------|----------|
| 2026-05-26 | +2.1% | +0.9% | +1.1% | +1.5% | — | +1.1% | -0.0% |

## Component Leaderboard (YoY %)

*DFM nowcast vs AR(1) vs NAIVE baseline for each expenditure component.*

### Consumption (Private) (C)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| NAIVE *(last Q)* |  🟢 +4.7% (+0.0pp) | `+4.7%` |
| AR(1) *(baseline)* |  🟡 +5.1% (+0.4pp) | `+4.7%` |
| DFM |  🟠 +7.5% (+2.8pp) | `+4.7%` |

### Government Spending (G)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| NAIVE *(last Q)* |  🟢 +4.1% (+0.0pp) | `+4.1%` |
| AR(1) *(baseline)* |  🟡 +4.3% (+0.2pp) | `+4.1%` |
| DFM |  🟠 +4.7% (+0.6pp) | `+4.1%` |

### Investment (GFCF) (I)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| NAIVE *(last Q)* |  🟢 +7.3% (+0.0pp) | `+7.3%` |
| AR(1) *(baseline)* |  🟡 +5.4% (+1.9pp) | `+7.3%` |
| DFM |  🟠 +5.2% (+2.1pp) | `+7.3%` |

### Exports (X)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| NAIVE *(last Q)* |  🟢 +5.2% (+0.0pp) | `+5.2%` |
| AR(1) *(baseline)* |  🟡 +4.9% (+0.3pp) | `+5.2%` |
| DFM |  🟠 +4.0% (+1.2pp) | `+5.2%` |

### Imports (M)

| Model | Nowcast | Reference (Actual) |
|-------|---------|--------------------|
| NAIVE *(last Q)* |  🟢 +4.6% (+0.0pp) | `+4.6%` |
| DFM |  🟡 +4.7% (+0.1pp) | `+4.6%` |
| AR(1) *(baseline)* |  🟠 +4.8% (+0.2pp) | `+4.6%` |


## Ground Truth Definition

- **Main GDP:** QoQ SA growth from DOSM `gdp_qtr_real_sa`
- **Components:** YoY growth from DOSM `gdp_qtr_real_demand`
- **Source:** [OpenDOSM API](https://open.dosm.gov.my)
- **Latest vintage:** 2026-05-27

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
