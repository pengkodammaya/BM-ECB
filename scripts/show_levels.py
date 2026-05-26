"""Double-check government spending (e2) from DOSM API."""
import sys; sys.path.insert(0,"src")
import pandas as pd
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

c = OpenDOSMClient()
df = c.fetch("gdp_qtr_real_demand", limit=20000)

print("=== Government Spending (e2) - Last 6 Quarters ===")
print()

for s in ["abs", "growth_qoq", "growth_yoy"]:
    sub = df[(df["type"] == "e2") & (df["series"] == s)].copy()
    sub["date"] = pd.to_datetime(sub["date"])
    sub = sub.sort_values("date")
    print(f"--- {s} ---")
    for _, row in sub.tail(6).iterrows():
        d = row["date"]
        ql = f"{d.year}-Q{(d.month-1)//3+1}"
        if s == "abs":
            print(f"  {ql}: MYR {row['value']:>12,.0f} million")
        else:
            print(f"  {ql}: {row['value']:+.1f}%")
    print()

# Share of GDP
abs_sub = df[(df["type"] == "e2") & (df["series"] == "abs")].copy()
abs_sub["date"] = pd.to_datetime(abs_sub["date"])
abs_sub = abs_sub.sort_values("date")
gdp_sub = df[(df["type"] == "e0") & (df["series"] == "abs")].copy()
gdp_sub["date"] = pd.to_datetime(gdp_sub["date"])

print("--- Government as % of GDP ---")
for _, row in abs_sub.tail(6).iterrows():
    d = row["date"]
    ql = f"{d.year}-Q{(d.month-1)//3+1}"
    gdp_row = gdp_sub[gdp_sub["date"] == row["date"]]
    if len(gdp_row) > 0:
        share = row["value"] / gdp_row.iloc[0]["value"] * 100
        print(f"  {ql}: {share:.1f}%")

c.close()
