# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-11-23 | **Latest actual:** Q3 2026 | **Nowcasting:** Q4 2026

## GDP Nowcast (YoY %)

*Nowcasting Q4 2026. Actual releases ~mid-2; scored once published.*

| Model | Nowcast |
|-------|--------|
| DFM | `+14.1%` |
| BVAR | `+5.2%` |
| ENSEMBLE | `+5.2%` |

## GDP by Expenditure Category (YoY %)

*Nowcasts target Q4 2026. "Actual" is the FROZEN first-release value once Q4 2026 publishes; "pending" until then.*

| Component | BVAR | DFM | Actual (target Q) | Error |
|-----------|------|-----|-------------------|-------|
| **Private Consumption** (C) | +4.9% | +12.7% | pending | pending |
| **Gross Fixed Capital Formation** (I) | +5.2% | +3.2% | pending | pending |
| **Government Consumption** (G) | +6.5% | +5.4% | pending | pending |
| **Exports** (X) | +13.6% | +15.5% | pending | pending |
| **Imports** (M) | +11.1% | +8.4% | pending | pending |

## GDP by Economic Sector (YoY %)

| Sector | Latest Actual |
|--------|---------------|
| Agriculture | `+1.4%` |
| Mining & Quarrying | `-6.1%` |
| Manufacturing | `+7.7%` |
| Construction | `+5.9%` |
| Services | `+5.8%` |
| **Overall GDP** | `+5.5%` |

## Model Accuracy (vintage-frozen, quarter-matched)

*MAE/RMSE/FDA vs FIRST-RELEASE actuals, joined on target quarter. Appears after 3+ scored quarters.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N |
|-------|----------|-----------|---------|---|
| DFM | 2.097 | 2.589 | 100.0% | 127 |
| BVAR | 0.937 | 1.103 | 100.0% | 124 |
| BEQ | 1.411 | 1.574 | 100.0% | 108 |
| AR1 | 4.603 | 4.629 | 0.0% | 127 |
| NAIVE | 4.701 | 4.889 | 0.0% | 126 |
| ENSEMBLE | 0.937 | 1.103 | 100.0% | 126 |

## Accuracy by Horizon (QoQ)

*forecast = before quarter; m1/m2/m3 = month within quarter; backcast = after quarter end, pre-release.*

| Model | Horizon | MAE (pp) | N |
|-------|---------|----------|---|
| AR1 | m1 | 4.040 | 31 |
| AR1 | m2 | 4.652 | 36 |
| AR1 | m3 | 4.865 | 60 |
| BEQ | m1 | 1.303 | 31 |
| BEQ | m2 | 1.755 | 35 |
| BEQ | m3 | 1.204 | 42 |
| BVAR | m1 | 0.943 | 31 |
| BVAR | m2 | 1.137 | 36 |
| BVAR | m3 | 0.809 | 57 |
| DFM | m1 | 1.216 | 31 |
| DFM | m2 | 1.744 | 36 |
| DFM | m3 | 2.763 | 60 |
| ENSEMBLE | m1 | 1.006 | 31 |
| ENSEMBLE | m2 | 1.033 | 36 |
| ENSEMBLE | m3 | 0.842 | 59 |
| NAIVE | m1 | 5.510 | 31 |
| NAIVE | m2 | 4.338 | 35 |
| NAIVE | m3 | 4.495 | 60 |

## Recent Nowcasts (30 days)

| Date | Target Q | DFM | BVAR | BEQ | ENSEMBLE |
|------|----------|-----|------|-----|----------|
| 2026-10-25 | 2026-Q4 | +7.2% | +5.6% | +4.5% | +5.6% |
| 2026-10-26 | 2026-Q4 | +6.7% | +5.6% | +4.5% | +5.6% |
| 2026-10-27 | 2026-Q4 | +6.7% | +5.6% | +4.5% | +5.6% |
| 2026-10-28 | 2026-Q4 | +6.6% | +5.5% | +4.5% | +5.5% |
| 2026-10-29 | 2026-Q4 | +6.7% | +5.6% | +4.7% | +5.6% |
| 2026-10-30 | 2026-Q4 | +6.7% | +5.6% | +4.7% | +5.6% |
| 2026-10-31 | 2026-Q4 | +6.7% | +5.6% | +4.7% | +5.6% |
| 2026-11-01 | 2026-Q4 | +7.0% | +5.6% | +4.7% | +5.6% |
| 2026-11-02 | 2026-Q4 | +7.8% | +5.6% | +4.7% | +5.6% |
| 2026-11-03 | 2026-Q4 | +8.8% | +5.6% | +4.6% | +5.6% |
| 2026-11-04 | 2026-Q4 | +9.8% | +5.6% | +4.7% | +5.6% |
| 2026-11-05 | 2026-Q4 | +10.0% | +5.6% | +4.7% | +5.6% |
| 2026-11-06 | 2026-Q4 | +8.8% | +5.6% | +4.7% | +5.6% |
| 2026-11-07 | 2026-Q4 | +9.7% | +5.6% | +4.7% | +5.6% |
| 2026-11-08 | 2026-Q4 | +9.6% | +5.6% | +4.7% | +5.6% |
| 2026-11-09 | 2026-Q4 | +9.6% | +5.6% | +4.7% | +5.6% |
| 2026-11-10 | 2026-Q4 | +11.1% | +5.6% | +4.7% | +5.6% |
| 2026-11-11 | 2026-Q4 | +11.2% | +5.6% | +4.7% | +5.6% |
| 2026-11-12 | 2026-Q4 | +12.5% | +5.6% | +4.7% | +5.6% |
| 2026-11-13 | 2026-Q4 | +11.9% | +5.6% | +4.7% | +5.6% |
| 2026-11-14 | 2026-Q4 | +11.3% | +5.6% | +4.7% | +5.6% |
| 2026-11-15 | 2026-Q4 | +11.4% | +5.6% | +4.7% | +5.6% |
| 2026-11-16 | 2026-Q4 | +11.6% | +5.6% | +4.7% | +5.6% |
| 2026-11-17 | 2026-Q4 | +12.6% | +5.6% | +4.7% | +5.6% |
| 2026-11-18 | 2026-Q4 | +13.0% | +5.6% | +4.8% | +5.6% |
| 2026-11-19 | 2026-Q4 | +13.7% | +5.3% | +4.8% | +5.3% |
| 2026-11-20 | 2026-Q4 | +13.6% | +5.3% | +4.8% | +5.3% |
| 2026-11-21 | 2026-Q4 | +13.3% | +5.2% | +4.8% | +5.2% |
| 2026-11-22 | 2026-Q4 | +12.8% | +5.2% | +4.8% | +5.2% |
| 2026-11-23 | 2026-Q4 | +14.1% | +5.2% | +4.8% | +5.2% |

## Data Sources

- **GDP:** DOSM `gdp_qtr_real` (YoY), `gdp_qtr_real_sa` (QoQ)
- **Expenditure:** DOSM `gdp_qtr_real_demand`; **Sectors:** `gdp_qtr_real_supply`
- **Vintages:** `docs/actuals_vintage.csv` (first-release frozen, revisions tracked)
- **Last updated:** 2026-11-23

---
*Auto-generated daily via GitHub Actions. [Source](https://github.com/pengkodammaya/BM-ECB)*
