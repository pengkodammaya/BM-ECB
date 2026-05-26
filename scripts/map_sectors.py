"""Map API GDP sector codes to names."""
import sys; sys.path.insert(0,"src")
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

c = OpenDOSMClient()

# Try lookup table
try:
    df_lookup = c.fetch("gdp_lookup", limit=200)
    print("=== Lookup table ===")
    print(df_lookup.to_string())
except Exception as e:
    print(f"No lookup: {e}")

# Get Q1 2026 sector values
df = c.fetch("gdp_qtr_real_supply", limit=5000)
q1_2026 = df[(df["date"] == "2026-01-01") & (df["series"] == "growth_yoy")]
print("\n=== Q1 2026 Sector YoY ===")
for _, row in q1_2026.iterrows():
    print(f"  {row['sector']}: {row['value']}%")

c.close()
