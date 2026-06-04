# Configuration

## Config File Format

The toolbox supports JSON and YAML configuration files.

### Generate Template

```bash
nowcast config-template
```

This creates `config_example.json` with all available options.

### Example Config (JSON)

```json
{
  "dfm": {
    "r": 2,
    "p": 4,
    "max_iter": 50,
    "thresh": 0.0001,
    "idio": 1
  },
  "bvar": {
    "bvar_lags": 2,
    "bvar_thresh": 1e-5,
    "bvar_max_iter": 200,
    "bvar_n_draws": 100,
    "bvar_burn_in": 30,
    "bvar_seed": 42
  },
  "beq": {
    "lagM": 1,
    "lagQ": 1,
    "lagY": 1,
    "type": 901
  },
  "eval": {
    "eval_startyear": 2021,
    "eval_startmonth": 1,
    "eval_endyear": 2025,
    "eval_endmonth": 12
  }
}
```

### Using Config

```bash
nowcast --config config.json run
```

## Key Parameters

### DFM Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `r` | 2 | Number of factors |
| `p` | 4 | Number of lags in factor VAR |
| `max_iter` | 100 | Maximum EM iterations |
| `thresh` | 1e-4 | Convergence threshold |
| `idio` | 1 | Idiosyncratic spec (0=iid, 1=AR(1)) |

### BVAR Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `bvar_lags` | 5 | Number of VAR lags |
| `bvar_n_draws` | 100 | Gibbs sampler draws |
| `bvar_burn_in` | 30 | Gibbs burn-in period |
| `bvar_seed` | 42 | Random seed |

### BEQ Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `lagM` | 1 | Monthly regressor lags |
| `lagQ` | 1 | Quarterly regressor lags |
| `lagY` | 1 | Endogenous variable lags |
| `type` | 901 | Interpolation type (901=BVAR all) |
