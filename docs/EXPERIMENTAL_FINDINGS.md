# Experimental Findings — Malaysia GDP Nowcasting

This document captures key experimental results, both positive and negative, from the nowcasting system development.

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

---

*Last updated: 2026-05-26. All findings are from the Malaysia nowcasting pipeline using OpenDOSM + BNM public APIs.*
