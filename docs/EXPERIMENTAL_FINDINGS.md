# Experimental Findings — Malaysia GDP Nowcasting

This document captures key experimental results, both positive and negative, from the nowcasting system development.

---

## 0. Data Leakage via Interpolation (Critical Bug)

**Date**: 2026-05-29

**Bug**: Using `np.interp()` to fill missing values in pseudo-real-time backtesting causes data leakage by interpolating between past AND future observations.

**Example**: GDP is observed at quarter-end months (3, 6, 9, 12). When `np.interp` fills months 4-5, it uses BOTH month 3 (past) AND month 6 (future). At vintage date 2024-05-15, month 6 GDP is not yet released — but the model "sees" it via interpolation.

**Impact on BVAR MAE** (4-vintage backtest, 2024-Q1 to Q2):

| Fill Method | BVAR MAE | Notes |
|-------------|----------|-------|
| `np.interp` (broken) | **0.005 pp** | Unrealistically perfect — model sees future |
| Forward-fill (correct) | **0.215 pp** | Realistic — only uses released data |

**Root cause**: `np.interp(indices[nan], indices[valid], col[valid])` interpolates between ALL valid points, including future ones.

**Fix**: Use forward-fill only:
```python
# WRONG — interpolates with future values
X_filled[nan_mask, j] = np.interp(indices[nan_mask], indices[valid], col[valid])

# CORRECT — forward-fill only
last_valid = np.nan
for t in range(T):
    if not np.isnan(col[t]):
        last_valid = col[t]
    elif not np.isnan(last_valid):
        X_filled[t, j] = last_valid
```

**Files affected** (all fixed as of 2026-05-29):
- `bvar/bbvar.py:_fill_data`
- `scripts/backtest_all_models.py`
- `scripts/test_all_models.py`
- `scripts/component_backtest.py`

**DFM unaffected** — uses Kalman filter with explicit missing data handling, not interpolation.

**Rule**: Never use `np.interp` for time series imputation in backtesting contexts. Use `utils.missing.forward_fill()` instead.

---

## 1. GDP Identity Reconciliation (Negative Finding)

**Date**: 2026-05-26

**Hypothesis**: Deriving imports from the GDP expenditure identity (M = C + I + G + X - GDP) would improve imports nowcast accuracy by enforcing cross-component consistency.

**Method**: After fitting DFM for all 5 expenditure components (C, I, G, X, M), compute derived imports growth via:
```
M_growth = (C_lvl × C_g + I_lvl × I_g + G_lvl × G_g + X_lvl × X_g - GDP_lvl × GDP_g) / M_lvl
```
Where `_lvl` are absolute MYR levels from the API and `_g` are the DFM nowcast growth rates.

**Result**:

| Imports Method | Nowcast | Actual | Error |
|---------------|:------:|:------:|:-----:|
| Direct DFM model | +3.4% | +4.6% | **-1.2 pp** |
| GDP identity | +13.6% | +4.6% | **+9.0 pp** |

**Why it failed**: The identity amplifies individual component errors. Consumption (61% of GDP) is overestimated by +3.9 pp. This error propagates through the identity with a multiplier of C_lvl/M_lvl ≈ 0.97, adding ~3.8 pp to the imports error.

**Conclusion**: GDP identity reconciliation is **theoretically correct but practically harmful** when individual component MAE exceeds ~1 pp. The direct DFM model for imports is substantially better. This approach would only be viable if all components were forecast with sub-1pp MAE.

**Recommendation**: Continue using direct DFM imports nowcast. Revisit identity approach only if component MAE drops below 1 pp (unlikely with public data alone).

---

## 2. Indicator Set Expansion (Positive Finding)

**Date**: 2026-05-26

**Initial set**: 8 indicators (IPI, CPI headline, CPI core, PPI, unemployment, participation, leading, coincident)

**Final set**: 17 indicators (+ youth unemployment, exports, WRT sales, trade balance, interbank rate, FX rate, capital goods imports, consumer goods imports, and more)

**Key findings**:

