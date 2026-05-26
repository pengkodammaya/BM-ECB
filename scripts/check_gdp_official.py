"""Fetch latest GDP data from OpenDOSM and compare with our nowcast."""
import sys
sys.path.insert(0, "src")

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
from nowcasting_toolbox.data.sources.cache import DataCache

# Clear cache for fresh data
cache = DataCache()
cache.invalidate("gdp_qtr_real_sa")
cache.invalidate("gdp_qtr_real")

client = OpenDOSMClient()

for did in ["gdp_qtr_real_sa", "gdp_qtr_real"]:
    df = client.fetch(did, limit=20000)
    print(f"=== {did} ({len(df)} rows) ===")
    print(f"  Columns: {list(df.columns)}")
    
    series_vals = df["series"].unique()
    print(f"  Series types: {list(series_vals)}")
    
    # Show most recent entries for each series type
    last_dates = sorted(df["date"].unique())[-6:]
    print(f"  Last 6 dates: {[str(d.date()) for d in last_dates]}")
    
    for s in series_vals:
        sub = df[(df["series"] == s) & (df["date"].isin(last_dates))]
        if len(sub) > 0:
            print(f"  Series={s}:")
            for _, row in sub.iterrows():
                print(f"    {str(row['date'].date()):12s}  value={row['value']:>12.1f}")
    print()

client.close()

# Also check DOSM dashboard for official Q1 2026 GDP
import httpx
resp = httpx.get("https://open.dosm.gov.my/dashboard/gdp", timeout=15)
print(f"Dashboard status: {resp.status_code}")
