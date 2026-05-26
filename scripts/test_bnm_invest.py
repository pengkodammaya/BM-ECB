"""Test BNM investment and construction indicators."""
import sys; sys.path.insert(0,"src")
import httpx, json, warnings

warnings.filterwarnings("ignore")
client = httpx.Client(timeout=30, verify=False, 
    headers={"Accept": "application/vnd.BNM.API.v1+json"},
    base_url="https://api.bnm.gov.my/public")

# Test with indicator=month for monthly data
resp = client.get("/msb/3.5.7/year/2024", params={"indicator": "month"})
data = resp.json()
records = data.get("data", [])
print(f"3.5.7 indicator=month: {len(records)} records")
if records:
    r = records[0]
    print(f"  Keys: {list(r.keys())}")
    last = records[-1]
    print(f"  Last: {last}")

# Also try indicator=period
resp_p = client.get("/msb/3.5.7/year/2024", params={"indicator": "period"})
data_p = resp_p.json()
records_p = data_p.get("data", [])
print(f"\n3.5.7 indicator=period: {len(records_p)} records")
if records_p:
    print(f"  Sample: {records_p[0]}")

# Try latest (no year)
resp_l = client.get("/msb/3.5.7")
data_l = resp_l.json()
records_l = data_l.get("data", [])
print(f"\n3.5.7 Latest (no params): {len(records_l) if isinstance(records_l,list) else type(records_l).__name__}")

client.close()
