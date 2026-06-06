# Methodology

**Last updated:** 2026-06-06

This document describes the methodology used in the Malaysia GDP Nowcasting system.

---

## 1. Overview

The system produces real-time nowcasts of Malaysian GDP growth (YoY %) using three statistical models and an ensemble. It runs daily via GitHub Actions, fetching fresh data from public APIs and publishing results to a dashboard.

**Target variable:** Quarterly real GDP, YoY growth (%)

---

## 2. Models

### 2.1 Dynamic Factor Model (DFM)

Extracts common factors from a panel of monthly indicators using the EM algorithm with Kalman filtering/smoothing.

- **Factors (r):** 2
- **Lags (p):** 4
- **Idiosyncratic:** AR(1)
- **EM convergence:** threshold = 1e-4, max 20 iterations
- **Reference:** Bańbura & Modugno (2014), *J. Applied Econometrics*

### 2.2 Bayesian VAR (BVAR)

Large Bayesian VAR with Minnesota prior, optimized using csminwel (Chris Sims' BFGS variant).

- **Lags:** 2
- **Prior:** Minnesota (Litterman) with dummy observations
- **Gibbs sampler:** 20 draws, 5 burn-in
- **Optimizer:** csminwel, max 5 iterations, threshold 1e-5
- **Reference:** Cimadomo et al. (2022), *J. Econometrics*

### 2.3 Bridge Equations (BEQ)

Individual bridge regressions per indicator, combined via median. Missing values filled with BVAR interpolation.

- **Monthly lags:** 1
- **Quarterly lags:** 1
- **Endogenous lags:** 1
- **Interpolation:** BVAR-based (type 901)
- **Reference:** Bańbura et al. (2023), ECB Working Paper No. 2815

### 2.4 AR(1) Benchmark

Persistence forecast: predicts current quarter = last known quarter.

---

## 3. Ensemble

The ensemble combines predictions from DFM, BVAR, and BEQ using a direction-aware hybrid method:

1. **Models agree on direction** (all positive or all negative): Inverse MAE² weighted average
2. **Models disagree on direction:** Direction vote — pick majority direction, then average concordant predictions

Additional ensemble methods available:
- `median`: Simple median (robust to outliers)
- `mean`: Simple mean
- `inverse_mae`: Inverse MAE² weighting (requires history)
- `inverse_mse`: Inverse MSE weighting (penalizes large errors)
- `direction_vote`: Majority direction, then mean of concordant
- `trimmed_mean`: Remove min/max, then mean

---

## 4. Data Sources

| Source | Indicators | Frequency |
|--------|------------|-----------|
| **OpenDOSM** | IPI, CPI, PPI, labour, trade, WRT, economic indicators | Monthly |
| **BNM OpenAPI** | Interbank rate, MYR/USD exchange rate | Daily |
| **Yahoo Finance** | SP500, Shanghai, SOX, KLCI, STI, Brent, CPO, BDRY | Daily |
| **FRED** | US Industrial Production, US Consumer Sentiment | Monthly |
| **DOSM ARC** | Publication dates for vintage construction | ICS feed |

**Total indicators:** 25+ monthly/quarterly variables

---

## 5. Data Transformations

| Code | Name | Formula | Use Case |
|------|------|---------|----------|
| 0 | Level | No transform | Rates (unemployment, interest) |
| 1 | MoM | log(x[t]) - log(x[t-1]) | Prices, trade, indices |
| 2 | Diff | x[t] - x[t-1] | Stationary series |
| 3 | QoQ Ann | (log(x[t]) - log(x[t-1])) × 4 | Quarterly GDP |
| 4 | YoY | log(x[t]) - log(x[t-12]) | Annual growth |

---

## 6. Vintage Construction

For backtesting, the system uses the DOSM Advance Release Calendar (ARC) to simulate real-time data availability:

1. Parse ARC ICS feed for exact publication dates
2. At each vintage date, mask data not yet published
3. Re-standardize per-vintage (no look-ahead bias)
4. Fit model and extract nowcast

---

## 7. Scoring

### 7.1 Metrics

| Metric | Formula | Interpretation |
|--------|---------|----------------|
| MAE | Mean absolute error | Lower is better |
| RMSE | Root mean squared error | Lower is better |
| FDA | Fraction correct sign | Higher is better (50% = coin flip) |
| MASE | MAE / MAE_naive | <1 = better than persistence |
| Bias | Mean signed error | 0 = unbiased |

### 7.2 Scoring Process

1. Daily nowcasts are logged to `docs/daily_log.csv`
2. Actuals are frozen at first release in `docs/actuals_vintage.csv`
3. Scoring joins nowcasts with actuals on target quarter
4. Requires 3+ scored quarters for leaderboard entry

---

## 8. Consensus Forecasts

Trading Economics consensus forecasts are fetched daily for comparison:

- **GDP YoY:** Direct from TE forecast table
- **Components:** Level forecasts from TE, converted to YoY using DOSM actuals as base
- **Cache:** Consensus data cached to `docs/consensus_cache.json` for CI fallback

---

## 9. Pipeline Flow

```
1. Fetch data (OpenDOSM, BNM, Yahoo Finance, FRED)
2. Build monthly grid (T × N matrix)
3. Apply transforms (MoM, YoY, etc.)
4. Standardize (z-score)
5. Run models (DFM, BVAR, BEQ)
6. Compute ensemble
7. Score against actuals
8. Generate dashboard (HTML + JSON)
9. Publish to GitHub Pages
```

---

## 10. References

1. Bańbura, M., & Modugno, M. (2014). *J. Applied Econometrics*, 29(11), 133–160.
2. Cimadomo, J., et al. (2022). *J. Econometrics*, 231(2), 500–519.
3. Bańbura, M., et al. (2023). ECB Working Paper No. 2815.
4. Linzenich, J., & Meunier, B. (2024). ECB Working Paper No. 3004.
