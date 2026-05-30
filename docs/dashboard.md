# Malaysia GDP Nowcasting — Dashboard

> *Comparable to [OpenDOSM GDP Dashboard](https://open.dosm.gov.my/dashboard/gdp)*

**Last updated:** 2026-05-30 | **Latest actual:** Q1 2026 | **Nowcasting:** Q2 2026

---

## How is GDP trending?

### Q1 2026 Actual (YoY)

| | Value | Source |
|---|:---:|---|
| **GDP Growth** | **`+5.4%`** | DOSM Official |

### Q2 2026 Nowcast (YoY) — No ground truth yet

| Model | Nowcast | 90% Confidence Band | Description |
|-------|:-------:|:-------------------:|-------------|
| **DFM** | `+9.7%` | — | Dynamic Factor Model (r=2, p=4) |
| **BVAR** | `+4.1%` | `[—, —]` | Bayesian VAR with Minnesota prior |
| **Ensemble** | `+6.9%` | — | Median of DFM + BVAR |

> *Q2 2026 actual releases ~August 2026. Nowcasts cannot be validated yet.*
> *BVAR confidence band computed from posterior draws (10th/90th percentiles).*

---

## Backcast Accuracy — Q1 2026

*How well models estimated Q1 2026. Actual: `+5.4%` YoY.*

| Model | Estimate | Error | Accuracy |
|-------|:--------:|:-----:|----------|
| **DFM** | +9.7% | 4.3pp | 🔴 Fair |
| **BVAR** | +4.1% | 1.3pp | 🟡 Good |
| **Ensemble** | +6.9% | 1.5pp | 🟡 Good |

---

## A deeper look at GDP by economic sector

*Q1 2026 | YoY Growth | Source: DOSM `gdp_qtr_real_supply`*

| Sector | Actual | Nowcast | Error |
|--------|:------:|:-------:|:-----:|
| Agriculture | `+2.6%` | `+0.8%` | `1.8pp` |
| Mining & Quarrying | `-2.1%` | `-1.1%` | `1.0pp` |
| Manufacturing | `+5.9%` | `+4.3%` | `1.6pp` |
| Construction | `+7.7%` | `+4.2%` | `3.5pp` |
| Services | `+5.6%` | `+8.5%` | `2.9pp` |
| **Overall GDP** | **`+5.4%`** | **`+4.1%`** | 1.3pp |

---

## A deeper look at GDP by expenditure category

*Q1 2026 | YoY Growth | BVAR primary model*

| Component | BVAR | Actual | Error |
|-----------|:----:|:------:|:-----:|
| **Consumption** (C) | +6.1% | +4.7% | 1.4pp |
| **Investment** (I) | +9.3% | +7.3% | 2.0pp |
| **Government** (G) | +6.6% | +4.1% | 2.5pp |
| **Exports** (X) | +6.3% | +5.2% | 1.1pp |
| **Imports** (M) | +9.0% | +4.6% | 4.4pp |

---

## Model Accuracy (Rolling)

*Daily nowcast accuracy vs DOSM actuals. Lower MAE = better. Higher FDA = better.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|:--------:|:---------:|:-------:|:-:|:------:|
| DFM | 3.046 | 3.347 | 0.0% | 5 | +2.6% |
| BVAR | 0.930 | 0.930 | 0.0% | 4 | +nan% |
| BEQ | 1.088 | 1.088 | 0.0% | 5 | +1.1% |
| AR1 *(baseline)* | 1.470 | 1.470 | 100.0% | 5 | +1.5% |
| NAIVE *(last Q)* | 0.000 | 0.000 | 100.0% | 4 | -0.0% |
| ENSEMBLE *(combined)* | 1.176 | 1.183 | 0.0% | 5 | +1.2% |

---

## Recent Nowcasts

| Date | DFM | BVAR | 90% Band | BEQ | Ensemble | Actual |
|------|:---:|:----:|:--------:|:---:|:--------:|:------:|
| 2026-05-26 | +2.1% | +0.9% | — | +1.1% | +1.1% | -0.0% |
| 2026-05-27 | +2.4% | +0.9% | [-203.0%, -201.0%] | +1.1% | +1.1% | -0.0% |
| 2026-05-28 | +5.8% | +0.9% | [-202.0%, -201.0%] | +1.1% | +1.4% | -0.0% |
| 2026-05-29 | +2.2% | +0.9% | — | +1.1% | +1.0% | -0.0% |
| 2026-05-30 | +2.6% | — | — | +1.1% | +1.2% | -0.0% |

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
