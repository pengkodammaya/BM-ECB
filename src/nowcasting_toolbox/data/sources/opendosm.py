"""OpenDOSM API client for fetching Malaysian macroeconomic data.

API docs: https://developer.data.gov.my/static-api/opendosm
Endpoint: GET https://api.data.gov.my/opendosm?id=<dataset_id>

Response format: {"value": [{...records...}], "Count": N}
Each record has a "date" field (ISO 8601) plus data columns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

BASE_URL = "https://api.data.gov.my/opendosm/"


class OpenDOSMClient:
    """Thin wrapper around the OpenDOSM static API.

    Parameters
    ----------
    timeout : float
        Request timeout in seconds.
    verbose : bool
        Log API calls at DEBUG level.
    """

    def __init__(self, timeout: float = 30.0, verbose: bool = False) -> None:
        self._client = httpx.Client(base_url=BASE_URL, timeout=timeout)
        self._verbose = verbose

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, dataset_id: str, **params: Any) -> pd.DataFrame:
        """Fetch a dataset from OpenDOSM and return it as a DataFrame.

        Parameters
        ----------
        dataset_id : str
            e.g. ``"cpi_headline"``, ``"lfs_month"``, ``"gdp_qtr_real"``.
        **params
            Optional query params forwarded to the API (limit, offset, date filters).

        Returns
        -------
        pd.DataFrame
            Flattened table with a ``date`` column (datetime64) and data columns.
        """
        all_params = {"id": dataset_id, **params}
        if self._verbose:
            logger.debug("GET / params=%s", all_params)
        resp = self._client.get("/", params=all_params)
        resp.raise_for_status()
        payload = resp.json()
        return self._to_dataframe(payload)

    def fetch_all(self, dataset_id: str, **base_params: Any) -> pd.DataFrame:
        """Fetch all records for a dataset using pagination.

        Parameters
        ----------
        dataset_id : str
            Dataset identifier.
        **base_params
            Additional query parameters forwarded to each page request.

        Returns
        -------
        pd.DataFrame
        """
        page_size = 5000
        offset = 0
        frames: list[pd.DataFrame] = []
        while True:
            params = {**base_params, "limit": page_size, "offset": offset}
            df = self.fetch(dataset_id, **params)
            if df.empty:
                break
            frames.append(df)
            offset += page_size
            if len(df) < page_size:
                break
        if not frames:
            return pd.DataFrame()
        result = pd.concat(frames, ignore_index=True)
        result.drop_duplicates(subset="date", keep="last", inplace=True)
        return result

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dataframe(payload: list[dict[str, Any]]) -> pd.DataFrame:
        records: list[dict[str, Any]] = payload if isinstance(payload, list) else payload.get("value", [])
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        return df


# ------------------------------------------------------------------
# Convenience function
# ------------------------------------------------------------------


def fetch_opendosm(dataset_id: str, **params: Any) -> pd.DataFrame:
    """One-shot fetch from OpenDOSM (creates & closes client)."""
    with OpenDOSMClient() as client:
        return client.fetch(dataset_id, **params)
