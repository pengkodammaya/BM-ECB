# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-05-30 | **Latest actual:** Q1 2026 | **Nowcasting:** Q2 2026

## GDP Nowcast (YoY %)

*Nowcasting Q2 2026 — no ground truth available yet (releases ~mid-8).*

| Model | Nowcast |
|-------|--------|
| DFM | `+10.5%` |
| BVAR | `+4.1%` |
| ENSEMBLE | `+7.3%` |

## Backcast Accuracy (Q1 2026, YoY %)

*How well models estimated Q1 2026. DOSM actual: `+5.4%`.*

| Model | Estimate | Error |
|-------|----------|-------|
| DFM | `+10.5%` | 5.1pp |
| BVAR | `+4.1%` | 1.3pp |
| ENSEMBLE | `+7.3%` | 1.9pp |

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
| **Private Consumption** (C) | +6.1% | +6.3% | +4.7% | 1.4pp |
| **Gross Fixed Capital Formation** (I) | +9.3% | +2.3% | +7.3% | 2.0pp |
| **Government Consumption** (G) | +6.6% | +4.8% | +4.1% | 2.5pp |
| **Exports** (X) | +6.3% | +4.1% | +5.2% | 1.1pp |
| **Imports** (M) | +9.0% | +4.7% | +4.6% | 4.4pp |

## Model Accuracy (Rolling)

*Daily nowcast accuracy vs DOSM actuals. Metrics appear after 3+ days.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | 3.114 | 3.404 | 0.0% | 5 | +3.0% |
| BVAR | 0.930 | 0.930 | 0.0% | 4 | +nan% |
| BEQ | 1.088 | 1.088 | 0.0% | 5 | +1.1% |
| AR1 *(baseline)* | 1.470 | 1.470 | 100.0% | 5 | +1.5% |
| NAIVE *(last Q)* | 0.000 | 0.000 | 100.0% | 4 | -0.0% |
| ENSEMBLE *(combined)* | 1.182 | 1.190 | 0.0% | 5 | +1.3% |

## Recent Nowcasts (5 days)

| Date | DFM | BVAR | BEQ | AR(1) | NAIVE | ENSEMBLE | Actual |
|------|-----|------|-----|-------|-------|----------|--------|
| 2026-05-26 | +2.1% | +0.9% | +1.1% | +1.5% | — | +1.1% | -0.0% |
| 2026-05-27 | +2.4% | +0.9% | +1.1% | +1.5% | -0.0% | +1.1% | -0.0% |
| 2026-05-28 | +5.8% | +0.9% | +1.1% | +1.5% | -0.0% | +1.4% | -0.0% |
| 2026-05-29 | +2.2% | +0.9% | +1.1% | +1.5% | -0.0% | +1.0% | -0.0% |
| 2026-05-30 | +3.0% | — | +1.1% | +1.5% | -0.0% | +1.3% | -0.0% |

## Data Sources

- **GDP (YoY):** DOSM `gdp_qtr_real` — non-SA, constant 2015 prices
- **Sectors:** DOSM `gdp_qtr_real_supply` — supply-side breakdown
- **Expenditure:** DOSM `gdp_qtr_real_demand` — demand-side breakdown
- **Dashboard:** [OpenDOSM GDP](https://open.dosm.gov.my/dashboard/gdp)
- **API:** [OpenDOSM Developer](https://developer.data.gov.my/static-api/opendosm)
- **Last updated:** 2026-05-30

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