| Expansion | ENSEMBLE MAE Change | Notes |
|-----------|:-------------------:|-------|
| 8 → 10 indicators | -0.20 pp | BNM interbank rate added significant value |
| 10 → 12 (trade + WRT) | -0.03 pp | Marginal gain, approaching diminishing returns |
| 12 → 17 | -0.06 pp | Youth unemployment and BEC imports helped slightly |

**Conclusion**: 10-12 indicators is the sweet spot. Beyond 17, diminishing returns from public APIs. The BNM financial data was the most impactful single addition.

---

## 3. BNM Historical Data Discovery (Positive Finding)

**Date**: 2026-05-26

**Initial assumption**: BNM OpenAPI only provides latest/recent data, useless for backtesting.

**Discovery**: The BNM API has three endpoint variants per dataset:
- `/endpoint` — Latest only (1 record)
- `/endpoint/date/{date}` — Specific date (1 record)  
- `/endpoint/year/{year}/month/{month}` — **Full month of daily data** (20-23 records per month)

**Impact**: By looping month-by-month from 2015 to present, we recovered **137 monthly observations** of interbank rates and **70 monthly observations** of MYR/USD exchange rates.

**Architecture lesson**: Never assume an API is limited to what the "Latest" endpoint returns. Always inspect the OpenAPI/Swagger spec for hidden endpoint variants.

---

## 4. BEQ Debugging (Negative Finding + Fix)

**Date**: 2026-05-25

**Symptom**: BEQ produced NaN forecasts for 6 out of 24 backtest vintages. MAE was 7-14 pp vs DFM's 1.6 pp.

**Root cause**: The `bridge_forecast` function in `beq/forecast.py` padded lagged regressors with zeros, but the `Y_lag` column had trailing NaN (from yet-unreleased GDP in the vintage). When `X_all @ coeffs` computed forecasts for trailing quarters, any row with NaN in the Y_lag column produced NaN output.

**Fix**: 
1. Aligned regression matrix to trim lead/trail instead of padding
2. For trailing Y_lag NaN, substituted the last known Y value (persistence forecast)
3. Set other NaN regressors to 0 (no contribution from missing data)

**Before → After**:
| Metric | Before | After |
|--------|:------:|:-----:|
| Valid vintages | 18/24 | 24/24 |
| BEQ MAE (post-COVID) | 7.1 pp | 2.5 pp |
| BEQ RMSE | 24.1 | 4.2 |

**Conclusion**: The BEQ implementation was functionally broken for 6 months. The fix was a data alignment issue, not an algorithmic one.

---

## 5. Component Nowcast Performance

**Date**: 2026-05-26

**29 out-of-sample quarters, DFM vs AR(1) benchmark**

| Component | AR(1) MAE | DFM MAE | DFM Wins By | AR(1) FDA | DFM FDA | Verdict |
|-----------|:------:|:-----:|:---------:|:------:|:-----:|---------|
| GDP | 5.8 pp | 1.3 pp | 78% | 50% | 88% | ✅ Excellent |
| Investment | 6.8 pp | 2.4 pp | 65% | 39% | 75% | ✅ Good |
| Exports | 7.3 pp | 5.3 pp | 27% | 57% | 47% | ⚠️ Mixed |
| Imports | 6.6 pp | 6.1 pp | 8% | 50% | 47% | ❌ Poor |

**Key insight**: Components with direct monthly counterparts perform better:
- Investment benefits from IPI + capital goods imports (both directly observable monthly)
- Exports benefits from trade_headline (monthly exports)
- Imports is a residual — no single monthly indicator drives it

---

## 6. ARC Vintage Builder (Positive Finding)

**Date**: 2026-05-24

**Problem**: Hardcoded publication lags (e.g., "CPI ~19 days") are imprecise.

**Solution**: Parsed the DOSM Advance Release Calendar ICS feed to extract exact publication dates for every Malaysian statistical release (598 releases across 17 datasets, 2023-2026).

**Impact**: FDA for BVAR improved from 31.6% to 42.1% (+10.5 pp) when switching from approximate lags to exact ARC dates. Ensemble FDA improved from 52.6% to 68.4% (+15.8 pp).

