# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-05-28 | **Nowcasting:** Q2 2026 | **Reference:** DOSM Actual (latest: Q1 2026)

## GDP Growth (YoY %)

*Comparable to [OpenDOSM GDP Dashboard](https://open.dosm.gov.my/dashboard/gdp). Data as of Q1 2026.*

| Model | Nowcast | Reference | Error |
|-------|---------|-----------|-------|
| **DFM** | `+9.9%` | `+5.4%` | 4.5pp |
| **BVAR** | `+4.2%` | `+5.4%` | 1.2pp |
| **ENSEMBLE** | `+7.0%` | `+5.4%` | 1.6pp |

*DOSM official YoY: `+5.4%` (Q1 2026)*

## GDP Growth (QoQ SA %)

*Internal tracking metric. Seasonally adjusted, quarter-on-quarter.*

| Model | Nowcast | Backcast | Forecast |
|-------|---------|----------|----------|
| DFM | +5.8% | +2.3% | +0.1% |
| BVAR | +0.9% | +0.9% | +0.5% |
| BEQ | +1.1% | +1.1% | +1.1% |
| ENSEMBLE | +1.4% | — | — |

*DOSM official QoQ SA: `-0.0%` (Q1 2026)*

## GDP by Economic Sector (YoY %)

*Comparable to DOSM "A deeper look at GDP by economic sector". Actual values from `gdp_qtr_real_supply`.*

| Sector | Latest Actual |
|--------|---------------|
| Agriculture | `+2.6%` |
| Mining & Quarrying | `-2.1%` |
| Manufacturing | `+5.9%` |
| Construction | `+7.7%` |
| Services | `+5.6%` |
| **Overall GDP** | `+5.4%` |

## GDP by Expenditure Category (YoY %)

*Comparable to DOSM "A deeper look at GDP by expenditure category". BVAR primary, DFM comparison.*

| Component | BVAR | DFM | Actual | Error (BVAR) |
|-----------|------|-----|--------|--------------|
| **Private Consumption** (C) | +4.8% | +5.2% | +4.7% | 0.0pp |
| **Gross Fixed Capital Formation** (I) | +7.3% | +5.2% | +7.3% | 0.0pp |
| **Government Consumption** (G) | +4.1% | +4.7% | +4.1% | 0.0pp |
| **Exports** (X) | +5.2% | +4.1% | +5.2% | 0.0pp |
| **Imports** (M) | +4.6% | +4.7% | +4.6% | 0.0pp |

## Model Accuracy (Rolling)

*Daily nowcast accuracy vs DOSM actuals. Metrics appear after 3+ days.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | 3.450 | 3.831 | 0.0% | 3 | +5.8% |
| BVAR | 0.920 | 0.920 | 0.0% | 3 | +0.9% |
| BEQ | 1.090 | 1.090 | 0.0% | 3 | +1.1% |
| AR1 | 1.470 | 1.470 | 100.0% | 3 | +1.5% |
| ENSEMBLE *(combined)* | 1.190 | 1.198 | 0.0% | 3 | +1.4% |

## Recent Nowcasts (3 days)

| Date | DFM | BVAR | BEQ | AR(1) | NAIVE | ENSEMBLE | Actual |
|------|-----|------|-----|-------|-------|----------|--------|
| 2026-05-26 | +2.1% | +0.9% | +1.1% | +1.5% | — | +1.1% | -0.0% |
| 2026-05-27 | +2.4% | +0.9% | +1.1% | +1.5% | -0.0% | +1.1% | -0.0% |
| 2026-05-28 | +5.8% | +0.9% | +1.1% | +1.5% | -0.0% | +1.4% | -0.0% |

## Data Sources

- **Main GDP (YoY):** DOSM `gdp_qtr_real` (non-SA, constant 2015 prices)
- **Main GDP (QoQ SA):** DOSM `gdp_qtr_real_sa` (seasonally adjusted)
- **Sectors:** DOSM `gdp_qtr_real_supply` (supply-side, YoY)
- **Expenditure:** DOSM `gdp_qtr_real_demand` (demand-side, YoY)
- **Source:** [OpenDOSM API](https://open.dosm.gov.my) | [Dashboard](https://open.dosm.gov.my/dashboard/gdp)
- **Latest vintage:** 2026-05-28

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
