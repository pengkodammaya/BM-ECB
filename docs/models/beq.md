# BEQ — Bridge Equations

## Overview

Bridge Equations (BEQ) estimate GDP from monthly indicators using individual regressions per indicator, combined via median. Missing values at the ragged edge are filled using BVAR-based interpolation.

**Reference:** Bańbura, M., Belousova, I., Bodnár, K., & Tóth, M. B. (2023). "Nowcasting employment in the euro area." *ECB Working Paper Series*, No 2815.

## Usage

```python
from nowcasting_toolbox.beq import BEQ
from nowcasting_toolbox.config import BEQParams

# Create model
params = BEQParams(lagM=1, lagQ=1, lagY=1, type=901)
beq = BEQ(params)

# Fit data
result = beq.fit(X, datet, var_names)

# Access results
smoothed = result.X_sm  # (T, N) smoothed observations
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `lagM` | int | 1 | Monthly regressor lags (quarterly terms) |
| `lagQ` | int | 1 | Quarterly regressor lags |
| `lagY` | int | 1 | Endogenous variable lags |
| `type` | int | 901 | Interpolation type |
| `Dum` | list | [] | COVID dummy dates [(year, month), ...] |

## Interpolation Types

| Type | Description |
|------|-------------|
| 901 | BVAR on all variables |
| 902 | BVAR on selected variables |
| 903 | Univariate BVAR (one series at a time) |

## Combination Method

Individual bridge equation forecasts are combined via **median**. This is robust to outliers and matches the ECB toolbox implementation.

## COVID Dummies

Add dummy variables for pandemic period:

```python
params = BEQParams(
    lagM=1, lagQ=1, lagY=1, type=901,
    Dum=[(2020, 2), (2020, 3), (2020, 4), (2020, 5), (2020, 6)]
)
```
