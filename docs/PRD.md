# Product Requirements Document (PRD)
## Nowcasting Toolbox — Python Edition (Malaysia)

**Version**: 0.1.0  
**Date**: 24 May 2026  
**Status**: MVP Delivered

---

## 1. Problem Statement

Economic policymakers, analysts, and researchers need real-time estimates of GDP growth to make informed decisions. Official GDP data is released with a 45–60 day lag after each quarter ends. In the interim, monthly indicators (industrial production, inflation, employment, trade) are released at staggered intervals, creating a "ragged edge" of partial information. A nowcasting system extracts the GDP signal from this incomplete data to produce timely, defensible estimates.

The original ECB Nowcasting Toolbox (Linzenich & Meunier, 2024) provides this capability in MATLAB. This project ports it to Python and extends it with a live Malaysian data pipeline.

---

## 2. Target Users

| User | Use Case |
|------|----------|
| Central bank / treasury economists | Real-time GDP monitoring, policy briefings |
| Financial analysts / traders | Tactical positioning ahead of GDP releases |
| Academic researchers | Reproducible nowcasting research, methodological experiments |
| Data journalists | Data-driven economic reporting |

---

## 3. Functional Requirements

### 3.1 Data Pipeline

| ID | Requirement | Priority |
|----|-------------|----------|
| D1 | Fetch macroeconomic indicators from OpenDOSM API (CPI, IPI, PPI, labour, leading/coincident indexes) | P0 |
| D2 | Fetch financial data from Bank Negara Malaysia OpenAPI (exchange rates, OPR, monetary aggregates) | P1 |
| D3 | Parse DOSM Advance Release Calendar for exact publication dates | P1 |
| D4 | Cache fetched data as Parquet files with configurable TTL | P0 |
| D5 | Support local file input: Excel (toolbox format), CSV, Parquet | P0 |
| D6 | Apply stationarity transformations (5 types: level, MoM, diff, QoQ ann, YoY) | P0 |
| D7 | Handle mixed-frequency data (monthly indicators + quarterly GDP) with Mariano-Murasawa approximation | P0 |
| D8 | Automatic ragged-edge construction using publication lags | P0 |

### 3.2 Model Engines

| ID | Requirement | Priority |
|----|-------------|----------|
| M1 | **DFM** — Dynamic Factor Model with EM estimation, Kalman filter/smoother, arbitrary missing data handling (Bańbura & Modugno, 2014) | P0 |
| M2 | **BVAR** — Large Bayesian VAR with Minnesota prior, block structure, hyperparameter optimization (Cimadomo et al., 2022) | P0 |
| M3 | **BEQ** — Bridge Equations ensemble with BVAR-based interpolation, combinatorial specification generation, median combination (Bańbura et al., 2023) | P0 |
| M4 | sklearn-compatible `.fit()` / `.predict()` API for all three models | P0 |
| M5 | Configurable hyperparameters via Pydantic-validated config objects | P0 |

### 3.3 Evaluation & Output

| ID | Requirement | Priority |
|----|-------------|----------|
| E1 | Compute MAE (Mean Absolute Error), RMSE, and FDA (Forecast Directional Accuracy) | P0 |
| E2 | Pseudo-real-time backtest engine with vintage-appropriate data availability | P0 |
| E3 | News decomposition — attribute nowcast revisions to specific data releases | P1 |
| E4 | Model-implied confidence bands (Kalman filter covariance) | P0 |
| E5 | Bootstrapped range estimation (mirrors `common_range.m`) | P1 |
| E6 | Growth-to-level conversion (GDP growth % → MYR billion levels) | P1 |
| E7 | Model leaderboard: comparison table with rankings (terminal + CSV + Excel) | P0 |
| E8 | 3-model ensemble nowcast (simple median of DFM + BVAR + BEQ) | P1 |

### 3.4 CLI & Automation

| ID | Requirement | Priority |
|----|-------------|----------|
| C1 | `nowcast fetch` — pull latest data from APIs to local cache | P0 |
| C2 | `nowcast run` — full pipeline: fetch → transform → nowcast (all models) → leaderboard → export | P0 |
| C3 | `nowcast backtest` — run evaluation over a configurable date window | P0 |
| C4 | `nowcast leaderboard` — print latest comparison table | P0 |
| C5 | `nowcast schedule` — install daily/weekly scheduled task (Windows Task Scheduler / cron) | P1 |
| C6 | Variable selection: `nowcast select-vars` — LARS / t-stat / correlation-based ranking | P2 |
| C7 | JSON/YAML configuration file support | P1 |

### 3.5 Variable Selection

| ID | Requirement | Priority |
|----|-------------|----------|
| V1 | LARS (Least Angle Regression) ranking of candidate regressors | P2 |
| V2 | t-statistic-based univariate ranking | P2 |
| V3 | Correlation-based ranking (Sure Independence Screening) | P2 |
| V4 | Output CSV with ranking, publication delays, group, and frequency | P2 |

---

## 4. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| N1 | Python ≥ 3.10, managed with `uv` for virtual environments |
| N2 | Dependency stack: numpy, scipy, pandas, scikit-learn, statsmodels, pydantic, click, httpx, rich |
| N3 | All numerical routines must handle arbitrary NaN patterns |
| N4 | EM algorithm must converge within 100 iterations on datasets with ≥ 20% missingness |
| N5 | Full nowcast pipeline (fetch + all models) must complete within 5 minutes on a standard laptop |
| N6 | API clients must respect rate limits and use local caching |
| N7 | Test coverage ≥ 60% on core model code |

