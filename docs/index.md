# Nowcasting Toolbox — Python Edition

Python port of the [ECB Nowcasting Toolbox](https://github.com/baptiste-meunier/Nowcasting_toolbox) (Linzenich & Meunier, 2024) with a live Malaysian macroeconomic data pipeline.

## Features

- **Three model engines:** DFM, BVAR, BEQ
- **Ensemble methods:** Median, inverse MAE/MSE, direction vote, trimmed mean
- **Live data pipeline:** OpenDOSM, BNM, Yahoo Finance, FRED
- **CLI interface:** `nowcast fetch`, `nowcast run`, `nowcast backtest`
- **Evaluation:** MAE, RMSE, FDA, MASE, CRPS metrics

## Quick Links

- [Installation](installation.md)
- [Quick Start](quickstart.md)
- [CLI Reference](cli/commands.md)
- [API Reference](api/full.md)
- [GitHub Repository](https://github.com/pengkodammaya/BM-ECB)

## Model Overview

| Model | Algorithm | Reference |
|-------|-----------|-----------|
| **DFM** | Dynamic Factor Model with EM + Kalman filter/smoother | Bańbura & Modugno (2014) |
| **BVAR** | Large Bayesian VAR with Minnesota prior | Cimadomo et al. (2022) |
| **BEQ** | Bridge Equations ensemble with BVAR interpolation | Bańbura et al. (2023) |
| **AR(1)** | Autoregressive benchmark | Standard baseline |

## Live Dashboard

| Resource | Description |
|----------|-------------|
| [Dashboard](https://github.com/pengkodammaya/BM-ECB/blob/main/docs/dashboard.md) | DOSM-style markdown dashboard |
| [Leaderboard](https://github.com/pengkodammaya/BM-ECB/blob/main/docs/leaderboard.md) | Model accuracy comparison |
| [Data (JSON)](https://github.com/pengkodammaya/BM-ECB/blob/main/docs/data.json) | Machine-readable nowcast data |
