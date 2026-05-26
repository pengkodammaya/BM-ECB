"""Vintage builder using live ARC data for exact publication dates.

Replaces the hardcoded MALAYSIA_PUBLICATION_LAGS with actual release
dates from the DOSM Advance Release Calendar (ICS format).

Usage:
    from nowcasting_toolbox.eval.vintage import ARCVintageBuilder
    from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule

    schedule = build_publication_schedule(years=[2020, 2021, 2022, 2023, 2024, 2025, 2026])
    vb = ARCVintageBuilder(schedule)
    X_vintage = vb.build(X_full, datet, vintage_date, var_names)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from nowcasting_toolbox.data.sources.arc_parser import (
    build_publication_schedule,
    match_dataset_id,
    extract_reference_period,
)

FloatArray = NDArray[np.float64]

# ---------------------------------------------------------------------------
# Hardcoded fallback (used when ARC is unavailable)
# ---------------------------------------------------------------------------

FALLBACK_LAGS: dict[str, int] = {
    "ipi": 8, "cpi_headline": 19, "cpi_core": 19,
    "ppi": 25, "u_rate": 12, "p_rate": 12,
    "leading": 55, "coincident": 55,
    "gdp": 45,
}


@dataclass
class SeriesReleaseSchedule:
    """Release schedule for a single dataset series.

    Maps reference period (year, month_end) → release_date.
    """
    dataset_id: str
    releases: dict[tuple[int, int], date] = field(default_factory=dict)

    def get_release_date(self, ref_year: int, ref_month: int) -> Optional[date]:
        """Get the release date for a given reference period."""
        return self.releases.get((ref_year, ref_month))

    def is_available_at(self, ref_year: int, ref_month: int, as_of: date) -> bool:
        """Check if data for (ref_year, ref_month) was released by as_of."""
        rel = self.get_release_date(ref_year, ref_month)
        if rel is None:
            return False
        return rel <= as_of


class ARCVintageBuilder:
    """Vintage builder using live ARC release dates.

    Parameters
    ----------
    schedule : list[dict] or None
        Output from build_publication_schedule().
        If None, builds from live ARC (2020-current year).
    cache_dir : Path, optional
        Directory for ARC ICS cache files.
    """

    def __init__(
        self,
        schedule: list[dict] | None = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.cache_dir = cache_dir or Path("data/malaysia")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if schedule is None:
            schedule = build_publication_schedule(cache_dir=self.cache_dir)
        self.schedule = schedule

        # Index by dataset_id → SeriesReleaseSchedule
        self._series_schedules: dict[str, SeriesReleaseSchedule] = {}
        self._build_index()

    def _build_index(self) -> None:
        """Build lookup index from schedule list."""
        for entry in self.schedule:
            did = entry["dataset_id"]
            if did is None:
                continue
            ref_year = entry.get("ref_year")
            ref_month_end = entry.get("ref_month_end")
            if ref_year is None or ref_month_end is None:
                continue

            rel_date = entry["release_date"]
            if not isinstance(rel_date, date):
                rel_date = date.fromisoformat(str(rel_date))

            if did not in self._series_schedules:
                self._series_schedules[did] = SeriesReleaseSchedule(dataset_id=did)

            key = (ref_year, ref_month_end)
            # If multiple releases for same period, keep the earliest
            existing = self._series_schedules[did].releases.get(key)
            if existing is None or rel_date < existing:
                self._series_schedules[did].releases[key] = rel_date

    def get_release_date(
        self,
        dataset_id: str,
        ref_year: int,
        ref_month: int,
    ) -> Optional[date]:
        """Get exact release date for a dataset's reference period."""
        sched = self._series_schedules.get(dataset_id)
        if sched is None:
            return None
        return sched.get_release_date(ref_year, ref_month)

    def build(
        self,
        X_full: FloatArray,
        datet: FloatArray,
        vintage_date: date,
        var_names: list[str],
        dataset_ids: Optional[list[str]] = None,
    ) -> FloatArray:
        """Return the data matrix as it would have looked at vintage_date.

        Uses exact ARC release dates where available, falling back to
        hardcoded approximate lags for unmatched series.

        Parameters
        ----------
        X_full : (T, N) array
            Complete data matrix.
        datet : (T, 2) array
            Year-month for each row.
        vintage_date : date
            The "as of" date for this vintage.
        var_names : list[str]
            Variable names (used for fallback lags).
        dataset_ids : list[str], optional
            Dataset IDs corresponding to each variable.
            If None, uses var_names as dataset IDs.

        Returns
        -------
        X_vintage : (T, N) array
        """
        T, N = X_full.shape
        X_vint = X_full.copy()

        if dataset_ids is None:
            dataset_ids = var_names

        for j in range(N):
            did = dataset_ids[j] if j < len(dataset_ids) else var_names[j]
            sched = self._series_schedules.get(did)

            for t in range(T - 1, -1, -1):
                if np.isnan(X_full[t, j]):
                    continue
                y, m = int(datet[t, 0]), int(datet[t, 1])

                # Try ARC exact date first
                if sched is not None:
                    rel = sched.get_release_date(y, m)
                    if rel is not None:
                        if rel <= vintage_date:
                            break  # available
                        else:
                            X_vint[t, j] = np.nan
                            continue

                # Fallback: approximate lag (days after month end)
                fallback_lag_days = FALLBACK_LAGS.get(did, 30)
                ref_end = date(y, m, 1) + timedelta(days=32)
                ref_end = ref_end.replace(day=1) - timedelta(days=1)  # last day of month
                approx_release = ref_end + timedelta(days=fallback_lag_days)

                if approx_release <= vintage_date:
                    break
                else:
                    X_vint[t, j] = np.nan

        return X_vint

    def describe_coverage(self) -> dict:
        """Return summary stats about schedule coverage."""
        return {
            "total_releases": len(self.schedule),
            "datasets_with_schedule": sorted(self._series_schedules.keys()),
            "num_datasets": len(self._series_schedules),
            "date_range": (
                min(self.schedule, key=lambda e: e["release_date"])["release_date"]
                if self.schedule else None,
                max(self.schedule, key=lambda e: e["release_date"])["release_date"]
                if self.schedule else None,
            ),
        }


# ---------------------------------------------------------------------------
# Convenience: generate a sequence of vintage dates for backtesting
# ---------------------------------------------------------------------------


def generate_vintage_dates(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    frequency: str = "monthly",
    day_of_month: int = 1,
) -> list[date]:
    """Generate a list of vintage dates for backtesting."""
    dates = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        dates.append(date(y, m, min(day_of_month, 28)))
        if frequency == "monthly":
            m += 1
            if m > 12:
                m = 1
                y += 1
        else:
            m += 3
            if m > 12:
                m -= 12
                y += 1
    return dates
