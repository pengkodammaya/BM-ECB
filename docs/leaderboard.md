# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-08-04 | **Latest actual:** Q1 2026 | **Nowcasting:** Q3 2026

## GDP Nowcast (YoY %)

*Nowcasting Q3 2026. Actual releases ~mid-11; scored once published.*

| Model | Nowcast |
|-------|--------|
| DFM | `+7.8%` |
| BVAR | `+4.4%` |
| ENSEMBLE | `+4.4%` |

## GDP by Expenditure Category (YoY %)

*Nowcasts target Q3 2026. "Actual" is the FROZEN first-release value once Q3 2026 publishes; "pending" until then.*

| Component | BVAR | DFM | Actual (target Q) | Error |
|-----------|------|-----|-------------------|-------|
| **Private Consumption** (C) | +4.7% | +8.7% | pending | pending |
| **Gross Fixed Capital Formation** (I) | +7.9% | +5.6% | pending | pending |
| **Government Consumption** (G) | +5.8% | +4.8% | pending | pending |
| **Exports** (X) | +4.9% | +2.7% | pending | pending |
| **Imports** (M) | +7.3% | +5.4% | pending | pending |

## GDP by Economic Sector (YoY %)

| Sector | Latest Actual |
|--------|---------------|
| Agriculture | `+2.6%` |
| Mining & Quarrying | `-2.1%` |
| Manufacturing | `+5.9%` |
| Construction | `+7.7%` |
| Services | `+5.6%` |
| **Overall GDP** | `+5.4%` |

## Model Accuracy (vintage-frozen, quarter-matched)

*MAE/RMSE/FDA vs FIRST-RELEASE actuals, joined on target quarter. Appears after 3+ scored quarters.*

*No quarters scored yet — accumulating nowcasts until target quarters publish.*

## Accuracy by Horizon (QoQ)

*forecast = before quarter; m1/m2/m3 = month within quarter; backcast = after quarter end, pre-release.*

*Not enough scored observations per horizon yet.*

## Recent Nowcasts (30 days)

| Date | Target Q | DFM | BVAR | BEQ | ENSEMBLE |
|------|----------|-----|------|-----|----------|
| 2026-07-06 | 2026-Q3 | +4.4% | +4.6% | +4.3% | +4.4% |
| 2026-07-07 | 2026-Q3 | +4.3% | +4.6% | +4.3% | +4.3% |
| 2026-07-08 | 2026-Q3 | +5.1% | +4.6% | +4.3% | +4.6% |
| 2026-07-09 | 2026-Q3 | +5.3% | +4.6% | +4.3% | +4.6% |
| 2026-07-10 | 2026-Q3 | +5.1% | +4.6% | +4.3% | +4.6% |
| 2026-07-11 | 2026-Q3 | +5.0% | +4.6% | +4.3% | +4.6% |
| 2026-07-12 | 2026-Q3 | +5.1% | +4.6% | +4.3% | +4.6% |
| 2026-07-13 | 2026-Q3 | +5.3% | +4.5% | +4.3% | +4.5% |
| 2026-07-14 | 2026-Q3 | +6.0% | +4.5% | +4.3% | +4.5% |
| 2026-07-15 | 2026-Q3 | +5.9% | +4.5% | +4.3% | +4.5% |
| 2026-07-16 | 2026-Q3 | +6.4% | +4.5% | +4.3% | +4.5% |
| 2026-07-17 | 2026-Q3 | +6.4% | +4.5% | +4.3% | +4.5% |
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

## Data Sources

- **GDP:** DOSM `gdp_qtr_real` (YoY), `gdp_qtr_real_sa` (QoQ)
- **Expenditure:** DOSM `gdp_qtr_real_demand`; **Sectors:** `gdp_qtr_real_supply`
- **Vintages:** `docs/actuals_vintage.csv` (first-release frozen, revisions tracked)
- **Last updated:** 2026-08-04

---
*Auto-generated daily via GitHub Actions. [Source](https://github.com/pengkodammaya/BM-ECB)*
