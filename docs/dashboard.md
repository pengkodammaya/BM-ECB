# Malaysia GDP Nowcasting — Dashboard

> *Comparable to [OpenDOSM GDP Dashboard](https://open.dosm.gov.my/dashboard/gdp)*

**Last updated:** 2026-11-28 | **Latest actual:** Q3 2026 | **Nowcasting:** Q4 2026

---

## How is GDP trending?

### Q3 2026 Actual (YoY)

| | Value | Source |
|---|:---:|---|
| **GDP Growth** | **`+5.5%`** | DOSM Official |

### Q4 2026 Nowcast (YoY) — No ground truth yet

| Model | Nowcast | vs AR(1) | Description |
|-------|:-------:|:--------:|-------------|
| **DFM** | `+9.6%` | 4.1pp | Dynamic Factor Model |
| **BVAR** | `+5.3%` | -0.2pp | Bayesian VAR |
| **AR(1)** | `+5.5%` | — | Persistence (baseline) |
| **Ensemble** | `+5.3%` | -0.2pp | Median of DFM + BVAR |

> *Q4 2026 actuals expected via DOSM ARC*

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

*Q3 2026 | YoY Growth | Source: DOSM `gdp_qtr_real_supply`*

| Sector | Actual | Nowcast | Error |
|--------|:------:|:-------:|:-----:|
| Agriculture | `+1.4%` | `+0.8%` | `0.6pp` |
| Mining & Quarrying | `-6.1%` | `-0.9%` | `5.2pp` |
| Manufacturing | `+7.7%` | `+4.3%` | `3.4pp` |
| Construction | `+5.9%` | `+3.0%` | `2.9pp` |
| Services | `+5.8%` | `+7.5%` | `1.7pp` |
| **Overall GDP** | **`+5.5%`** | **`+5.2%`** | 0.3pp |

---

## A deeper look at GDP by expenditure category

*Q3 2026 | YoY Growth | BVAR primary model*

| Component | BVAR | Actual | Error |
|-----------|:----:|:------:|:-----:|
| **Consumption (C)** | +4.1% | +4.3% | 0.2pp |
| **Investment (I)** | +6.8% | +8.1% | 1.3pp |
| **Government (G)** | +4.2% | +1.2% | 3.0pp |
| **Exports (X)** | +4.2% | +25.2% | 21.0pp |
| **Imports (M)** | +5.1% | +26.7% | 21.6pp |

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
| 2026-10-30 | 2026-Q4 | +6.7% | +5.6% | — | +5.6% | — |
| 2026-10-31 | 2026-Q4 | +6.7% | +5.6% | — | +5.6% | — |
| 2026-11-01 | 2026-Q4 | +7.0% | +5.6% | — | +5.6% | — |
| 2026-11-02 | 2026-Q4 | +7.8% | +5.6% | — | +5.6% | — |
| 2026-11-03 | 2026-Q4 | +8.8% | +5.6% | — | +5.6% | — |
| 2026-11-04 | 2026-Q4 | +9.8% | +5.6% | — | +5.6% | — |
| 2026-11-05 | 2026-Q4 | +10.0% | +5.6% | — | +5.6% | — |
| 2026-11-06 | 2026-Q4 | +8.8% | +5.6% | — | +5.6% | — |
| 2026-11-07 | 2026-Q4 | +9.7% | +5.6% | — | +5.6% | — |
| 2026-11-08 | 2026-Q4 | +9.6% | +5.6% | — | +5.6% | — |
| 2026-11-09 | 2026-Q4 | +9.6% | +5.6% | — | +5.6% | — |
| 2026-11-10 | 2026-Q4 | +11.1% | +5.6% | — | +5.6% | — |
| 2026-11-11 | 2026-Q4 | +11.2% | +5.6% | — | +5.6% | — |
| 2026-11-12 | 2026-Q4 | +12.5% | +5.6% | — | +5.6% | — |
| 2026-11-13 | 2026-Q4 | +11.9% | +5.6% | — | +5.6% | — |
| 2026-11-14 | 2026-Q4 | +11.3% | +5.6% | — | +5.6% | — |
| 2026-11-15 | 2026-Q4 | +11.4% | +5.6% | — | +5.6% | — |
| 2026-11-16 | 2026-Q4 | +11.6% | +5.6% | — | +5.6% | — |
| 2026-11-17 | 2026-Q4 | +12.6% | +5.6% | — | +5.6% | — |
| 2026-11-18 | 2026-Q4 | +13.0% | +5.6% | — | +5.6% | — |
| 2026-11-19 | 2026-Q4 | +13.7% | +5.3% | — | +5.3% | — |
| 2026-11-20 | 2026-Q4 | +13.6% | +5.3% | — | +5.3% | — |
| 2026-11-21 | 2026-Q4 | +13.3% | +5.2% | — | +5.2% | — |
| 2026-11-22 | 2026-Q4 | +12.8% | +5.2% | — | +5.2% | — |
| 2026-11-23 | 2026-Q4 | +14.1% | +5.2% | — | +5.2% | — |
| 2026-11-24 | 2026-Q4 | +14.4% | +5.3% | — | +5.3% | — |
| 2026-11-25 | 2026-Q4 | +11.5% | +5.3% | — | +5.3% | — |
| 2026-11-26 | 2026-Q4 | +10.0% | +5.3% | — | +5.3% | — |
| 2026-11-27 | 2026-Q4 | +10.0% | +5.3% | — | +5.3% | — |
| 2026-11-28 | 2026-Q4 | +9.6% | +5.3% | — | +5.3% | — |

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
