"""Trading Economics consensus forecast client for Malaysia.

Scrapes quarterly GDP and component forecasts from tradingeconomics.com/malaysia/forecast.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

TE_FORECAST_URL = "https://tradingeconomics.com/malaysia/forecast"

# Component mapping: TE indicator prefix -> our component key
COMPONENT_MAP = {
    "Consumer Spending": "consumption",
    "Gross Fixed Capital Formation": "investment",
    "Government Spending": "government",
    "Exports": "exports",
    "Imports": "imports",
}


def fetch_consensus_forecasts() -> dict:
    """Fetch Malaysia GDP and component consensus forecasts from Trading Economics.

    Returns
    -------
    dict with keys:
        - gdp_yoy: dict of {quarter: forecast} (YoY %)
        - gdp_qoq: dict of {quarter: forecast} (QoQ %)
        - components: dict of {component: {quarter: level}} (MYR Million)
        - source: "Trading Economics"
        - url: source URL
    """
    result = {
        "gdp_yoy": {},
        "gdp_qoq": {},
        "components": {},
        "source": "Trading Economics",
        "url": TE_FORECAST_URL,
    }

    try:
        resp = httpx.get(TE_FORECAST_URL, timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        html = resp.text

        rows = _parse_forecast_table(html)
        quarter_labels = ["Q2 2026", "Q3 2026", "Q4 2026", "Q1 2027"]

        for row in rows:
            indicator = row.get("indicator", "")
            forecasts = row.get("forecasts", {})

            # GDP YoY growth
            if "GDP Annual Growth" in indicator or "GDP Growth Rate YoY" in indicator:
                result["gdp_yoy"] = forecasts

            # GDP QoQ growth
            elif "GDP Growth Rate" in indicator and "YoY" not in indicator:
                result["gdp_qoq"] = forecasts

            # Component levels
            else:
                for te_name, comp_key in COMPONENT_MAP.items():
                    if indicator.startswith(te_name):
                        result["components"][comp_key] = {
                            "levels": forecasts,  # MYR Million
                            "unit": "MYR Million",
                        }
                        break

        logger.info("Fetched consensus: GDP YoY=%s, Components=%s",
                    result["gdp_yoy"], list(result["components"].keys()))

    except Exception as e:
        logger.warning("Failed to fetch Trading Economics forecasts: %s", e)

    return result


def _parse_forecast_table(html: str) -> list[dict]:
    """Parse the Trading Economics forecast table HTML."""
    rows = []
    row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    cell_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)

    for row_match in row_pattern.finditer(html):
        row_html = row_match.group(1)
        cells = cell_pattern.findall(row_html)

        if len(cells) >= 3:
            clean_cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            indicator = clean_cells[0]

            # Clean indicator name (remove units in parentheses and extra whitespace)
            indicator = re.sub(r'\s*\(.*?\)\s*$', '', indicator).strip()
            indicator = re.sub(r'\s+', ' ', indicator)

            # Skip headers
            if not indicator or indicator in ('Markets', 'Overview', 'GDP', 'Labour',
                                               'Prices', 'Money', 'Trade', 'Business',
                                               'Consumer', 'Government', 'Housing'):
                continue

            forecasts = {}
            quarter_labels = ["Q2 2026", "Q3 2026", "Q4 2026", "Q1 2027"]

            for i, label in enumerate(quarter_labels):
                col_idx = i + 2  # Skip indicator + actual
                if col_idx < len(clean_cells):
                    val_str = clean_cells[col_idx]
                    try:
                        val = float(val_str.replace('%', '').replace(',', ''))
                        forecasts[label] = val
                    except (ValueError, TypeError):
                        pass

            if forecasts:
                rows.append({"indicator": indicator, "forecasts": forecasts})

    return rows


def get_consensus_gdp_forecast(quarter: str) -> Optional[float]:
    """Get consensus GDP forecast for a specific quarter."""
    if "-" in quarter:
        parts = quarter.split("-")
        quarter = f"Q{parts[1].replace('Q', '')} {parts[0]}"

    forecasts = fetch_consensus_forecasts()
    return forecasts.get("gdp_yoy", {}).get(quarter)
