# Malaysia GDP Nowcasting — Dashboard

> *Comparable to [OpenDOSM GDP Dashboard](https://open.dosm.gov.my/dashboard/gdp)*

**Last updated:** 2026-06-04 | **Latest actual:** Q1 2026 | **Nowcasting:** Q2 2026

---

## How is GDP trending?

### Q1 2026 Actual (YoY)

| | Value | Source |
|---|:---:|---|
| **GDP Growth** | **`+5.4%`** | DOSM Official |

### Q2 2026 Nowcast (YoY) — No ground truth yet

| Model | Nowcast | vs AR(1) | Description |
|-------|:-------:|:--------:|-------------|
| **DFM** | `+6.1%` | 0.7pp | Dynamic Factor Model |
| **BVAR** | `+5.1%` | -0.3pp | Bayesian VAR |
| **AR(1)** | `+5.4%` | — | Persistence (baseline) |
| **Ensemble** | `+5.6%` | 0.2pp | Median of DFM + BVAR |

> *Q2 2026 actuals expected via DOSM ARC*

---

## Model Accuracy (vs AR(1) Baseline)

*9-vintage backtest, YoY GDP. AR(1) = persistence forecast.*

| Model | MAE | Bias | FDA | MASE | Verdict |
|-------|:---:|:----:|:---:|:----:|---------|
| **Ensemble** | 0.74 | +0.20 | 37% | 0.91 | ✅ Beats AR(1) |
| AR(1) | 0.81 | -0.28 | 62% | 1.00 | — Baseline |
| DFM | 0.99 | +0.92 | 50% | 1.22 | ❌ Worse |
| BVAR | 1.05 | -0.51 | 25% | 1.30 | ❌ Worse |

*MASE < 1 = better than AR(1)*

---

## Component Accuracy

| Component | Best Model | vs AR(1) |
|-----------|------------|:--------:|
| Consumption | DFM (0.48pp) | ✅ |
| Investment | Ensemble (2.64pp) | ✅ |
| Government | DFM (0.64pp) | ✅ |
| Exports | AR(1) (2.75pp) | — |
| Imports | Ensemble (3.66pp) | ✅ |

---

## A deeper look at GDP by economic sector

*Q1 2026 | YoY Growth | Source: DOSM `gdp_qtr_real_supply`*

| Sector | Actual | Nowcast | Error |
|--------|:------:|:-------:|:-----:|
| Agriculture | `+2.6%` | `+0.8%` | `1.8pp` |
| Mining & Quarrying | `-2.1%` | `-1.1%` | `1.0pp` |
| Manufacturing | `+5.9%` | `+4.1%` | `1.8pp` |
| Construction | `+7.7%` | `+9.6%` | `1.9pp` |
| Services | `+5.6%` | `+8.2%` | `2.6pp` |
| **Overall GDP** | **`+5.4%`** | **`+3.9%`** | 1.5pp |

---

## A deeper look at GDP by expenditure category

*Q1 2026 | YoY Growth | BVAR primary model*

| Component | BVAR | Actual | Error |
|-----------|:----:|:------:|:-----:|
| **Consumption (C)** | +5.6% | +4.7% | 0.9pp |
| **Investment (I)** | +7.5% | +7.3% | 0.2pp |
| **Government (G)** | +5.8% | +4.1% | 1.7pp |
| **Exports (X)** | +6.0% | +5.2% | 0.8pp |
| **Imports (M)** | +7.5% | +4.6% | 2.9pp |

---

## DOSM ARC (Next Releases)

| Date | Release |
|------|---------|
| 2026-01-16 | Advance Gross Domestic Product (GDP) Estimates Fourth Quarter 2025 |
| 2026-01-23 | Malaysian Economic Indicators: Leading, Coincident & Lagging Indexes, November 2025 |
| 2026-02-13 | Gross Domestic Product Fourth Quarter 2025 |
| 2026-02-20 | Malaysian Economic Indicators: Leading, Coincident & Lagging Indexes, December 2025 |
| 2026-03-19 | Malaysian Economic Indicators: Leading, Coincident & Lagging Indexes, January 2026 |

---

## Recent Nowcasts

| Date | Target | DFM | BVAR | AR(1) | Ensemble | Actual |
|------|:------:|:---:|:----:|:-----:|:--------:|:------:|
| 2026-05-26 | 2026-Q2 | +2.1% | +0.9% | — | +1.1% | — |
| 2026-05-27 | 2026-Q2 | +2.4% | +0.9% | — | +1.1% | — |
| 2026-05-28 | 2026-Q2 | +9.9% | +4.2% | — | +7.0% | — |
| 2026-05-29 | 2026-Q2 | +8.2% | +4.2% | — | +6.2% | — |
| 2026-05-30 | 2026-Q2 | +9.0% | +4.1% | — | +6.6% | — |
| 2026-06-01 | 2026-Q2 | +8.5% | +3.9% | — | +6.2% | — |
| 2026-06-02 | 2026-Q2 | +8.6% | — | — | — | — |
| 2026-06-03 | 2026-Q2 | +6.2% | +5.1% | — | +5.7% | — |
| 2026-06-04 | 2026-Q2 | +6.1% | +5.1% | — | +5.6% | — |

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
