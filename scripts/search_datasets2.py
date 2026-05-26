"""Search for more OpenDOSM dataset IDs."""
import sys
sys.path.insert(0, "src")
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

client = OpenDOSMClient()

more = [
    "mfg", "manufacturing_output", "industrial_output",
    "export", "import", "trade", "merchandise_trade",
    "construction_sector", "building", "cement",
    "credit", "loan", "m3", "m2",
    "retail", "wholesale", "trade_wholesale",
    "rubber", "palm_oil", "crude_oil", "commodity",
    "bop_current", "current_account",
    "motor_vehicle", "vehicle_sales",
    "tourism", "tourist_arrivals",
    "ipi_1d", "ppi_1d",  # 1-digit breakdowns
    "gdp_qtr_real_supply", "gdp_qtr_real_demand",
]

for did in more:
    try:
        df = client.fetch(did, limit=1)
        if len(df) > 0:
            cols = list(df.columns)
            print(f"FOUND: {did} -> {cols}")
    except Exception:
        pass

client.close()
