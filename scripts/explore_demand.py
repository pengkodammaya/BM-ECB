"""Explore GDP demand-side components for nowcasting."""
import sys; sys.path.insert(0,"src")
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

c = OpenDOSMClient()
df = c.fetch("gdp_qtr_real_demand", limit=20000)

print("=== GDP Demand Components ===")
print("Types:", sorted(df["type"].unique()))
print("Series:", df["series"].unique())
print()

last_dates = sorted(df["date"].unique())[-3:]
for t in sorted(df["type"].unique()):
    for s in df["series"].unique():
        sub = df[(df["type"]==t) & (df["series"]==s)]
        if len(sub) > 0:
            last = sub.iloc[-1]
            print(f"  type={t}, series={s}: {len(sub)} obs, last={last['date'].date()} value={last['value']}")

print()
print("=== Demand-side type descriptions (from lookup) ===")
df_lookup = c.fetch("gdp_lookup", limit=500)
if df_lookup is not None and len(df_lookup) > 0:
    demand = df_lookup[df_lookup["code"].str.startswith("e", na=False)]
    for _, r in demand.iterrows():
        if len(r["code"]) <= 2:  # top-level only (e0, e1, e2, etc.)
            print(f"  {r['code']}: {r['desc_en']}")

c.close()
