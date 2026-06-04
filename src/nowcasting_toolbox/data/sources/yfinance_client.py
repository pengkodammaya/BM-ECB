"""Yahoo Finance data client for global market indicators.

Fetches monthly returns from global equity indices and commodities
using the yfinance library.

Indicators:
- SP500, Shanghai Composite, SOX, KLCI, STI (equity indices)
- Brent Crude, CPO (commodities)
- BDRY (shipping/demand proxy)
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Ticker -> (label, group) mapping
GLOBAL_INDICATORS: dict[str, tuple[str, str]] = {
    "^GSPC": ("sp500", "global_equity"),
    "000001.SS": ("shcomp", "global_equity"),
    "^SOX": ("sox", "global_equity"),
    "^KLSE": ("klci", "global_equity"),
    "^STI": ("sti", "global_equity"),
    "BZ=F": ("brent", "global_commodity"),
    "CPO=F": ("cpo", "global_commodity"),
    "BDRY": ("bdry", "global_demand"),
}


def fetch_yfinance_indicator(
    ticker: str,
    label: str,
    start_date: str = "2015-01-01",
    min_observations: int = 24,
) -> Optional[pd.DataFrame]:
    """Fetch a single indicator from Yahoo Finance.

    Parameters
    ----------
    ticker : str
        Yahoo Finance ticker symbol (e.g., "^GSPC", "BZ=F").
    label : str
        Column name for the output DataFrame.
    start_date : str
        Start date for data fetch (YYYY-MM-DD).
    min_observations : int
        Minimum observations required; skip if fewer.

    Returns
    -------
    pd.DataFrame or None
        DataFrame with 'date' and label columns (monthly MoM dlog growth).
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed. Install with: pip install yfinance")
        return None

    try:
        data = yf.download(ticker, start=start_date, progress=False)
        if data is None or len(data) == 0:
            logger.warning("No data returned for %s", ticker)
            return None

        # Handle MultiIndex columns (newer yfinance)
        if isinstance(data.columns, pd.MultiIndex):
            close_col = ("Close", ticker) if ("Close", ticker) in data.columns else data.columns[0]
        else:
            close_col = "Close" if "Close" in data.columns else "Adj Close"

        monthly = data[close_col].resample("ME").last().dropna()
        if len(monthly) < min_observations:
            logger.warning("Insufficient data for %s: %d < %d", ticker, len(monthly), min_observations)
            return None

        # Compute MoM dlog growth
        vals = monthly.values
        growth = np.full(len(vals), np.nan)
        for i in range(1, len(vals)):
            if vals[i-1] > 0:
                growth[i] = np.log(vals[i]) - np.log(vals[i-1])

        df = pd.DataFrame({"date": monthly.index, label: growth}).dropna()
        logger.info("yfinance %s (%s): %d monthly obs", label, ticker, len(df))
        return df

    except Exception as e:
        logger.warning("yfinance %s failed: %s", ticker, e)
        return None


def fetch_all_global_indicators(
    start_date: str = "2015-01-01",
) -> dict[str, pd.DataFrame]:
    """Fetch all global indicators from Yahoo Finance.

    Parameters
    ----------
    start_date : str
        Start date for data fetch.

    Returns
    -------
    dict[str, pd.DataFrame]
        Dict of {label: DataFrame} for each successfully fetched indicator.
    """
    results = {}
    for ticker, (label, group) in GLOBAL_INDICATORS.items():
        df = fetch_yfinance_indicator(ticker, label, start_date)
        if df is not None and not df.empty:
            results[label] = df
    return results