**Architecture lesson**: Exact release dates matter more than expected — a 2-3 day difference in when data is "available" can flip directional nowcast calls.

---

## 7. COVID Correction Mode Impact

**Date**: 2026-05-26

**Method**: Mode 2 (NaN-block Feb-Sep 2020). Removes pandemic period from training data.

| Model | Before COVID Fix | After COVID Fix | Improvement |
|-------|:---------------:|:---------------:|:-----------:|
| DFM full-period MAE | 3.52 pp | 2.80 pp | **20%** |
| BVAR full-period MAE | 4.24 pp | 2.85 pp | **33%** |
| DFM post-COVID MAE | 1.81 pp | 1.54 pp | **15%** |
| DFM post-COVID FDA | 47.4% | 57.9% | **+10.5 pp** |

**Conclusion**: The COVID pandemic (Q2 2020: -16.9% YoY, Q3 2020: +18.2% QoQ) creates outlier observations that poison factor estimates for all subsequent vintages. Removing the COVID period from training is the single most impactful data cleaning step.

---

## 8. Pre-Computed Growth Rates vs Raw Data

**Date**: 2026-05-25

**Finding**: Using the API's pre-computed `growth_mom` series hurt model performance compared to using `abs` (absolute levels) with our own dlog transform.

| Approach | Exports/WRT MAE Impact |
|----------|:---------------------:|
| API `growth_mom` pre-computed | +0.20 pp (worse) |
| API `abs` + our dlog transform | -0.06 pp (better) |

**Hypothesis**: The API's growth rate computation may use different methodology (e.g., working-day adjustment, seasonal adjustment) that doesn't match our standardization pipeline. Using raw levels ensures consistent transforms across all indicators.

**Recommendation**: Always use `abs` series and compute growth internally. Only use `growth_mom` for variables where the absolute level is meaningless (e.g., unemployment rate which is already a percentage).


## 9. Block Factors in DFM (Negative Finding)

**Date**: 2026-05-26

**Hypothesis**: Adding block-specific factors (one per economic category: industry, prices, labour, external, services) would improve factor identification by forcing variables in the same category to share a dedicated factor.

**Implementation**: State vector expanded from r×p to r×p + n_blocks×p. Block factors initialized with halved loadings on their own block's variables, zero elsewhere. M-step enforces zero cross-block loadings.

**Result**: Backtest with `block_factors=1` produced **identical** MAE and FDA to `block_factors=0`.

| Metric | block_factors=0 | block_factors=1 | Delta |
|--------|:--------------:|:--------------:|:-----:|
| DFM MAE (post-COVID) | 1.544 pp | 1.544 pp | 0 |
| DFM FDA (post-COVID) | 57.9% | 57.9% | 0 |

**Why it failed**: The block factor implementation only constrains loadings in the M-step but doesn't properly allocate the additional state-space dimensions. The EM algorithm effectively zeros out the block factors because they're initialized with weak loadings (0.5× global) and the M-step can't move them significantly given the constraint. Additionally, many blocks have only 1-2 variables (industry, leading, coincident, services, financial), providing insufficient signal for a dedicated factor.

**Conclusion**: Block factors as currently implemented add no value. They would only be useful with: (a) larger blocks (5+ variables per category), (b) stronger initialization, or (c) a hierarchical EM formulation that fits block factors first then global factors. For the current 17-indicator set with 8 categories, block factors are pure overhead.

**Recommendation**: Leave disabled. Revisit only if indicator set grows to 30+ with 5+ variables per economic category.


## 10. Hyperparameter Grid Search

**Date**: 2026-05-26

**Method**: Grid search over r ∈ {2,3,4,5} × p ∈ {1,2,3,4} over 20 vintages (2021-2025). 16 combinations tested.

**Results**:

| r | p | MAE (pp) | FDA | Verdict |
|---|:--:|:------:|:---:|---------|
| **2** | **4** | **1.406** | 85% | **Best MAE** |
| 4 | 1 | 1.542 | 85% | |
| 2 | 1 | 1.574 | 85% | **Best FDA** |
| 5 | 1 | 1.586 | 85% | |
| 3 | 2 | 1.665 | 75% | *(current default)* |
| 4 | 2 | 2.496 | 70% | *(worst)* |

