"""DEPRECATED — kept only so existing CI steps that call it don't fail.

The dashboard data pipeline changed: `daily_update.py` now writes the canonical
`docs/data.json` (rolled forward by quarter, scored against frozen first-release
vintages), and `docs/dashboard.html` already fetches `data.json` directly. This
script therefore no longer builds data or rewrites the HTML — doing so would
overwrite the good data.json with hardcoded values and re-introduce the stray
`}`-append bug in dashboard.html.

It now simply verifies data.json exists and exits cleanly.
"""
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_dashboard")

data_path = Path("docs/data.json")
if data_path.exists():
    logger.info("data.json present (written by daily_update.py). Nothing to do.")
else:
    logger.warning("data.json not found — run daily_update.py first. "
                   "This script is deprecated and no longer generates data.")
# Always exit 0 so it never breaks the GitHub Action.
sys.exit(0)
