"""Search OpenDOSM data catalogue for all available monthly datasets."""
import sys; sys.path.insert(0,"src")
import httpx

resp = httpx.get("https://api.data.gov.my/data-catalogue", timeout=30)
catalogue = resp.json()
print(f"Total datasets in catalogue: {len(catalogue)}")

# Find monthly datasets
monthly = []
for d in catalogue:
    if isinstance(d, dict):
        did = d.get("id", "")
        name = d.get("name", "")
        freq = d.get("frequency", "")
        catalog = d.get("catalog_name", "")
        if freq == "monthly" or freq == "MONTHLY":
            monthly.append((did, name, catalog))

print(f"\nMonthly datasets: {len(monthly)}")
for did, name, catalog in sorted(monthly):
    print(f"  [{catalog}] {did}: {name}")
