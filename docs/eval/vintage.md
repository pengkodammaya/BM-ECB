# Vintage Builder

## Overview

The vintage builder simulates real-time data availability by masking data that wouldn't have been published at a given date.

## Usage

```python
from nowcasting_toolbox.eval.vintage import ARCVintageBuilder
from datetime import date

# Build publication schedule from ARC
schedule = build_publication_schedule(years=[2023, 2024, 2025])

# Create vintage builder
vb = ARCVintageBuilder(schedule=schedule)

# Build vintage for specific date
X_vintage = vb.build(X, datet, vintage_date=date(2024, 6, 15),
                     var_names=var_names, dataset_ids=dataset_ids)
```

## ARC (Advance Release Calendar)

The DOSM ARC provides exact publication dates for Malaysian statistical releases. The parser fetches ICS calendar files and extracts:
- Release date
- Title
- Dataset ID (via fuzzy matching)
- Reference period

## Publication Schedule

| Variable | Approximate Lag | Release Day |
|----------|-----------------|-------------|
| IPI | 1 month | ~8th |
| CPI | 1 month | ~19th |
| PPI | 1 month | ~25th |
| Labour | 1 month | ~12th |
| Leading/Coincident | 2 months | ~25th |
| GDP | 2 months | ~15th |
