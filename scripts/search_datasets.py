"""Search for available OpenDOSM datasets by trying common IDs."""
import sys
sys.path.insert(0, "src")

from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

client = OpenDOSMClient()

# Common IDs to try based on the data catalogue
candidates = [
    # Industrial
    "ipi", "industrial_production", "index_industrial_production",
    # Manufacturing
    "manufacturing", "manufacturing_statistics", "manufacturing_monthly",
    # External trade
    "external_trade", "exports", "imports", "trade_balance",
    "exports_monthly", "imports_monthly",
    # Services / WRT  
    "wrt", "wholesale_retail", "services_index",
    "volume_index_services",
    # Leading indicators
    "leading_index", "coincident_index", "lagging_index",
    "economic_indicators",
    # Construction
    "construction", "construction_statistics",
    # Money / financial
    "money_supply", "monetary",
    # GDP variants
    "gdp_qtr_nominal", "gdp_qtr_real_sa",
]

for did in candidates:
    try:
        df = client.fetch(did, limit=1)
        if len(df) > 0:
            cols = list(df.columns)
            print(f"FOUND: {did} -> {cols}")
        else:
            print(f"EMPTY: {did}")
    except Exception as e:
        err = str(e)[:80]
        print(f"FAIL:  {did} -> {err}")

client.close()
