# Quick Start

## Fetch Data

```bash
# Fetch latest data from OpenDOSM, BNM, and global APIs
nowcast fetch
```

## Run Nowcast

```bash
# Full pipeline: fetch → transform → nowcast → leaderboard
nowcast run
```

## Backtest

```bash
# Run pseudo-real-time backtest evaluation
nowcast backtest

# With custom date range
nowcast backtest --start 2023-01-01 --end 2025-12-31
```

## News Decomposition

```bash
# Attribute nowcast changes to data releases
nowcast news

# Compare specific dates
nowcast news --old-date 2026-05-01 --new-date 2026-06-01
```

## Variable Selection

```bash
# Rank indicators by predictive power
nowcast select-vars --method lars --n 20
```

## Configuration

```bash
# Generate sample config
nowcast config-template

# Use custom config
nowcast --config config.json run

# YAML also supported
nowcast --config config.yaml run
```

## Python API

```python
from nowcasting_toolbox.dfm import DFM
from nowcasting_toolbox.config import DFMParams

# Create model
dfm = DFM(DFMParams(r=2, p=4, max_iter=50))

# Fit data (T×N array, last column = quarterly GDP)
result = dfm.fit(X)

# Get smoothed GDP estimates
gdp_smoothed = result.X_sm[:, -1]
```
