"""Test newly discovered OpenDOSM dataset IDs."""
import sys; sys.path.insert(0,"src")
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
c = OpenDOSMClient()
for did in ["trade_headline", "iowrt", "trade_sitc_1d"]:
    df = c.fetch(did, limit=5)
    if len(df) > 0:
        print(f"=== {did} ({len(df)} rows) ===")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
        print(f"  Last 2 rows:")
        print(df.tail(2).to_string())
        print()
c.close()
