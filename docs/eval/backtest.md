# Backtesting

## Overview

The backtest engine runs pseudo-real-time evaluation by simulating what data would have been available at each historical date.

## Usage

```python
from nowcasting_toolbox.eval.backtest import run_backtest
from nowcasting_toolbox.config import ToolboxConfig

config = ToolboxConfig()
config.eval.eval_startyear = 2021
config.eval.eval_endyear = 2025

results = run_backtest(config, X, datet)
```

## CLI

```bash
nowcast backtest --start 2021-01-01 --end 2025-12-31
```

## How It Works

1. For each vintage date in the evaluation window:
   - Apply ragged edge (mask data not yet published)
   - Fit all three models (DFM, BVAR, BEQ)
   - Extract nowcast for current quarter
2. Compare nowcasts against actual GDP
3. Compute metrics (MAE, RMSE, FDA, MASE)

## Vintage Dates

Vintage dates are typically quarter-end months when GDP is released:
- Q1: May (GDP released ~May 15)
- Q2: August (GDP released ~Aug 15)
- Q3: November (GDP released ~Nov 15)
- Q4: February (GDP released ~Feb 15)
