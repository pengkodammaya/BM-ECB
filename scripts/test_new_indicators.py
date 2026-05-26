"""Test new monthly indicators for nowcasting value."""
import sys; sys.path.insert(0,"src")
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
c = OpenDOSMClient()

candidates = [
    # Labour market (new dimensions)
    "lfs_month_status",      # Employment by status
    "lfs_month_youth",       # Youth unemployment
    "lfs_month_duration",    # Unemployment by duration
    # Trade (new dimensions)
    "trade_sitc_1d",         # Trade by SITC section
    "trade_enduse_bec",       # Imports by end use
    # Prices (additional)
    "fuelprice",              # Weekly fuel prices
    "sppi",                   # Services PPI (might be quarterly)
    "cpi_strata",             # CPI by urban/rural
    # Other
    "electricity_consumption", # Electricity
    "electricity_supply",      # Electricity supply
    "capacity_utilisation",    # Manufacturing capacity
    "productivity_qtr",        # Quarterly productivity
]

for did in candidates:
    try:
        df = c.fetch(did, limit=5)
        if len(df) == 0:
            print(f"EMPTY: {did}")
            continue

        # Check columns
        cols = list(df.columns)
        date_col = "date" if "date" in cols else cols[0]

        # Check full range
        df_full = c.fetch(did, limit=20000)
        if len(df_full) == 0:
            print(f"NO FULL: {did}")
            continue

        dmin = df_full[date_col].min() if date_col in df_full.columns else "?"
        dmax = df_full[date_col].max() if date_col in df_full.columns else "?"
        n = len(df_full)

        # Unique values of key categorical columns
        cat_cols = [c for c in cols if c != date_col and df_full[c].nunique() < 20]
        cat_info = ""
        for cc in cat_cols[:3]:
            cat_info += f" {cc}={list(df_full[cc].unique())[:5]}"

        print(f"FOUND: {did} -> {n} rows, {dmin} to {dmax}, cols={cols}{cat_info}")

    except Exception as e:
        print(f"ERR: {did} -> {str(e)[:80]}")

c.close()
