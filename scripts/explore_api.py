"""Fetch sample data from OpenDOSM API to verify dataset availability."""
import sys
sys.path.insert(0, "src")

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

client = OpenDOSMClient()
try:
    for did in ["gdp_qtr_real", "cpi_headline", "lfs_month", "ppi", "cpi_core", "lfs_month_sa"]:
        try:
            df = client.fetch(did, limit=3)
            print(f"--- {did}: {len(df)} rows ---")
            print(f"  Columns: {list(df.columns)}")
            if len(df) > 0:
                date_range = f"{df['date'].min()} to {df['date'].max()}"
                print(f"  Date range: {date_range}")
                if len(df) > 0:
                    print(f"  Last row: {df.iloc[-1].to_dict()}")
            print()
        except Exception as e:
            print(f"--- {did}: ERROR: {type(e).__name__}: {e} ---")
            print()
finally:
    client.close()
