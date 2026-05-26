"""Quick test of live ARC vintage builder with available years."""
import sys; sys.path.insert(0,"src")
from pathlib import Path
from datetime import date
import numpy as np
from nowcasting_toolbox.eval.vintage import ARCVintageBuilder
from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule

# Build schedule for years we have
schedule = build_publication_schedule(
    years=[2023, 2024, 2025, 2026],
    cache_dir=Path("data/malaysia"),
)
print(f"Schedule: {len(schedule)} releases")

vb = ARCVintageBuilder(schedule=schedule)
cov = vb.describe_coverage()
print(f"Datasets: {cov['datasets_with_schedule']}")

# Simulate: what data was available on May 15, 2026?
test_date = date(2026, 5, 15)
print(f"\nAs of: {test_date}")

# Create dummy data matrix
T = 120
datet = np.column_stack([
    np.repeat(np.arange(2018, 2028), 12)[:T],
    np.tile(np.arange(1, 13), 10)[:T],
])
X = np.random.randn(T, 9)  # dummy data
var_names = ["ipi", "cpi_headline", "cpi_core", "ppi", "u_rate", "p_rate", "leading", "coincident", "gdp"]
did_map = ["ipi", "cpi_headline", "cpi_core", "ppi", "u_rate", "u_rate", "leading", "coincident", "gdp"]

X_vint = vb.build(X, datet, test_date, var_names=var_names, dataset_ids=did_map)

# Count how many non-NaN values each column has before vs after
for j, name in enumerate(var_names):
    before = np.sum(~np.isnan(X[:, j]))
    after = np.sum(~np.isnan(X_vint[:, j]))
    last_available = np.where(~np.isnan(X_vint[:, j]))[0]
    if len(last_available) > 0:
        last_idx = last_available[-1]
        y, m = int(datet[last_idx, 0]), int(datet[last_idx, 1])
        print(f"  {name}: {before} -> {after} obs, last available: {y}-{m:02d}")
    else:
        print(f"  {name}: {before} -> {after} obs, last available: NONE")
