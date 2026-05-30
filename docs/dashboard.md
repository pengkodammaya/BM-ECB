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
| **DFM** | `+9.0%` | — | Dynamic Factor Model (r=2, p=4) |
| **BVAR** | `+4.1%` | `—` | Bayesian VAR with Minnesota prior |
| **Ensemble** | `+6.6%` | — | Median of DFM + BVAR |

> *Q2 2026 actual releases the quarter after it ends; scored once published.*

---

## Backcast Accuracy — Q1 2026

*Nowcasts made for Q1 2026, scored against its YoY actual.*

| Model | Estimate (YoY) | Error | Accuracy |
|-------|:--------------:|:-----:|----------|
| **DFM** | +5.3% | 0.1pp | 🟢 Excellent |
| **BVAR** | +3.4% | 2.0pp | 🔴 Fair |
| **Ensemble** | +4.3% | 1.1pp | 🟡 Good |

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
| **Overall GDP** | **`+5.4%`** | **`+3.4%`** | 2.0pp |

---

## A deeper look at GDP by expenditure category

*Q1 2026 | YoY Growth | BVAR primary model*

| Component | BVAR | Actual | Error |
|-----------|:----:|:------:|:-----:|
| **Consumption (C)** | +4.9% | +4.7% | 0.2pp |
| **Investment (I)** | +9.1% | +7.3% | 1.8pp |
| **Government (G)** | +6.6% | +4.1% | 2.5pp |
| **Exports (X)** | +6.3% | +5.2% | 1.1pp |
| **Imports (M)** | +9.1% | +4.6% | 4.5pp |

---

## Model Accuracy (vintage-frozen, quarter-matched)

*MAE/RMSE/FDA vs FIRST-RELEASE actuals, joined on target quarter. Lower MAE = better.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|:--------:|:---------:|:-------:|:-:|:------:|
| — | — | — | — | 0 | — |

---

## Accuracy by Horizon (QoQ)

*forecast = before quarter; m1/m2/m3 = month within quarter; backcast = after quarter, pre-release.*

| Model | Horizon | MAE (pp) | N |
|-------|:-------:|:--------:|:-:|
| — | — | — | — |

---

## Recent Nowcasts

| Date | Target Q | DFM | BVAR | BEQ | Ensemble | Actual |
|------|:--------:|:---:|:----:|:---:|:--------:|:------:|
| 2026-05-26 | 2026-Q2 | +2.1% | +0.9% | +1.1% | +1.1% | — |
| 2026-05-27 | 2026-Q2 | +2.4% | +0.9% | +1.1% | +1.1% | — |
| 2026-05-28 | 2026-Q2 | +9.9% | +4.2% | +1.1% | +7.0% | — |
| 2026-05-29 | 2026-Q2 | +8.2% | +4.2% | +1.1% | +6.2% | — |
| 2026-05-30 | 2026-Q2 | +9.0% | +4.1% | — | +6.6% | — |

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
