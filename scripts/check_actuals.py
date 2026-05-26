"""Query actual API values for investment, exports, imports."""
import sys; sys.path.insert(0,"src")
import pandas as pd
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

c = OpenDOSMClient()
df = c.fetch("gdp_qtr_real_demand", limit=20000)

for tcode in ["e3", "e5", "e6"]:
    label = {"e3": "Investment (GFCF)", "e5": "Exports", "e6": "Imports"}[tcode]
    for s in ["growth_yoy", "abs"]:
        sub = df[(df["type"] == tcode) & (df["series"] == s)].copy()
        sub["date"] = pd.to_datetime(sub["date"])
        sub = sub.sort_values("date")
        last = sub.iloc[-1]
        unit = "%" if "yoy" in s else "MYR million"
        print(f"{label}: {s} = {last['value']} {unit} (as of {last['date'].date()})")
    print()

c.close()
