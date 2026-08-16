# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-08-16 | **Latest actual:** Q2 2026 | **Nowcasting:** Q3 2026

## GDP Nowcast (YoY %)

*Nowcasting Q3 2026. Actual releases ~mid-11; scored once published.*

| Model | Nowcast |
|-------|--------|
| DFM | `+6.9%` |
| BVAR | `+4.8%` |
| ENSEMBLE | `+4.8%` |

## GDP by Expenditure Category (YoY %)

*Nowcasts target Q3 2026. "Actual" is the FROZEN first-release value once Q3 2026 publishes; "pending" until then.*

| Component | BVAR | DFM | Actual (target Q) | Error |
|-----------|------|-----|-------------------|-------|
| **Private Consumption** (C) | +4.1% | +6.9% | pending | pending |
| **Gross Fixed Capital Formation** (I) | +6.5% | +5.8% | pending | pending |
| **Government Consumption** (G) | +4.2% | +4.8% | pending | pending |
| **Exports** (X) | +4.1% | -0.5% | pending | pending |
| **Imports** (M) | +4.3% | +4.8% | pending | pending |

## GDP by Economic Sector (YoY %)

| Sector | Latest Actual |
|--------|---------------|
| Agriculture | `-3.7%` |
| Mining & Quarrying | `+9.2%` |
| Manufacturing | `+7.3%` |
| Construction | `+6.5%` |
| Services | `+5.9%` |
| **Overall GDP** | `+6.0%` |

## Model Accuracy (vintage-frozen, quarter-matched)

*MAE/RMSE/FDA vs FIRST-RELEASE actuals, joined on target quarter. Appears after 3+ scored quarters.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N |
|-------|----------|-----------|---------|---|
| DFM | 3.375 | 3.906 | nan% | 35 |
| BVAR | 1.273 | 1.646 | nan% | 32 |
| BEQ | 2.237 | 2.722 | nan% | 16 |
| AR1 | 4.540 | 4.540 | nan% | 35 |
| NAIVE | 6.010 | 6.010 | nan% | 34 |
| ENSEMBLE | 1.092 | 1.519 | nan% | 34 |

## Accuracy by Horizon (QoQ)

*forecast = before quarter; m1/m2/m3 = month within quarter; backcast = after quarter end, pre-release.*

| Model | Horizon | MAE (pp) | N |
|-------|---------|----------|---|
| AR1 | m2 | 4.540 | 5 |
| AR1 | m3 | 4.540 | 30 |
| BEQ | m2 | 4.922 | 4 |
| BEQ | m3 | 1.342 | 12 |
| BVAR | m2 | 3.146 | 5 |
| BVAR | m3 | 0.926 | 27 |
| DFM | m2 | 3.316 | 5 |
| DFM | m3 | 3.385 | 30 |
| ENSEMBLE | m2 | 2.324 | 5 |
| ENSEMBLE | m3 | 0.879 | 29 |
| NAIVE | m2 | 6.010 | 4 |
| NAIVE | m3 | 6.010 | 30 |

## Recent Nowcasts (30 days)

| Date | Target Q | DFM | BVAR | BEQ | ENSEMBLE |
|------|----------|-----|------|-----|----------|
| 2026-07-18 | 2026-Q3 | +7.2% | +4.6% | +4.1% | +4.6% |
| 2026-07-19 | 2026-Q3 | +7.1% | +4.5% | +4.1% | +4.5% |
| 2026-07-20 | 2026-Q3 | +7.2% | +4.4% | +4.1% | +4.4% |
| 2026-07-21 | 2026-Q3 | +6.2% | +4.6% | +4.1% | +4.6% |
| 2026-07-22 | 2026-Q3 | +6.2% | +4.5% | +4.1% | +4.5% |
| 2026-07-23 | 2026-Q3 | +6.7% | +4.5% | +4.1% | +4.5% |
| 2026-07-24 | 2026-Q3 | +7.1% | +4.5% | +4.1% | +4.5% |
| 2026-07-25 | 2026-Q3 | +7.5% | +4.6% | +4.1% | +4.6% |
| 2026-07-26 | 2026-Q3 | +7.1% | +4.6% | +4.1% | +4.6% |
| 2026-07-27 | 2026-Q3 | +6.8% | +4.6% | +4.1% | +4.6% |
| 2026-07-28 | 2026-Q3 | +6.8% | +4.5% | +4.1% | +4.5% |
| 2026-07-29 | 2026-Q3 | +7.5% | +4.5% | +4.1% | +4.5% |
| 2026-07-30 | 2026-Q3 | +8.1% | +4.5% | +4.1% | +4.5% |
| 2026-07-31 | 2026-Q3 | +7.4% | +4.5% | +4.1% | +4.5% |
| 2026-08-01 | 2026-Q3 | +7.5% | +4.6% | +4.1% | +4.6% |
| 2026-08-02 | 2026-Q3 | +7.5% | +4.6% | +4.1% | +4.6% |
| 2026-08-03 | 2026-Q3 | +4.6% | +4.5% | +4.1% | +4.5% |
| 2026-08-04 | 2026-Q3 | +7.8% | +4.4% | +4.1% | +4.4% |
| 2026-08-05 | 2026-Q3 | +9.5% | +4.5% | +4.1% | +4.5% |
| 2026-08-06 | 2026-Q3 | +9.2% | +4.4% | +4.1% | +4.4% |
| 2026-08-07 | 2026-Q3 | +4.0% | +4.6% | +4.2% | +4.2% |
| 2026-08-08 | 2026-Q3 | +8.7% | +4.5% | +4.1% | +4.5% |
| 2026-08-09 | 2026-Q3 | +8.0% | +4.4% | +4.1% | +4.4% |
| 2026-08-10 | 2026-Q3 | +7.8% | +4.5% | +4.1% | +4.5% |
| 2026-08-11 | 2026-Q3 | +6.6% | +4.5% | +4.1% | +4.5% |
| 2026-08-12 | 2026-Q3 | +6.1% | +4.5% | +4.1% | +4.5% |
| 2026-08-13 | 2026-Q3 | +6.5% | +4.4% | +4.1% | +4.4% |
| 2026-08-14 | 2026-Q3 | +6.5% | +4.4% | +4.1% | +4.4% |
| 2026-08-15 | 2026-Q3 | +7.1% | +4.9% | +4.2% | +4.9% |
| 2026-08-16 | 2026-Q3 | +6.9% | +4.8% | +4.2% | +4.8% |

## Data Sources

- **GDP:** DOSM `gdp_qtr_real` (YoY), `gdp_qtr_real_sa` (QoQ)
- **Expenditure:** DOSM `gdp_qtr_real_demand`; **Sectors:** `gdp_qtr_real_supply`
- **Vintages:** `docs/actuals_vintage.csv` (first-release frozen, revisions tracked)
- **Last updated:** 2026-08-16

---
*Auto-generated daily via GitHub Actions. [Source](https://github.com/pengkodammaya/BM-ECB)*
