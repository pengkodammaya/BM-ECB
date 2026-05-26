"""Explore BNM API and new OpenDOSM dataset IDs for expanded indicator set."""
import sys; sys.path.insert(0,"src")
import httpx
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

print("=" * 60)
print("BNM API Exploration")
print("=" * 60)

# BNM API endpoints to try
bnm_endpoints = [
    "/public/exchange-rate",
    "/public/opr", 
    "/public/interbank-rate",
    "/public/interest-rate",
    "/public/interest-volumes",
    "/public/money-supply",
    "/public/consumer-credit",
    "/public/kijang-emas",
    "/public/fx-turn-over",
]

for ep in bnm_endpoints:
    try:
        resp = httpx.get(
            f"https://api.bnm.gov.my{ep}",
            headers={"Accept": "application/vnd.BNM.API.v1+json"},
            timeout=15,
            verify=False,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "data" in data:
                print(f"FOUND: {ep} -> {len(data['data'])} records")
                if data["data"]:
                    print(f"  Keys: {list(data['data'][0].keys()) if isinstance(data['data'][0], dict) else 'list'}")
                    if isinstance(data["data"][0], dict):
                        print(f"  Sample: {data['data'][0]}")
            elif isinstance(data, list) and len(data) > 0:
                print(f"FOUND: {ep} -> {len(data)} records (list)")
                print(f"  Sample: {data[0]}")
            else:
                print(f"FOUND: {ep} -> empty?")
        else:
            print(f"NO: {ep} -> HTTP {resp.status_code}")
    except Exception as e:
        print(f"ERR: {ep} -> {str(e)[:80]}")

print()
print("=" * 60)
print("OpenDOSM New Dataset IDs")
print("=" * 60)

# Known from ARC but need correct IDs
new_ids = [
    # External trade
    "external_trade", "exports", "imports", "trade_balance",
    "exports_monthly", "imports_monthly", "merchandise_trade",
    # Construction
    "construction", "construction_statistics", "construction_sector",
    "building", "building_statistics",
    # WRT
    "wrt", "wholesale_retail", "wholesale_retail_trade",
    "retail_trade", "wholesale_trade",
    # Services
    "services", "services_index", "volume_index_services",
    "services_statistics", "quarterly_services",
    # Other
    "rubber", "rubber_statistics", "monthly_rubber",
    "motor_vehicle", "vehicle_sales",
    "tourism", "tourist_arrivals",
    "crude_oil", "palm_oil", "commodity_prices",
    "capacity_utilisation",
    "business_tendency",
]

c = OpenDOSMClient()
for did in new_ids:
    try:
        df = c.fetch(did, limit=3)
        if len(df) > 0:
            cols = list(df.columns)
            print(f"FOUND: {did} -> {cols}")
            print(f"  Last: {df.iloc[-1].to_dict()}")
    except Exception as e:
        err = str(e)[:80]
        # Only print interesting errors
        if "404" not in err and "400" not in err:
            print(f"ERR: {did} -> {err}")

# Special: try with different base patterns
special = [
    "monthly_external_trade",
    "trade_external",
    "external_sector",
    "export", "import",
    "building_construction",
]

for did in special:
    try:
        df = c.fetch(did, limit=3)
        if len(df) > 0:
            cols = list(df.columns)
            print(f"FOUND: {did} -> {cols}")
    except Exception:
        pass

c.close()
