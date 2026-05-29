# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-05-29 | **Latest actual:** Q1 2026 | **Nowcasting:** Q2 2026

## GDP Nowcast (YoY %)

*Nowcasting Q2 2026 — no ground truth available yet (releases ~mid-8).*

| Model | Nowcast |
|-------|--------|
| DFM | `+7.3%` |
| BVAR | `+4.1%` |
| ENSEMBLE | `+5.7%` |

## Backcast Accuracy (Q1 2026, YoY %)

*How well models estimated Q1 2026. DOSM actual: `+5.4%`.*

| Model | Estimate | Error |
|-------|----------|-------|
| DFM | `+7.3%` | 1.9pp |
| BVAR | `+4.1%` | 1.3pp |
| ENSEMBLE | `+5.7%` | 0.3pp |

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
| **Private Consumption** (C) | +4.8% | +5.5% | +4.7% | 0.1pp |
| **Gross Fixed Capital Formation** (I) | +7.3% | +5.2% | +7.3% | 0.0pp |
| **Government Consumption** (G) | +4.1% | +4.7% | +4.1% | 0.0pp |
| **Exports** (X) | +5.2% | +4.0% | +5.2% | 0.0pp |
| **Imports** (M) | +4.6% | +4.7% | +4.6% | 0.0pp |

## Model Accuracy (Rolling)

*Daily nowcast accuracy vs DOSM actuals. Metrics appear after 3+ days.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | 3.725 | 4.023 | 0.0% | 4 | +4.5% |
| BVAR | 0.918 | 0.918 | 33.3% | 4 | +0.9% |
| BEQ | 1.090 | 1.090 | 33.3% | 4 | +1.1% |
| AR1 | 1.470 | 1.470 | 100.0% | 4 | +1.5% |
| NAIVE *(last Q)* | 0.000 | 0.000 | 100.0% | 3 | -0.0% |
| ENSEMBLE *(combined)* | 1.175 | 1.182 | 0.0% | 4 | +1.1% |

## Recent Nowcasts (4 days)

| Date | DFM | BVAR | BEQ | AR(1) | NAIVE | ENSEMBLE | Actual |
|------|-----|------|-----|-------|-------|----------|--------|
| 2026-05-26 | +2.1% | +0.9% | +1.1% | +1.5% | — | +1.1% | -0.0% |
| 2026-05-27 | +2.4% | +0.9% | +1.1% | +1.5% | -0.0% | +1.1% | -0.0% |
| 2026-05-28 | +5.8% | +0.9% | +1.1% | +1.5% | -0.0% | +1.4% | -0.0% |
| 2026-05-29 | +4.5% | +0.9% | +1.1% | +1.5% | -0.0% | +1.1% | -0.0% |

## Data Sources

- **GDP (YoY):** DOSM `gdp_qtr_real` — non-SA, constant 2015 prices
- **Sectors:** DOSM `gdp_qtr_real_supply` — supply-side breakdown
- **Expenditure:** DOSM `gdp_qtr_real_demand` — demand-side breakdown
- **Dashboard:** [OpenDOSM GDP](https://open.dosm.gov.my/dashboard/gdp)
- **API:** [OpenDOSM Developer](https://developer.data.gov.my/static-api/opendosm)
- **Last updated:** 2026-05-29

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