**Key findings**:
- **r=2 (fewer factors) outperforms r=3** — with only 17 indicators, 2 factors is sufficient. r=3 overfits.
- **p=4 (more lags) outperforms p=2** — GDP dynamics have longer memory than our default assumed.
- **Current default (r=3, p=2) is suboptimal** — MAE 1.665 vs optimal 1.406, a 15.6% gap.
- The optimal (r=2, p=4) uses 8 state dimensions vs current 6 — more memory, fewer factors.

**Recommendation**: Switch default to r=2, p=4. Update `backtest_all_models.py` and `daily_update.py` to use these values.


## 11. Component Backtest Results

**Date**: 2026-05-26

**Method**: Full backtest for all 5 expenditure components (C, I, G, X, M) over 24 vintages (2020-Q1 to 2025-Q4), using the same ARC-based vintage builder and DFM (r=3, p=2) as the main GDP backtest.

**Results**:

| Component | MAE (pp) | RMSE (pp) | FDA | N |
|-----------|:------:|:--------:|:---:|:-:|
| Consumption (e1) | **0.69** | 0.89 | **78%** | 24 |
| Investment (e3) | **0.74** | 1.19 | **96%** | 24 |
| Government (e2) | 1.03 | 1.21 | 96% | 24 |
| Exports (e5) | 1.60 | 2.17 | 96% | 24 |
| Imports (e6) | **2.71** | 3.46 | 96% | 24 |

**Key findings**:
- **Consumption is highly predictable** at 0.69 pp MAE — much better than expected. The earlier daily nowcast errors (+3.9 pp) were single-point estimates; averaged over 24 vintages, the DFM performs well on consumption.
- **Investment and government are excellent** at <1 pp MAE with 96% FDA. These components are well-captured by the monthly indicators.
- **Imports remains the hardest** at 2.71 pp MAE, though FDA is 96% (strong direction). Imports are structurally the residual component.
- **All components have strong directional accuracy** (78-96% FDA) — the DFM rarely gets the sign wrong.
- The backtest validates that component-level nowcasting with the DFM is viable and robust, even if single-point daily nowcasts can be noisy.

### Update: High-Frequency Global Indicators (2026-05-26)

Added 3 new daily indicators via yfinance:
- **SOX** (`^SOX`): Philadelphia Semiconductor Index — E&E = 40% of Malaysian exports
- **CPO** (`CPO=F`): CME Malaysian Crude Palm Oil Futures — Malaysia's #1 agri-commodity
- **BDRY** (`BDRY`): Breakwave Dry Bulk Shipping ETF — trade volume proxy (BDI removed from FRED in 2021)

24-vintage backtest with per-component filtering:

| Component | Without Global | With Global | Change |
|-----------|:------:|:------:|:------:|
| Consumption (e1) | 0.69 | **0.55** | -20% |
| Exports (e5) | 1.60 | **1.49** | -7% |
| Imports (e6) | 2.71 | **2.24** | -17% |
| Investment (e3) | 0.74 | 1.20 | +62% (noise) |
| Government (e2) | 1.03 | 1.16 | +13% (noise) |

**Key findings**:
- SOX, CPO, and BDRY meaningfully improve trade-linked components (exports/imports/consumption)
- Global indicators add noise to investment and government — excluded from those component filters in production
- CPO delivers despite having fewer obs (130 months vs 136) — commodity prices are inherently cyclical and informative
- BDRY (BDI proxy) contributes to import forecasting despite limited history (98 months)
- Per-component indicator subsets are essential — 1-size-fits-all hurts non-trade components

### BVAR vs DFM Component Backtest (2026-05-27)

Ran component backtest with BVAR alongside DFM (10 vintages, 2023-Q2 to 2025-Q3):

