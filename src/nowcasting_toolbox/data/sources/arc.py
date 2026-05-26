"""DOSM Advance Release Calendar (ARC) parser.

The ARC (https://www.dosm.gov.my/portal-main/arc) lists the scheduled
publication dates for all DOSM statistical releases. This module scrapes
the calendar and builds a mapping of:

    series -> [(release_date, reference_period), ...]

This mapping is critical for pseudo-real-time backtesting and for the
scheduler to know when new data should have become available.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import pandas as pd
import httpx

logger = logging.getLogger(__name__)

ARC_URL = "https://www.dosm.gov.my/portal-main/arc"

# Known ARC series names mapped to dataset IDs for OpenDOSM
# Extended during implementation as more are discovered.
ARC_SERIES_MAP: dict[str, str] = {
    "Consumer Price Index": "cpi_headline",
    "Producer Price Index": "ppi",
    "Index of Industrial Production": "ipi",  # TBC during implementation
    "Monthly Manufacturing Statistics": "manufacturing",  # TBC
    "Performance of Wholesale & Retail Trade": "wrt",  # TBC
    "Monthly External Trade Statistics": "external_trade",  # TBC
    "Labour Force": "lfs_month",
    "Gross Domestic Product": "gdp_qtr_real",
    "Leading Index": "leading_index",  # TBC
}


@dataclass
class Release:
    """A single ARC release entry."""
    release_date: date
    title: str
    reference_period: str  # e.g. "MAR 2026", "Q1 2026"
    dataset_id: Optional[str] = None  # matched OpenDOSM id if known


class ARCParser:
    """Parse the DOSM Advance Release Calendar.

    Can use either live scraping (default) or a pre-cached static copy.
    During initial implementation this uses static heuristics;
    live scraping will be activated once the HTML structure is confirmed.
    """

    def __init__(self, use_cache: bool = True) -> None:
        self._use_cache = use_cache

    def fetch_releases(self, year: int | None = None) -> list[Release]:
        """Return ARC entries for a given year (default: current year).

        Parameters
        ----------
        year : int, optional
            Calendar year. Defaults to current year.

        Returns
        -------
        list[Release]
        """
        raw = self._scrape_arc(year or datetime.now().year)
        return self._parse(raw)

    def build_release_schedule(
        self, start_year: int = 2020, end_year: int | None = None
    ) -> pd.DataFrame:
        """Build a full release schedule DataFrame.

        Returns DataFrame with columns: release_date, dataset_id, reference_period.
        """
        end_year = end_year or datetime.now().year
        all_releases: list[Release] = []
        for y in range(start_year, end_year + 1):
            all_releases.extend(self.fetch_releases(y))
        return self._to_dataframe(all_releases)

    def get_publication_lag(self, dataset_id: str) -> int:
        """Estimate publication lag (in days) for a given dataset.

        Returns the typical number of days between reference period end
        and release date. Used for ragged-edge construction.
        """
        schedule = self.build_release_schedule()
        subset = schedule[schedule["dataset_id"] == dataset_id]
        if subset.empty:
            return 45  # Conservative default
        # Compute median lag
        subset = subset.copy()
        subset["ref_end"] = pd.to_datetime(subset["reference_period"])
        subset["lag"] = (subset["release_date"] - subset["ref_end"]).dt.days
        return int(subset["lag"].median())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _scrape_arc(year: int) -> list[dict[str, str]]:
        """Scrape ARC HTML for a given year.

        Currently returns an empty list; will be implemented once
        we can inspect the page structure. The ARC is loaded via
        client-side JavaScript, so we may need to use the site's
        download-calendar endpoint instead.
        """
        try:
            resp = httpx.get(
                "https://www.dosm.gov.my/site/downloadarc",
                params={"search_year": str(year), "search_month": "All", "action": "download"},
                timeout=30,
            )
            resp.raise_for_status()
            # Try parsing as CSV (the download endpoint usually returns CSV)
            import io
            df = pd.read_csv(io.StringIO(resp.text))
            records: list[dict[str, str]] = []
            for _, row in df.iterrows():
                records.append({
                    "release_date": str(row.get("Date", "")),
                    "title": str(row.get("Release", "")),
                    "reference_period": str(row.get("Reference Period", "")),
                })
            return records
        except Exception as exc:
            logger.warning("ARC scrape failed for year %s: %s", year, exc)
            return []

    @staticmethod
    def _parse(raw: list[dict[str, str]]) -> list[Release]:
        releases: list[Release] = []
        for entry in raw:
            rdate_str = entry.get("release_date", "").strip()
            title = entry.get("title", "").strip()
            ref = entry.get("reference_period", "").strip()
            if not rdate_str or not title:
                continue
            try:
                rdate = datetime.strptime(rdate_str, "%d %B %Y").date()
            except ValueError:
                try:
                    rdate = datetime.strptime(rdate_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
            dataset_id = ARC_SERIES_MAP.get(title)
            releases.append(Release(
                release_date=rdate,
                title=title,
                reference_period=ref,
                dataset_id=dataset_id,
            ))
        return releases

    @staticmethod
    def _to_dataframe(releases: list[Release]) -> pd.DataFrame:
        if not releases:
            return pd.DataFrame(columns=["release_date", "title", "dataset_id", "reference_period"])
        records = [
            {
                "release_date": r.release_date,
                "title": r.title,
                "dataset_id": r.dataset_id,
                "reference_period": r.reference_period,
            }
            for r in releases
        ]
        df = pd.DataFrame(records)
        df["release_date"] = pd.to_datetime(df["release_date"])
        return df
