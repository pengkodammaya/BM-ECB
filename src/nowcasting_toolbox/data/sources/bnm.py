"""BNM API client with historical data support via month-by-month endpoints.

Working endpoints:
- Interest Rate: /interest-rate/year/{year}/month/{month}?product=overall  (daily, 2015-present)
- Exchange Rate: /exchange-rate/USD/year/{year}/month/{month}               (daily, 2015-present)

Response format for interest rate (list):
  [{"date": "2024-01-02", "overnight": 3.0, "1_week": 3.05, ...}, ...]

Response format for exchange rate (dict with rate array):
  {"currency_code": "USD", "unit": 1, "rate": [{"date": "2024-01-02", "buying_rate": 4.576, ...}, ...]}
"""

from __future__ import annotations

import logging
import warnings
from datetime import date, datetime
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BASE_URL = "https://api.bnm.gov.my/public"
HEADERS = {"Accept": "application/vnd.BNM.API.v1+json"}


def fetch_bnm_historical(
    endpoint: str,
    start_year: int = 2015,
    end_year: Optional[int] = None,
    currency_code: Optional[str] = None,
    product: str = "overall",
    verbose: bool = False,
) -> pd.DataFrame:
    """Fetch historical BNM data month-by-month and aggregate to monthly frequency.

    Parameters
    ----------
    endpoint : str
        One of "interest-rate" or "exchange-rate".
    start_year : int
        First year to fetch (default 2015).
    end_year : int, optional
        Last year (default: current year).
    currency_code : str, optional
        For exchange-rate endpoint, e.g. "USD".
    product : str
        For interest-rate endpoint: "overall", "interbank", "money_market_operations".
    verbose : bool

    Returns
    -------
    pd.DataFrame with columns: date (month-end), value
    """
    if end_year is None:
        end_year = datetime.now().year

    all_daily = []
    total_months = (end_year - start_year + 1) * 12

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        client = httpx.Client(base_url=BASE_URL, timeout=30, verify=False, headers=HEADERS)

        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                # Skip future months
                today = date.today()
                if year > today.year or (year == today.year and month > today.month):
                    break

                try:
                    if endpoint == "interest-rate":
                        url = f"/interest-rate/year/{year}/month/{month}"
                        params = {"product": product}
                        resp = client.get(url, params=params)
                        resp.raise_for_status()
                        data = resp.json()
                        records = data.get("data", [])
                        if isinstance(records, list):
                            all_daily.extend(records)

                    elif endpoint == "exchange-rate":
                        cc = currency_code or "USD"
                        url = f"/exchange-rate/{cc}/year/{year}/month/{month}"
                        resp = client.get(url)
                        resp.raise_for_status()
                        data = resp.json()
                        # Response is a dict with rate array inside
                        result = data.get("data", {})
                        if isinstance(result, dict):
                            records = result.get("rate", [])
                            if isinstance(records, list):
                                all_daily.extend(records)

                except Exception as e:
                    if verbose:
                        logger.debug("BNM %s %d-%02d failed: %s", endpoint, year, month, e)

        client.close()

    if not all_daily:
        logger.warning("BNM %s: no data fetched", endpoint)
        return pd.DataFrame()

    # Convert to DataFrame
    df = pd.DataFrame(all_daily)
    if "date" not in df.columns:
        logger.warning("BNM %s: no 'date' column in response", endpoint)
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    # Extract the value column
    if endpoint == "interest-rate":
        # Use overnight rate, fall back to 1_week
        if "overnight" in df.columns:
            df["value"] = pd.to_numeric(df["overnight"], errors="coerce")
        elif "1_week" in df.columns:
            df["value"] = pd.to_numeric(df["1_week"], errors="coerce")
        else:
            return pd.DataFrame()

    elif endpoint == "exchange-rate":
        # Use buying_rate (middle_rate is often null in BNM API)
        if "buying_rate" in df.columns:
            df["value"] = pd.to_numeric(df["buying_rate"], errors="coerce")
        elif "selling_rate" in df.columns:
            df["value"] = pd.to_numeric(df["selling_rate"], errors="coerce")
        else:
            return pd.DataFrame()

    # Drop NaN values
    df = df[["date", "value"]].dropna()

    # Aggregate daily -> monthly: take last value of each month
    monthly = df.set_index("date").resample("ME").last().dropna().reset_index()

    if verbose:
        logger.info("BNM %s: %d daily -> %d monthly obs (%s to %s)",
                     endpoint, len(df), len(monthly),
                     monthly["date"].min().date(), monthly["date"].max().date())

    return monthly


def fetch_interest_rate_history(
    start_year: int = 2015,
    end_year: Optional[int] = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """Fetch full historical overnight interbank rate (monthly)."""
    return fetch_bnm_historical(
        "interest-rate", start_year, end_year,
        product="overall", verbose=verbose,
    )


def fetch_exchange_rate_history(
    start_year: int = 2015,
    end_year: Optional[int] = None,
    currency_code: str = "USD",
    verbose: bool = False,
) -> pd.DataFrame:
    """Fetch full historical USD/MYR exchange rate (monthly)."""
    return fetch_bnm_historical(
        "exchange-rate", start_year, end_year,
        currency_code=currency_code, verbose=verbose,
    )
