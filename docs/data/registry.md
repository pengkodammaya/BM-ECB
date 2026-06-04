# Registry

## Overview

The dataset registry provides a single source of truth for all available datasets, including metadata like frequency, transform code, group, and publication lag.

## Usage

```python
from nowcasting_toolbox.data.sources.registry import (
    MALAYSIA_REGISTRY,
    get_registry,
    get_meta,
    get_target,
    get_monthly_ids,
    get_global_ids,
    CLI_DATASETS,
)

# Get all datasets
all_datasets = get_registry()

# Get specific dataset metadata
ipi_meta = get_meta("ipi")
print(ipi_meta.name, ipi_meta.frequency, ipi_meta.group)

# Get target variable
gdp = get_target()
print(gdp.id)  # "gdp_qtr_real"

# Get monthly indicator IDs
monthly = get_monthly_ids()

# Get global indicator IDs
global_ids = get_global_ids()
```

## Dataset Metadata

Each `DatasetMeta` contains:

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Dataset ID (API identifier) |
| `name` | str | Human-readable name |
| `frequency` | Frequency | monthly/quarterly/daily |
| `transform` | TransformCode | Default transform (0-4) |
| `group` | str | Economic category |
| `pub_lag_days` | int | Publication delay (days) |
| `source` | str | Data source (opendosm/bnm/yfinance/fred) |
| `description` | str | Description |

## Groups

| Group | Description |
|-------|-------------|
| `industry` | Industrial production |
| `prices` | CPI, PPI |
| `labour` | Employment, unemployment |
| `external` | Trade |
| `financial` | Interest rates, FX |
| `leading` | Leading indicators |
| `coincident` | Coincident indicators |
| `services` | Wholesale/retail trade |
| `consumption` | Consumption indicators |
| `global_equity` | Global stock indices |
| `global_commodity` | Commodity prices |
| `global_demand` | Global demand proxies |
| `target` | GDP (target variable) |
