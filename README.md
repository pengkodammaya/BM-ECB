# Nowcasting Toolbox — Python Edition

Python port of the [ECB Nowcasting Toolbox](https://github.com/baptiste-meunier/Nowcasting_toolbox) (Linzenich & Meunier, 2024) with a live Malaysian macroeconomic data pipeline.

**Original**: MATLAB + R | **This port**: Python 3.12+ with `uv`

## 📊 Live Dashboard

| Resource | Description |
|----------|-------------|
| [Leaderboard (Markdown)](docs/leaderboard.md) | Model accuracy, nowcasts, sector/expenditure breakdowns |
| [Dashboard (HTML)](docs/dashboard.html) | DOSM-style visual dashboard — download and open locally |
| [Data (JSON)](docs/data.json) | Machine-readable nowcast data for integrations |

*Auto-updated daily at 8am MYT via GitHub Actions.*

## Model Engines

| Model | Algorithm | Reference |
|-------|-----------|-----------|
| **DFM** | Dynamic Factor Model with EM + Kalman filter/smoother | Bańbura & Modugno (2014) *J. Applied Econometrics* |
| **BVAR** | Large Bayesian VAR with Minnesota prior + block structure | Cimadomo et al. (2022) *J. Econometrics* |
| **BEQ** | Bridge Equations ensemble with BVAR interpolation | Bańbura et al. (2023) ECB Working Paper No. 2815 |

## Malaysian Data Pipeline

- **OpenDOSM API** — 12 monthly indicators (IPI, CPI, PPI, labour, trade, WRT, economic indicators)
- **BNM OpenAPI** — Daily interest rates and exchange rates (monthly aggregation)
- **DOSM ARC** — Live advance release calendar for pseudo-real-time vintages
- **DOSM Advance GDP Estimates** — Benchmark comparison (aggregate + component level)

## Quick Start

```bash
# Setup
uv venv
uv pip install -e ".[dev]"

# Fetch data and run nowcast
nowcast fetch
nowcast run

# Backtest with ARC vintages
nowcast backtest

# News decomposition
nowcast news

# Variable ranking
nowcast select-vars
```

## Acknowledgements

This project ports the MATLAB toolbox developed by Baptiste Meunier and Jan Linzenich at the ECB, published as:

> Linzenich, J., & Meunier, B. (2024). "Nowcasting Made Easier: a Toolbox for Real-Time Predictions." *ECB Working Paper Series*, No. 3004.

The original MATLAB repository is at https://github.com/baptiste-meunier/Nowcasting_toolbox.

When using models from this toolbox, please cite the original papers listed above.
