# DFM — Dynamic Factor Model

## Overview

The Dynamic Factor Model (DFM) extracts common factors from a panel of monthly indicators using the EM algorithm with Kalman filtering/smoothing. It handles arbitrary missing data patterns natively.

**Reference:** Bańbura, M., & Modugno, M. (2014). "Maximum likelihood estimation of factor models on datasets with arbitrary pattern of missing data." *Journal of Applied Econometrics*, 29(11), 133–160.

## Usage

```python
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams

# Create model
params = DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1)
dfm = DFM(params)

# Fit data
result = dfm.fit(X)

# Access results
smoothed = result.X_sm      # (T, N) smoothed observations
factors = result.factors     # (T, r) estimated factors
loadings = result.C          # (N, r) factor loadings
transition = result.A        # (r*p, r*p) state transition
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `r` | int | 2 | Number of static factors |
| `p` | int | 4 | Number of lags in factor VAR |
| `idio` | int | 1 | Idiosyncratic specification (0=iid, 1=AR(1)) |
| `thresh` | float | 1e-4 | EM convergence threshold |
| `max_iter` | int | 100 | Maximum EM iterations |
| `block_factors` | int | 0 | Include block-specific factors |

## State-Space Representation

```
y(t) = C * Z(t) + e(t),   e(t) ~ N(0, R)
Z(t) = A * Z(t-1) + v(t), v(t) ~ N(0, Q)
```

Where:
- `y(t)` is the (N×1) observation vector (may contain NaN)
- `Z(t)` is the (K×1) state vector (factors and their lags)
- `C` is the (N×K) observation/loading matrix
- `A` is the (K×K) state transition matrix

## Algorithm

1. **Initialization:** PCA-based initial conditions
2. **E-step:** Kalman smoother computes E[Z|Y] and Var[Z|Y]
3. **M-step:** Update C, A, Q, R using closed-form sufficient statistics
4. **Convergence:** Check relative log-likelihood change

## Handling Missing Data

The Kalman filter at each time step selects only observed rows of `y(t)`. If all observations are NaN (e.g., month 1 of a quarter for GDP), the filter propagates the prediction without updating.
