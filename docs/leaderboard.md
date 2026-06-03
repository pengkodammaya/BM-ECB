# Malaysia GDP Nowcasting — Leaderboard

**Updated:** 2026-06-03 | **Basis:** YoY % | **Source:** DOSM frozen first-release

---

## 1. Current Nowcast (Q2 2026)

| Model | Nowcast | vs AR(1) | vs DOSM Advance |
|-------|:-------:|:--------:|:---------------:|
| DFM | `+6.3%` | +1.2pp | — |
| BVAR | `+5.1%` | +0.0pp | — |
| AR(1) | `+5.1%` | — | — |
| **Ensemble** | **`+5.7%`** | **+0.6pp** | — |

---

## 2. Per-Vintage Backtest (YoY GDP)

| Vintage | DFM | BVAR | AR(1) | Ensemble | Actual |
|---------|:---:|:----:|:-----:|:--------:|:------:|
| 2024-Q1 | 5.52 | 3.15 | 2.90 | 4.33 | 4.2 |
| 2024-Q2 | 5.83 | 2.89 | 4.20 | 4.36 | 6.0 |
| 2024-Q3 | 6.24 | 4.19 | 6.00 | 5.21 | 5.5 |
| 2024-Q4 | 6.43 | 5.50 | 5.50 | 5.96 | 5.0 |
| 2025-Q1 | 6.25 | 5.07 | 5.00 | 5.66 | 4.4 |
| 2025-Q2 | 6.38 | 4.93 | 4.40 | 5.65 | 4.6 |
| 2025-Q3 | 6.06 | 4.55 | 4.60 | 5.30 | 5.3 |
| 2025-Q4 | 6.07 | 5.39 | 5.30 | 5.73 | 6.2 |
| 2026-Q1 | 6.14 | 6.34 | 6.20 | 6.24 | 5.4 |

---

## 3. Aggregate Metrics (GDP)

| Model | MAE | RMSE | Bias | FDA | MASE | vs AR(1) |
|-------|:---:|:----:|:----:|:---:|:----:|:--------:|
| DFM | 0.991 | 1.159 | +0.924 | 50% | 1.22 | ❌ |
| BVAR | 1.052 | 1.308 | -0.510 | 25% | 1.30 | ❌ |
| AR(1) | 0.811 | 0.929 | -0.278 | 62% | 1.00 | — |
| **Ensemble** | **0.738** | **0.902** | **+0.204** | 37% | **0.91** | ✅ |

---

## 4. Component Metrics (YoY)

| Component | Best Model | MAE | Bias | AR(1) MAE | vs AR(1) |
|-----------|------------|:---:|:----:|:---------:|:--------:|
| Consumption | DFM | 0.48 | -0.29 | 0.85 | ✅ |
| Investment | Ensemble | 2.64 | -0.72 | 3.20 | ✅ |
| Government | DFM | 0.64 | +0.64 | 4.75 | ✅ |
| Exports | AR(1) | 2.75 | -0.15 | 2.75 | — |
| Imports | Ensemble | 3.66 | -3.52 | 4.85 | ✅ |

---

## 5. DOSM ARC (GDP-related)

| Date | Release | Reference |
|------|---------|-----------|
| Aug 14 | GDP Q2 2026 | Q2 2026 |
| Nov 13 | GDP Q3 2026 | Q3 2026 |

---

## Data Sources

- **GDP:** DOSM `gdp_qtr_real` (YoY), `gdp_qtr_real_sa` (QoQ)
- **Expenditure:** DOSM `gdp_qtr_real_demand`
- **Sectors:** DOSM `gdp_qtr_real_supply`
- **Vintages:** `docs/actuals_vintage.csv` (first-release frozen)
- **Last updated:** 2026-06-03

---

*Auto-generated daily via GitHub Actions. [Source](https://github.com/pengkodammaya/BM-ECB)*
