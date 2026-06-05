"""Trading Economics consensus forecast client for Malaysia.

Scrapes quarterly GDP forecasts from tradingeconomics.com/malaysia/forecast.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

TE_URL = "https://tradingeconomics.com/malaysia/forecast"


def fetch_consensus_forecasts() -> dict:
    """Fetch Malaysia GDP consensus forecasts from Trading Economics.

    Returns
    -------
    dict with keys:
        - gdp_yoy: dict of {quarter: forecast} (e.g. {"Q2 2026": 5.2, "Q3 2026": 4.9})
        - gdp_qoq: dict of {quarter: forecast}
        - source: "Trading Economics"
        - url: source URL
    """
    result = {
        "gdp_yoy": {},
        "gdp_qoq": {},
        "source": "Trading Economics",
        "url": TE_URL,
    }

    try:
        resp = httpx.get(TE_URL, timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        html = resp.text

        # Parse the forecast table from HTML
        # Look for GDP Annual Growth Rate row
        # Pattern: <td>GDP Annual Growth Rate (%)</td> followed by forecast columns
        
        # Extract table rows
        rows = _parse_forecast_table(html)
        
        for row in rows:
            indicator = row.get("indicator", "")
            if "GDP Annual Growth" in indicator or "GDP Growth Rate YoY" in indicator:
                result["gdp_yoy"] = row.get("forecasts", {})
            elif "GDP Growth Rate" in indicator and "YoY" not in indicator:
                result["gdp_qoq"] = row.get("forecasts", {})

        logger.info("Fetched consensus forecasts: YoY=%s, QoQ=%s", 
                    result["gdp_yoy"], result["gdp_qoq"])

    except Exception as e:
        logger.warning("Failed to fetch Trading Economics forecasts: %s", e)

    return result


def _parse_forecast_table(html: str) -> list[dict]:
    """Parse the Trading Economics forecast table HTML.

    Returns list of dicts with 'indicator' and 'forecasts' keys.
    """
    rows = []
    
    # Find the forecast table section
    # Trading Economics uses a specific HTML structure
    # Look for rows with indicator names and forecast values
    
    # Pattern to find table rows with indicator and forecasts
    # The table has columns: Actual, Q2/26, Q3/26, Q4/26, Q1/27
    
    # Split by table rows
    row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    cell_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
    
    for row_match in row_pattern.finditer(html):
        row_html = row_match.group(1)
        cells = cell_pattern.findall(row_html)
        
        if len(cells) >= 3:  # At least indicator + 2 forecast columns
            # Clean HTML tags from cells
            clean_cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            
            indicator = clean_cells[0]
            
            # Skip header rows and non-numeric rows
            if not indicator or indicator in ('Markets', 'Overview', 'GDP', 'Labour', 
                                               'Prices', 'Money', 'Trade', 'Business', 
                                               'Consumer', 'Government', 'Housing'):
                continue
            
            # Extract forecast values (columns after indicator)
            forecasts = {}
            # The columns are typically: Actual, Q2/26, Q3/26, Q4/26, Q1/27
            quarter_labels = ["Q2 2026", "Q3 2026", "Q4 2026", "Q1 2027"]
            
            for i, label in enumerate(quarter_labels):
                col_idx = i + 2  # Skip indicator and actual columns
                if col_idx < len(clean_cells):
                    val_str = clean_cells[col_idx]
                    try:
                        val = float(val_str.replace('%', '').replace(',', ''))
                        forecasts[label] = val
                    except (ValueError, TypeError):
                        pass
            
            if forecasts:
                rows.append({
                    "indicator": indicator,
                    "forecasts": forecasts,
                })
    
    return rows


def get_consensus_gdp_forecast(quarter: str) -> Optional[float]:
    """Get consensus GDP forecast for a specific quarter.

    Parameters
    ----------
    quarter : str
        Quarter in format "Q2 2026" or "2026-Q2"

    Returns
    -------
    float or None
        Consensus forecast (YoY %), or None if not available.
    """
    # Normalize quarter format
    if "-" in quarter:
        parts = quarter.split("-")
        quarter = f"Q{parts[1].replace('Q', '')} {parts[0]}"

    forecasts = fetch_consensus_forecasts()
    return forecasts.get("gdp_yoy", {}).get(quarter)
