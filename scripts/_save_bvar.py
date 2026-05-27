"""Update leaderboard with local BVAR component results."""
import sys; sys.path.insert(0, "src")
import json
from pathlib import Path

# Fresh BVAR component results from local run
nowcasts_update = {
    "consumption_bvar": 4.73,
    "investment_bvar": 6.92,
    "government_bvar": 4.14,
    "exports_comp_bvar": 4.79,
    "imports_comp_bvar": 4.83,
}

# Read existing log
import pandas as pd
log = pd.read_csv("docs/daily_log.csv")
# Update last row with BVAR values
for k, v in nowcasts_update.items():
    log.at[len(log)-1, k] = v
log.to_csv("docs/daily_log.csv", index=False)

# Print results
print("Updated daily_log.csv with BVAR component values:")
for k in sorted(nowcasts_update):
    print(f"  {k}: {nowcasts_update[k]:+.2f}%")
