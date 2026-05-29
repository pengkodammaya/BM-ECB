# Malaysia GDP Nowcasting — Dashboard

> *Comparable to [OpenDOSM GDP Dashboard](https://open.dosm.gov.my/dashboard/gdp)*

**Last updated:** 2026-05-28 | **Latest actual:** Q1 2026 | **Nowcasting:** Q2 2026

---

## How is GDP trending?

### Q1 2026 Actual (YoY)

| | Value | Source |
|---|:---:|---|
| **GDP Growth** | **`+5.4%`** | DOSM Official |

### Q2 2026 Nowcast (YoY) — No ground truth yet

| Model | Nowcast | Description |
|-------|:-------:|-------------|
| **DFM** | `+9.9%` | Dynamic Factor Model (r=2, p=4) |
| **BVAR** | `+4.2%` | Bayesian VAR with Minnesota prior |
| **Ensemble** | `+7.0%` | Median of DFM + BVAR |

> *Q2 2026 actual releases ~August 2026. Nowcasts cannot be validated yet.*

---

## Backcast Accuracy — Q1 2026

*How well models estimated Q1 2026. Actual: `+5.4%` YoY.*

| Model | Estimate | Error | Accuracy |
|-------|:--------:|:-----:|----------|
| **DFM** | +9.9% | 4.5pp | 🔴 Fair |
| **BVAR** | +4.2% | 1.2pp | 🟡 Good |
| **Ensemble** | +7.0% | 1.6pp | 🟡 Good |

---

## A deeper look at GDP by economic sector

*Q1 2026 | YoY Growth | Source: DOSM `gdp_qtr_real_supply`*

| Sector | YoY % |
|--------|:-----:|
| Agriculture | `+2.6%` |
| Mining & Quarrying | `-2.1%` |
| Manufacturing | `+5.9%` |
| Construction | `+7.7%` |
| Services | `+5.6%` |
| **Overall GDP** | **`+5.4%`** |

---

## A deeper look at GDP by expenditure category

*Q1 2026 | YoY Growth | BVAR primary model*

| Component | BVAR | Actual | Error |
|-----------|:----:|:------:|:-----:|
| **Consumption** (C) | +4.8% | +4.7% | 0.1pp |
| **Investment** (I) | +7.3% | +7.3% | 0.0pp |
| **Government** (G) | +4.1% | +4.1% | 0.0pp |
| **Exports** (X) | +5.2% | +5.2% | 0.0pp |
| **Imports** (M) | +4.6% | +4.6% | 0.0pp |

---

## Model Accuracy (Rolling)

*Daily nowcast accuracy vs DOSM actuals. Lower MAE = better. Higher FDA = better.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|:--------:|:---------:|:-------:|:-:|:------:|
| DFM | 3.450 | 3.831 | 0.0% | 3 | +5.8% |
| BVAR | 0.920 | 0.920 | 0.0% | 3 | +0.9% |
| BEQ | 1.090 | 1.090 | 0.0% | 3 | +1.1% |
| AR1 *(baseline)* | 1.470 | 1.470 | 100.0% | 3 | +1.5% |
| ENSEMBLE *(combined)* | 1.190 | 1.198 | 0.0% | 3 | +1.4% |

---

## Recent Nowcasts

| Date | DFM | BVAR | BEQ | Ensemble | Actual |
|------|:---:|:----:|:---:|:--------:|:------:|
| 2026-05-26 | +2.1% | +0.9% | +1.1% | +1.1% | -0.0% |
| 2026-05-27 | +2.4% | +0.9% | +1.1% | +1.1% | -0.0% |
| 2026-05-28 | +5.8% | +0.9% | +1.1% | +1.4% | -0.0% |

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
