# Malaysia GDP Nowcasting — Live Leaderboard

**Updated:** 2026-05-29 | **Latest actual:** Q1 2026 | **Nowcasting:** Q2 2026

## GDP Nowcast (YoY %)

*Nowcasting Q2 2026 — no ground truth available yet (releases ~mid-8).*

| Model | Nowcast (YoY) | Nowcast (QoQ SA) |
|-------|:-------------:|:----------------:|
| DFM | `+8.2%` | `+2.2%` |
| BVAR | `+4.2%` | `+0.9%` |
| ENSEMBLE | `+6.2%` | `+1.0%` |

*YoY = Year-over-Year (comparable to DOSM reporting). QoQ SA = Quarter-over-Quarter Seasonally Adjusted.*

## Backcast Accuracy — Q1 2026

*How well models estimated Q1 2026. DOSM advance estimate: `+5.3%` YoY.*

| Model | Estimate (YoY) | Error (YoY) | Estimate (QoQ SA) | Error (QoQ SA) |
|-------|:--------------:|:-----------:|:-----------------:|:--------------:|
| DFM | `+8.2%` | 2.9pp | `+2.2%` | 2.2pp |
| BVAR | `+4.2%` | 1.1pp | `+0.9%` | 0.9pp |
| ENSEMBLE | `+6.2%` | 0.9pp | `+1.0%` | 1.0pp |

*DOSM advance estimate for Q1 2026 released 2026-04-17. Official QoQ SA: -0.01%.*

## GDP by Economic Sector (YoY %)

*Comparable to DOSM "A deeper look at GDP by economic sector".*

| Sector | Actual (Q1 2026) | Nowcast (Q2 2026) | Source |
|--------|:----------------:|:-----------------:|--------|
| Agriculture | `+2.8%` | — | DOSM advance |
| Mining & Quarrying | `-1.1%` | — | DOSM advance |
| Manufacturing | `+5.8%` | — | DOSM advance |
| Construction | `+7.8%` | — | DOSM advance |
| Services | `+5.4%` | — | DOSM advance |
| **Overall GDP** | **`+5.3%`** | **`+4.2%`** | DOSM advance / BVAR |

*Sector actuals from DOSM advance estimate (2026-04-17). Sector nowcasts available after daily_update.py runs.*

## GDP by Expenditure Category (YoY %)

*Comparable to DOSM "A deeper look at GDP by expenditure category". BVAR primary, DFM comparison.*

| Component | BVAR | DFM | Actual | Error (BVAR) |
|-----------|------|-----|--------|--------------|
| **Private Consumption** (C) | +6.0% | +5.0% | +4.7% | 1.3pp |
| **Gross Fixed Capital Formation** (I) | +9.3% | +4.2% | +7.3% | 2.0pp |
| **Government Consumption** (G) | +6.6% | +4.7% | +4.1% | 2.5pp |
| **Exports** (X) | +6.3% | +4.0% | +5.2% | 1.1pp |
| **Imports** (M) | +9.0% | +4.7% | +4.6% | 4.4pp |

## Model Accuracy (Backtest)

*12-vintage pseudo-real-time backtest (2023-Q1 to 2025-Q4) with ARC publication lags. Forward-fill only (no data leakage).*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N |
|-------|----------|-----------|---------|---|
| DFM | 1.256 | 1.531 | 45.5% | 12 |
| BVAR | 0.870 | 1.047 | 45.5% | 12 |
| NAIVE *(last Q)* | 0.894 | 1.076 | 40.0% | 11 |

*Note: Previous leaderboard (pre-2026-05-29) had data leakage from `np.interp` — BVAR MAE was 0.005 pp (unrealistic). Corrected to 0.870 pp.*

## Model Accuracy (Rolling — Live Nowcasts)

*Daily nowcast accuracy vs DOSM actuals. Metrics appear after 3+ days.*

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |
|-------|----------|-----------|---------|---|--------|
| DFM | 3.147 | 3.501 | 0.0% | 4 | +2.2% |
| BVAR | 0.930 | 0.930 | 0.0% | 4 | +0.9% |
| BEQ | 1.088 | 1.088 | 0.0% | 4 | +1.1% |
| AR1 | 1.470 | 1.470 | 100.0% | 4 | +1.5% |
| NAIVE *(last Q)* | 0.000 | 0.000 | 100.0% | 3 | -0.0% |
| ENSEMBLE *(combined)* | 1.155 | 1.163 | 0.0% | 4 | +1.0% |

## Recent Nowcasts (4 days)

| Date | DFM | BVAR | BEQ | AR(1) | NAIVE | ENSEMBLE | Actual |
|------|-----|------|-----|-------|-------|----------|--------|
| 2026-05-26 | +2.1% | +0.9% | +1.1% | +1.5% | — | +1.1% | -0.0% |
| 2026-05-27 | +2.4% | +0.9% | +1.1% | +1.5% | -0.0% | +1.1% | -0.0% |
| 2026-05-28 | +5.8% | +0.9% | +1.1% | +1.5% | -0.0% | +1.4% | -0.0% |
| 2026-05-29 | +2.2% | +0.9% | +1.1% | +1.5% | -0.0% | +1.0% | -0.0% |

## Data Sources

- **GDP (YoY):** DOSM `gdp_qtr_real` — non-SA, constant 2015 prices
- **Sectors:** DOSM `gdp_qtr_real_supply` — supply-side breakdown
- **Expenditure:** DOSM `gdp_qtr_real_demand` — demand-side breakdown
- **Dashboard:** [OpenDOSM GDP](https://open.dosm.gov.my/dashboard/gdp)
- **API:** [OpenDOSM Developer](https://developer.data.gov.my/static-api/opendosm)
- **Last updated:** 2026-05-29

---
*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*
