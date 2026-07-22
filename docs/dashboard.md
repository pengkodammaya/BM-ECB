# Malaysia GDP Nowcasting — Dashboard

> *Comparable to [OpenDOSM GDP Dashboard](https://open.dosm.gov.my/dashboard/gdp)*

**Last updated:** 2026-07-22 | **Latest actual:** Q1 2026 | **Nowcasting:** Q3 2026

---

## How is GDP trending?

### Q1 2026 Actual (YoY)

| | Value | Source |
|---|:---:|---|
| **GDP Growth** | **`+5.4%`** | DOSM Official |

### Q3 2026 Nowcast (YoY) — No ground truth yet

| Model | Nowcast | vs AR(1) | Description |
|-------|:-------:|:--------:|-------------|
| **DFM** | `+6.2%` | 0.8pp | Dynamic Factor Model |
| **BVAR** | `+4.5%` | -0.9pp | Bayesian VAR |
| **AR(1)** | `+5.4%` | — | Persistence (baseline) |
| **Ensemble** | `+4.5%` | -0.9pp | Median of DFM + BVAR |

> *Q3 2026 actuals expected via DOSM ARC*

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
| Agriculture | `+2.6%` | `+0.9%` | `1.7pp` |
| Mining & Quarrying | `-2.1%` | `-0.7%` | `1.4pp` |
| Manufacturing | `+5.9%` | `+4.3%` | `1.6pp` |
| Construction | `+7.7%` | `+3.5%` | `4.2pp` |
| Services | `+5.6%` | `+7.3%` | `1.7pp` |
| **Overall GDP** | **`+5.4%`** | **`+3.6%`** | 1.8pp |

---

## A deeper look at GDP by expenditure category

*Q1 2026 | YoY Growth | BVAR primary model*

| Component | BVAR | Actual | Error |
|-----------|:----:|:------:|:-----:|
| **Consumption (C)** | +4.8% | +4.7% | 0.1pp |
| **Investment (I)** | +7.5% | +7.3% | 0.2pp |
| **Government (G)** | +5.8% | +4.1% | 1.7pp |
| **Exports (X)** | +4.9% | +5.2% | 0.3pp |
| **Imports (M)** | +7.4% | +4.6% | 2.8pp |

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
| 2026-06-23 | 2026-Q2 | +11.0% | +5.1% | — | +5.1% | — |
| 2026-06-24 | 2026-Q2 | +11.8% | +5.1% | — | +5.1% | — |
| 2026-06-25 | 2026-Q2 | +11.6% | +5.1% | — | +5.1% | — |
| 2026-06-26 | 2026-Q2 | +11.2% | +5.1% | — | +5.1% | — |
| 2026-06-27 | 2026-Q2 | +12.0% | +5.1% | — | +5.1% | — |
| 2026-06-28 | 2026-Q2 | +11.8% | +5.1% | — | +5.1% | — |
| 2026-06-29 | 2026-Q2 | +11.9% | +5.1% | — | +5.1% | — |
| 2026-06-30 | 2026-Q2 | +11.3% | +5.1% | — | +5.1% | — |
| 2026-07-01 | 2026-Q3 | +2.2% | +4.6% | — | +4.3% | — |
| 2026-07-02 | 2026-Q3 | +3.6% | +4.7% | — | +4.3% | — |
| 2026-07-03 | 2026-Q3 | +4.2% | +4.7% | — | +4.3% | — |
| 2026-07-04 | 2026-Q3 | +4.4% | +4.6% | — | +4.4% | — |
| 2026-07-05 | 2026-Q3 | +4.4% | +4.6% | — | +4.4% | — |
| 2026-07-06 | 2026-Q3 | +4.4% | +4.6% | — | +4.4% | — |
| 2026-07-07 | 2026-Q3 | +4.3% | +4.6% | — | +4.3% | — |
| 2026-07-08 | 2026-Q3 | +5.1% | +4.6% | — | +4.6% | — |
| 2026-07-09 | 2026-Q3 | +5.3% | +4.6% | — | +4.6% | — |
| 2026-07-10 | 2026-Q3 | +5.1% | +4.6% | — | +4.6% | — |
| 2026-07-11 | 2026-Q3 | +5.0% | +4.6% | — | +4.6% | — |
| 2026-07-12 | 2026-Q3 | +5.1% | +4.6% | — | +4.6% | — |
| 2026-07-13 | 2026-Q3 | +5.3% | +4.5% | — | +4.5% | — |
| 2026-07-14 | 2026-Q3 | +6.0% | +4.5% | — | +4.5% | — |
| 2026-07-15 | 2026-Q3 | +5.9% | +4.5% | — | +4.5% | — |
| 2026-07-16 | 2026-Q3 | +6.4% | +4.5% | — | +4.5% | — |
| 2026-07-17 | 2026-Q3 | +6.4% | +4.5% | — | +4.5% | — |
| 2026-07-18 | 2026-Q3 | +7.2% | +4.6% | — | +4.6% | — |
| 2026-07-19 | 2026-Q3 | +7.1% | +4.5% | — | +4.5% | — |
| 2026-07-20 | 2026-Q3 | +7.2% | +4.4% | — | +4.4% | — |
| 2026-07-21 | 2026-Q3 | +6.2% | +4.6% | — | +4.6% | — |
| 2026-07-22 | 2026-Q3 | +6.2% | +4.5% | — | +4.5% | — |

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
