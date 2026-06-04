# BVAR — Bayesian Vector Autoregression

## Overview

The Bayesian VAR (BVAR) implements a large Bayesian VAR with Minnesota prior, optimized using Chris Sims' csminwel algorithm. It supports mixed-frequency data through quarter-block restructuring.

**Reference:** Cimadomo, J., Giannone, D., Lenza, M., Monti, F., & Sokol, A. (2022). "Nowcasting with large Bayesian vector autoregressions." *Journal of Econometrics*, 231(2), 500–519.

## Usage

```python
from nowcasting_toolbox.bvar import BVAR
from nowcasting_toolbox.config import BVARParams

# Create model
params = BVARParams(bvar_lags=2, bvar_n_draws=100, bvar_burn_in=30)
bvar = BVAR(params)

# Fit data (with optional datet for quarter-block mode)
result = bvar.fit(X, datet=datet)

# Access results
smoothed = result.X_sm       # (T, N) smoothed observations
B_draws = result.B_draws     # (n_draws, N, K) posterior draws
Sigma_draws = result.Sigma_draws  # (n_draws, N, N) covariance draws
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bvar_lags` | int | 5 | Number of VAR lags |
| `bvar_n_draws` | int | 100 | Gibbs sampler draws |
| `bvar_burn_in` | int | 30 | Burn-in period |
| `bvar_seed` | int | 42 | Random seed |
| `bvar_thresh` | float | 1e-6 | Optimizer convergence threshold |
| `bvar_max_iter` | int | 200 | Maximum optimization iterations |

## Minnesota Prior

The Minnesota prior imposes shrinkage on VAR coefficients:

- **λ (tightness):** Controls overall shrinkage (default: 0.2)
- **μ (sum-of-coefficients):** Stationarity prior (default: 1.0)
- **θ (co-persistence):** Random walk prior (default: 1.0)
- **α (block exogeneity):** Cross-variable shrinkage (default: 2.0)

## Quarter-Block Mode

When `datet` is provided, data is restructured into quarter-block format:
- Month 1 values: columns 0 to nM-1
- Month 2 values: columns nM to 2*nM-1
- Month 3 values: columns 2*nM to 3*nM-1 + nQ

This matches the MATLAB BVAR_bbvar behavior and improves accuracy but is slower.

## Speed vs Accuracy

```python
# Fast (daily nowcasting, ~30s)
bvar.fit(X)

# Accurate (backtesting, ~10min)
bvar.fit(X, datet)
```
