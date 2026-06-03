# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-06-03 | **Latest actual:** Q1 2026 | **Nowcasting:** Q2 2026

## GDP Nowcast (YoY %)

*Nowcasting Q2 2026. Actual releases ~mid-8; scored once published.*

| Model | Nowcast |
|-------|--------|
| DFM | `+7.0%` |
| BVAR | `+5.1%` |
| ENSEMBLE | `+6.0%` |

## GDP by Expenditure Category (YoY %)

*Nowcasts target Q2 2026. "Actual" is the FROZEN first-release value once Q2 2026 publishes; "pending" until then.*

| Component | BVAR | DFM | Actual (target Q) | Error |
|-----------|------|-----|-------------------|-------|
| **Private Consumption** (C) | +5.6% | +9.3% | pending | pending |
| **Gross Fixed Capital Formation** (I) | +7.5% | +3.4% | pending | pending |
| **Government Consumption** (G) | +5.8% | +6.7% | pending | pending |
| **Exports** (X) | +5.9% | +3.6% | pending | pending |
| **Imports** (M) | +7.4% | +6.0% | pending | pending |

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

## Recent Nowcasts (8 days)

| Date | Target Q | DFM | BVAR | BEQ | ENSEMBLE |
|------|----------|-----|------|-----|----------|
| 2026-05-26 | 2026-Q2 | +2.1% | +0.9% | +1.1% | +1.1% |
| 2026-05-27 | 2026-Q2 | +2.4% | +0.9% | +1.1% | +1.1% |
| 2026-05-28 | 2026-Q2 | +9.9% | +4.2% | +1.1% | +7.0% |
| 2026-05-29 | 2026-Q2 | +8.2% | +4.2% | +1.1% | +6.2% |
| 2026-05-30 | 2026-Q2 | +9.0% | +4.1% | — | +6.6% |
| 2026-06-01 | 2026-Q2 | +8.5% | +3.9% | — | +6.2% |
| 2026-06-02 | 2026-Q2 | +8.6% | — | — | — |
| 2026-06-03 | 2026-Q2 | +7.0% | +5.1% | — | +6.0% |

## Data Sources

- **GDP:** DOSM `gdp_qtr_real` (YoY), `gdp_qtr_real_sa` (QoQ)
- **Expenditure:** DOSM `gdp_qtr_real_demand`; **Sectors:** `gdp_qtr_real_supply`
- **Vintages:** `docs/actuals_vintage.csv` (first-release frozen, revisions tracked)
- **Last updated:** 2026-06-03

---
*Auto-generated daily via GitHub Actions. [Source](https://github.com/pengkodammaya/BM-ECB)*
