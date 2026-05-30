# Plan: BVAR & BEQ Faithfulness Fixes

**Date**: 2026-05-31  
**Status**: Pending  
**Priority**: High

---

## Problem

Comparison with original MATLAB toolbox (baptiste-meunier/Nowcasting_toolbox) reveals:
- **BVAR**: Missing quarter-block data restructuring (70% faithful)
- **BEQ**: Different interpolation, missing minimum obs checks (80% faithful)
- **Result**: BVAR behaves like persistence forecast, not using indicators properly

---

## BVAR Fixes

### Issue 1: Missing Quarter-Block Restructuring (Critical)

**MATLAB original** (`BVAR_filldata.m`):
- Restructures monthly data into 3-month blocks per quarter
- Month 1 columns: 1:nM
- Month 2 columns: nM+1:2*nM
- Month 3 columns: 2*nM+1:end

**Python current** (`bvar/bbvar.py:_fill_data`):
- Just forward-fills NaN values
- No block restructuring

**Fix**:
- [ ] Implement `BVAR_filldata` equivalent in Python
- [ ] Restructure data into quarter-block format before BVAR estimation
- [ ] Restructure output back to monthly format after estimation

### Issue 2: Missing Minimum Observations Check

**MATLAB original** (`BVAR_estimate.m`):
```matlab
min_obs = 3*2*Par.bvar_lags + 1;
if iMax - iX + 1 > min_obs
    idx_keep_Xm = [idx_keep_Xm, cc];
end
```

**Python current**: No check

**Fix**:
- [ ] Add minimum observations check before BVAR estimation
- [ ] Drop variables with insufficient data
- [ ] Log warning when variables are dropped

### Issue 3: Forward-Fill vs Block Structure

**Current behavior**: Forward-fill propagates last known value to all future months
**Expected behavior**: Data should be organized in quarter-blocks, not forward-filled

**Fix**:
- [ ] Replace `_fill_data` with quarter-block restructuring
- [ ] Keep NaN for months 1-2 of each quarter (BVAR handles missing data)
- [ ] Only fill month 3 with actual GDP value

---

## BEQ Fixes

### Issue 4: Interpolation Lambda Values

**MATLAB original** (`BEQ_estimate.m`):
```matlab
if size(Xm,2) > 1
    Par_BVAR.lambda = 0.2;  % multivariate
else
    Par_BVAR.lambda = 0.5;  % univariate
end
```

**Python current** (`beq/interpolate.py`):
- Uses fixed lambda=0.2

**Fix**:
- [ ] Use lambda=0.2 for multivariate BVAR (type 901)
- [ ] Use lambda=0.5 for univariate BVAR (type 903)

### Issue 5: Minimum Observations Check

**MATLAB original** (`BEQ_estimate.m`):
```matlab
min_obs = 2*Par_BVAR.lags + 1;
if iMax - iX + 1 > min_obs
    idx_keep_Xm = [idx_keep_Xm, cc];
end
```

**Python current**: No check

**Fix**:
- [ ] Add minimum observations check before BEQ estimation
- [ ] Drop variables with insufficient data

### Issue 6: In-Between NaN Handling

**MATLAB original** (`BEQ_estimate.m`):
```matlab
Xm = BEQ_inbetween_nan(Xm);
Xq = BEQ_inbetween_nan(Xq);
Y = BEQ_inbetween_nan(Y);
```

**Python current**: No in-between NaN handling

**Fix**:
- [ ] Implement `BEQ_inbetween_nan` equivalent
- [ ] Fill NaN between two non-missing values via linear interpolation

### Issue 7: Contribution Tracking

**MATLAB original**: Full contribution tracking for each bridge equation
**Python current**: Partial tracking

**Fix**:
- [ ] Implement full contribution tracking
- [ ] Store contributions for each variable in each bridge equation
- [ ] Rescale contributions to match median forecast

---

## Implementation Order

### Phase 1: BVAR Block Restructuring (Critical)
1. Implement `BVAR_filldata` equivalent
2. Add quarter-block restructuring
3. Update `_fill_data` to use block structure
4. Test with synthetic data

### Phase 2: BVAR Minimum Observations
1. Add minimum observations check
2. Drop variables with insufficient data
3. Log warnings

### Phase 3: BEQ Fixes
1. Implement variable lambda values
2. Add minimum observations check
3. Implement in-between NaN handling
4. Add full contribution tracking

### Phase 4: Validation
1. Run backtest with fixed BVAR/BEQ
2. Compare with MATLAB original results
3. Verify nowcasts are not just persistence forecasts

---

## Testing Plan

### Unit Tests
- [ ] Test `BVAR_filldata` with synthetic data
- [ ] Test quarter-block restructuring
- [ ] Test minimum observations check
- [ ] Test BEQ lambda values
- [ ] Test in-between NaN handling

### Integration Tests
- [ ] Run BVAR on Malaysian data, verify not persistence
- [ ] Run BEQ on Malaysian data, verify contributions
- [ ] Compare with MATLAB original outputs

### Backtest
- [ ] Run full backtest with fixed BVAR/BEQ
- [ ] Verify MAE/RMSE/FDA are reasonable
- [ ] Compare with old results

---

## Success Criteria

- [ ] BVAR uses indicators (not just persistence)
- [ ] BVAR MAE changes significantly from 0.038 pp
- [ ] BEQ contributions are tracked correctly
- [ ] All unit tests pass
- [ ] Full backtest runs successfully

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BVAR breaks | Medium | High | Keep old implementation as fallback |
| Performance degradation | Low | Medium | Profile before/after |
| Incompatible with existing data | Low | Low | Test with multiple datasets |

---

## References

- Original MATLAB toolbox: https://github.com/baptiste-meunier/Nowcasting_toolbox
- BVAR paper: Cimadomo et al. (2022) "Nowcasting with large Bayesian vector autoregressions"
- BEQ paper: Bańbura et al. (2023) "Nowcasting employment in the euro area"
