"""FRED (Federal Reserve Economic Data) client for US economic indicators.

Fetches monthly data from the FRED API for global demand indicators.

Indicators:
- US Industrial Production (INDPRO)
- US Consumer Sentiment (UMCSENT)
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Series ID -> (label, group) mapping
FRED_SERIES: dict[str, tuple[str, str]] = {
    "INDPRO": ("us_ip", "global_demand"),
    "UMCSENT": ("us_sentiment", "global_demand"),
}

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]  # seconds


def get_fred_api_key() -> str:
    """Get FRED API key from environment or file.

    Returns
    -------
    str
        API key, or empty string if not found.
    """
    # Prefer environment variable
    key = os.environ.get("FRED_API_KEY", "")
    if key:
        return key

    # Fall back to file
    key_path = Path(".fred_key")
    if key_path.exists():
        return key_path.read_text().strip()

    return ""


def fetch_fred_series(
    series_id: str,
    label: str,
    api_key: Optional[str] = None,
    start_date: str = "2015-01-01",
    min_observations: int = 24,
) -> Optional[pd.DataFrame]:
    """Fetch a single series from FRED.

    Parameters
    ----------
    series_id : str
        FRED series ID (e.g., "INDPRO", "UMCSENT").
    label : str
        Column name for the output DataFrame.
    api_key : str, optional
        FRED API key. If None, reads from env var or .fred_key file.
    start_date : str
        Start date for observations (YYYY-MM-DD).
    min_observations : int
        Minimum observations required; skip if fewer.

    Returns
    -------
    pd.DataFrame or None
        DataFrame with 'date' and label columns (monthly MoM dlog growth
        for indices, raw values for sentiment).
    """
    import httpx

    if api_key is None:
        api_key = get_fred_api_key()
    if not api_key:
        logger.warning("No FRED API key found. Set FRED_API_KEY env var or create .fred_key file.")
        return None

    # Fetch with retry
    resp = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.get(
                FRED_BASE_URL,
                params={
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "observation_start": start_date,
                },
                timeout=15,
            )
            if resp.status_code == 429:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                logger.warning("FRED 429 for %s, retrying in %ds...", series_id, wait)
                time.sleep(wait)
                resp = None
                continue
            break
        except Exception as e:
            logger.warning("FRED request error %s (attempt %d): %s", series_id, attempt + 1, e)
            return None

    if resp is None:
        logger.warning("FRED %s skipped after retries.", series_id)
        return None

    try:
        obs = resp.json().get("observations", [])
        records = [(o["date"], float(o["value"])) for o in obs if o["value"] != "."]
        if len(records) < min_observations:
            logger.warning("Insufficient FRED data for %s: %d < %d", series_id, len(records), min_observations)
            return None

        df = pd.DataFrame(records, columns=["date", label])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").resample("ME").last().dropna().reset_index()

        # For industrial production indices, compute dlog growth
        if series_id in ("INDPRO", "TCU"):
            vals = df[label].values
            growth = np.full(len(vals), np.nan)
            for i in range(1, len(vals)):
                if vals[i-1] > 0:
                    growth[i] = np.log(vals[i]) - np.log(vals[i-1])
            df[label] = growth
            df = df.dropna()

        logger.info("FRED %s: %d monthly obs", label, len(df))
        return df

    except Exception as e:
        logger.warning("FRED %s parse failed: %s", series_id, e)
        return None


def fetch_all_fred_indicators(
    api_key: Optional[str] = None,
    start_date: str = "2015-01-01",
) -> dict[str, pd.DataFrame]:
    """Fetch all FRED indicators.

    Parameters
    ----------
    api_key : str, optional
        FRED API key. If None, reads from env var or .fred_key file.
    start_date : str
        Start date for observations.

    Returns
    -------
    dict[str, pd.DataFrame]
        Dict of {label: DataFrame} for each successfully fetched indicator.
    """
    results = {}
    for series_id, (label, group) in FRED_SERIES.items():
        df = fetch_fred_series(series_id, label, api_key, start_date)
        if df is not None and not df.empty:
            results[label] = df
    return results