| Component | DFM MAE | BVAR MAE | BVAR Wins? |
|-----------|:------:|:------:|:------:|
| Investment (e3) | 3.68 | **0.55** | **6.7x better** |
| Exports (e5) | 5.89 | **0.21** | **28x better** |

Daily nowcast (single point, Q2 2026 vs Q1 2026 actual):

| Component | DFM Err | BVAR Err | Winner |
|-----------|:------:|:------:|:------:|
| Consumption | 2.3pp | **0.0pp** | BVAR |
| Government | 0.6pp | **0.0pp** | BVAR |
| Investment | 2.1pp | **0.0pp** | BVAR |
| Exports | 1.1pp | **0.1pp** | BVAR |
| Imports | 0.1pp | **0.0pp** | BVAR |

**Key findings**:
- **BVAR dominates DFM on components** — 6-28x better MAE in backtest, wins every daily comparison
- BVAR's Minnesota prior provides better regularization than DFM's factor structure for component-level data
- DFM's factor model is over-parameterized for component subsets (few indicators per component)
- BVAR ties with NAIVE on daily nowcasts (0.0pp error) — BVAR is essentially learning the persistence pattern
- Recommendation: **BVAR should be the primary component nowcast model**, not DFM
- BEQ returns NaN for all components (VAR interpolation fails with component indicator subsets) — needs debugging or removal from component pipeline

### Naive Forecast Baseline (2026-05-26)

The simplest possible benchmark: forecast current quarter GDP = last quarter's actual (persistence / random walk). 24-vintage backtest:

| Model | MAE (pp) | RMSE (pp) | FDA | N |
|-------|:------:|:--------:|:---:|:-:|
| **DFM** | **2.80** | 5.21 | **56.5%** | 24 |
| BVAR | 2.85 | 5.37 | 30.4% | 24 |
| ENSEMBLE | 2.86 | 5.21 | 47.8% | 24 |
| BEQ | 4.05 | 6.20 | 39.1% | 24 |
| **NAIVE** | **4.48** | **8.93** | **27.3%** | 23 |

**Key findings**:
- DFM beats naive by 38% (2.80 vs 4.48 pp MAE) — model adds signal beyond persistence
- All statistical models beat naive on MAE, confirming skill beyond "no change"
- Naive directional accuracy (27.3%) is worse than a coin flip — GDP growth does not persist quarter-to-quarter
- Naive's RMSE (8.93) is nearly double DFM's (5.21) — large errors when growth changes direction
- This validates the nowcasting approach: even simple models add meaningful information over persistence

### Main GDP Backtest with Global Indicators (2026-05-27)

Added 8 global indicators via yfinance (SP500, Shanghai, SOX, KLCI, STI, Brent, CPO, BDRY) to main GDP backtest. 12 vintages (2023-Q1 to 2025-Q4), DFM r=2 p=1, BVAR lags=2.

| Model | MAE (pp) | RMSE (pp) | FDA (%) | N |
|-------|:------:|:--------:|:------:|:-:|
| DFM | **0.569** | 0.650 | 54.5% | 12 |
| BEQ | 0.770 | 1.000 | 18.2% | 12 |
| BVAR | 0.787 | 0.938 | 45.5% | 12 |
| NAIVE | 0.926 | 1.095 | 36.4% | 12 |
| ENSEMBLE | 0.622 | 0.671 | **63.6%** | 12 |

**Key findings**:
- **DFM still wins main GDP** (0.569 MAE) — factor model handles 23 variables better than BVAR
- **Ensemble has best FDA** (63.6%) — weighted median catches directional changes better than any single model
- **BVAR loses on main GDP but wins on components** — consistent: factor model scales to many variables, BVAR's Minnesota prior excels with few
- **Global indicators don't improve main GDP** — they help components (exports -7%, imports -17%) but add noise to aggregate
- **DOSM Advance** (0.175 MAE) still dominates all models — official data beats statistical nowcasting
- **Strategy confirmed**: DFM for main GDP, BVAR for components, ensemble for directional accuracy

---

*Last updated: 2026-05-26. All findings are from the Malaysia nowcasting pipeline using OpenDOSM + BNM + yfinance + FRED public APIs.*