---

## 5. Data Specification

### 5.1 Target Variable

| Field | Value |
|-------|-------|
| Dataset ID | `gdp_qtr_real_sa` |
| Description | Quarterly Real GDP, seasonally adjusted, constant 2015 prices |
| Frequency | Quarterly (1st month of each quarter in API, shifted to 3rd month in grid) |
| Transformation | Convert absolute levels → QoQ growth rate (decimal), standardize |
| Source | OpenDOSM / DOSM |

### 5.2 Monthly Indicators (Current)

| Variable | Dataset ID | Value Column | Transform | Group |
|----------|-----------|-------------|-----------|-------|
| IPI MoM growth | `ipi` | `index` (series=`growth_mom`) | Level (÷100) | industry |
| CPI Headline | `cpi_headline` | `index` (division=`overall`) | MoM dlog | prices |
| CPI Core | `cpi_core` | `index` (division=`overall`) | MoM dlog | prices |
| PPI | `ppi` | `index` (series=`abs`) | MoM dlog | prices |
| Unemployment Rate | `lfs_month` | `u_rate` | Level | labour |
| Participation Rate | `lfs_month` | `p_rate` | Level | labour |
| Leading Index | `economic_indicators` | `leading` | MoM dlog | leading |
| Coincident Index | `economic_indicators` | `coincident` | MoM dlog | coincident |

### 5.3 Publication Lags (Approximate)

| Variable | Months lag | Release day of month |
|----------|:---------:|:--------------------:|
| IPI | 1 | 8th |
| CPI | 1 | 19th |
| PPI | 1 | 25th |
| Labour | 1 | 12th |
| Leading/Coincident | 2 | 25th |
| GDP | 2 | 15th |

---

## 6. Model Specifications

### 6.1 DFM
- Factors: r = 3 (default), configurable 1–6
- Lags: p = 2 (default), configurable 1–5
- Idiosyncratic: AR(1) for monthly, iid for quarterly (configurable)
- EM convergence: threshold = 1e-5, max 50 iterations
- Block factors: optional, one per economic category

### 6.2 BVAR
- Lags: 5 (default), configurable 2–12
- Prior: Minnesota (Litterman) with dummy observations
- Hyperparameters: λ=0.2 (tightness), μ=1.0 (sum-of-coefficients), θ=1.0 (co-persistence), α=2.0 (block exogeneity)
- Optimizer: csminwel (Chris Sims' BFGS variant)
- Convergence: threshold = 1e-6, max 200 iterations

### 6.3 BEQ
- Monthly lags: 1 (quarterly terms, configurable 0–4)
- Quarterly lags: 1 (configurable 0–4)
- Endogenous lags: 1 (configurable 0–2)
- Interpolation: BVAR-based (3 modes: all-variable, selected-variable, univariate)
- Combination: median of individual bridge equations
- COVID dummies: configurable (2020Q1, Q2, Q3)

---

## 7. Success Metrics

| Metric | Target | Current (DFM only) |
|--------|--------|---------------------|
| Correlation with official SA QoQ GDP | ≥ 0.85 | **0.935** ✓ |
| MAE vs official (ex-COVID) | ≤ 1.5 pp | **1.33 pp** ✓ |
| FDA (directional accuracy) | ≥ 60% | 42% ✗ |
| Pipeline runtime (fetch + nowcast) | ≤ 5 min | ~2 min ✓ |
| API fetch success rate | ≥ 95% | ~90% (BNM untested) |

---

## 8. Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| **MVP** | DFM on Malaysian data, CLI, backtest, leaderboard | ✅ Complete |
| **v0.2** | BVAR + BEQ on live data, 3-model leaderboard, ensemble | 🔲 |
| **v0.3** | BNM financial data, more monthly indicators, COVID handling | 🔲 |
| **v0.4** | Hyperparameter tuning, block factors, ARC live scraping | 🔲 |
| **v1.0** | Production hardening: tests, docs, config files, Docker | 🔲 |

---

## Appendix A: Dependency Stack

```
numpy≥1.24       scipy≥1.10        pandas≥2.0
openpyxl≥3.1     pyarrow≥12.0      scikit-learn≥1.3
statsmodels≥0.14 pydantic≥2.0      click≥8.0
httpx≥0.25       rich≥13.0         pytest≥7.0
matplotlib≥3.7   seaborn≥0.12
```

## Appendix B: References

1. Bańbura, M., & Modugno, M. (2014). "Maximum likelihood estimation of factor models on datasets with arbitrary pattern of missing data." *Journal of Applied Econometrics*, 29(11), 133–160.
2. Cimadomo, J., Giannone, D., Lenza, M., Monti, F., & Sokol, A. (2022). "Nowcasting with large Bayesian vector autoregressions." *Journal of Econometrics*, 231(2), 500–519.
3. Bańbura, M., Belousova, I., Bodnár, K., & Tóth, M. B. (2023). "Nowcasting employment in the euro area." *Working Paper Series*, No 2815, European Central Bank.
4. Linzenich, J., & Meunier, B. (2024). "Nowcasting Made Easier: a Toolbox for Real-Time Predictions." *Working Paper Series*, No 3004, European Central Bank.
5. Delle Chiaie, S., Ferrara, L., & Giannone, D. (2022). "Common factors of commodity prices." *Journal of Applied Econometrics*, 37(3), 461–476.
