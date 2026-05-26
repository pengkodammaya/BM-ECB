"""Live ARC parser: fetches and parses the DOSM Advance Release Calendar (ICS format).

The DOSM ARC download endpoint returns an iCalendar (.ics) file with VEVENT
blocks specifying exact release dates for each statistical publication.

This module:
1. Fetches the ICS for a given year
2. Parses it into (release_date, title, reference_period) tuples
3. Maps release titles to dataset IDs via fuzzy matching
4. Builds per-series publication lags
"""

from __future__ import annotations

import logging
import re
import warnings
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Suppress insecure HTTPS warnings for DOSM government site
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

ARC_DOWNLOAD_URL = "https://www.dosm.gov.my/site/downloadarc"

# ---------------------------------------------------------------------------
# Title → dataset ID mapping (fuzzy substring match)
# ---------------------------------------------------------------------------

# Each entry is (substring_lower, dataset_id)
# Order matters: more specific matches first
SERIES_MATCH_PATTERNS: list[tuple[str, str]] = [
    ("index of industrial production", "ipi"),
    ("monthly manufacturing statistics", "ipi"),  # same dataset
    ("consumer price index", "cpi_headline"),
    ("producer price index", "ppi"),
    ("labour force statistics", "u_rate"),
    ("labour force survey report", "u_rate"),
    ("employment statistics", "u_rate"),
    ("monthly external trade statistics", "external_trade"),
    ("malaysia external trade indices", "external_trade"),
    ("export import statistics", "external_trade"),
    ("performance of wholesale", "wrt"),
    ("volume index of wholesale", "wrt"),
    ("quarterly services statistics", "services"),
    ("volume index of services", "services"),
    ("construction statistics", "construction"),
    ("monthly rubber statistics", "rubber"),
    ("gross domestic product first quarter", "gdp"),
    ("gross domestic product second quarter", "gdp"),
    ("gross domestic product third quarter", "gdp"),
    ("gross domestic product fourth quarter", "gdp"),
    ("gross domestic product 20", "gdp"),  # annual GDP
    ("advance gross domestic product", "gdp_advance"),
    ("leading, coincident & lagging", "leading"),
    ("malaysian economic indicators", "leading"),
    ("business tendency statistics", "business_tendency"),
    ("labour productivity", "productivity"),
    ("quarterly balance of payments", "bop"),
    ("international investment position", "iip"),
    ("services producer price index", "services_ppi"),
    ("manufacturing industry capacity", "capacity_utilisation"),
]


def match_dataset_id(title: str) -> Optional[str]:
    """Match a release title to a dataset ID."""
    title_lower = title.lower()
    for pattern, did in SERIES_MATCH_PATTERNS:
        if pattern in title_lower:
            return did
    return None


# ---------------------------------------------------------------------------
# Reference period extraction from title
# ---------------------------------------------------------------------------

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
QUARTER_MAP = {
    "first quarter": (1, 3), "second quarter": (4, 6),
    "third quarter": (7, 9), "fourth quarter": (10, 12),
    "q1": (1, 3), "q2": (4, 6), "q3": (7, 9), "q4": (10, 12),
}


def extract_reference_period(title: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Extract (year, month_start, month_end) from a release title.

    Returns (None, None, None) if period cannot be determined.
    Examples:
        "Index of Industrial Production, March 2026" → (2026, 3, 3)
        "Gross Domestic Product First Quarter 2026" → (2026, 1, 3)
        "Consumer Price Index, April 2026" → (2026, 4, 4)
    """
    title_lower = title.lower()

    # Try quarterly periods first
    for qname, (sm, em) in QUARTER_MAP.items():
        if qname in title_lower:
            # Find year after the quarter name
            rest = title_lower.split(qname)[-1].strip()
            year_match = re.search(r"(20\d{2})", rest)
            if year_match:
                return int(year_match.group(1)), sm, em

    # Try "Month Year" pattern
    for mname, mnum in MONTH_MAP.items():
        # Pattern: "Month Year" or "Month, Year"
        pattern = rf"{mname}[,\s]+(20\d{{2}})"
        match = re.search(pattern, title_lower)
        if match:
            year = int(match.group(1))
            return year, mnum, mnum

    # Try standalone year
    year_match = re.search(r"(20\d{2})", title_lower)
    if year_match:
        year = int(year_match.group(1))
        # Check for quarter
        for qname, (sm, em) in QUARTER_MAP.items():
            if qname in title_lower:
                return year, sm, em
        return year, None, None

    return None, None, None


# ---------------------------------------------------------------------------
# ICS parser and release schedule builder
# ---------------------------------------------------------------------------


def fetch_arc(year: int, cache_dir: Optional[Path] = None) -> list[dict]:
    """Fetch and parse the ARC for a given year.

    Parameters
    ----------
    year : int
        Calendar year (e.g., 2026).
    cache_dir : Path, optional
        Directory to cache ICS files. If provided, avoids re-fetching.

    Returns
    -------
    list[dict]
        Each dict has keys: release_date, title, dataset_id, ref_year, ref_month
    """
    # Try local cache first
    if cache_dir:
        cache_path = cache_dir / f"arc_{year}.ics"
        if cache_path.exists():
            ics_text = cache_path.read_text(encoding="utf-8")
        else:
            ics_text = _download_ics(year)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(ics_text, encoding="utf-8")
    else:
        ics_text = _download_ics(year)

    return _parse_ics(ics_text)


def _download_ics(year: int) -> str:
    """Download ARC ICS file for a given year."""
    resp = httpx.get(
        ARC_DOWNLOAD_URL,
        params={"search_year": str(year), "search_month": "All", "action": "download"},
        timeout=30,
        verify=False,  # DOSM certificate chain issues on some systems
    )
    resp.raise_for_status()
    return resp.text


def _parse_ics(ics_text: str) -> list[dict]:
    """Parse an ICS calendar string into release events."""
    events = []

    for block in re.split(r"END:VEVENT", ics_text):
        if "BEGIN:VEVENT" not in block:
            continue

        dt_match = re.search(r"DTSTART:(\d{8})T", block)
        summary_match = re.search(r"SUMMARY:(.+)", block)

        if not dt_match or not summary_match:
            continue

        dt_str = dt_match.group(1)
        title = summary_match.group(1).strip()

        # Parse date
        y, m, d = int(dt_str[:4]), int(dt_str[4:6]), int(dt_str[6:8])
        release_date = date(y, m, d)

        # Match to dataset
        dataset_id = match_dataset_id(title)

        # Extract reference period
        ref_year, ref_m_start, ref_m_end = extract_reference_period(title)

        events.append({
            "release_date": release_date,
            "title": title,
            "dataset_id": dataset_id,
            "ref_year": ref_year,
            "ref_month_start": ref_m_start,
            "ref_month_end": ref_m_end,
        })

    return events


# ---------------------------------------------------------------------------
# Build publication lag table
# ---------------------------------------------------------------------------


def build_publication_schedule(
    years: list[int] | None = None,
    cache_dir: Optional[Path] = None,
) -> list[dict]:
    """Build a full publication schedule across multiple years.

    Only includes events that could be matched to a known dataset ID
    and have a valid reference period.

    Parameters
    ----------
    years : list[int]
        Years to fetch. Default: 2020–current year.
    cache_dir : Path, optional

    Returns
    -------
    list[dict] sorted by release_date
    """
    if years is None:
        current_year = datetime.now().year
        years = list(range(2020, current_year + 1))

    all_events = []
    for year in years:
        try:
            events = fetch_arc(year, cache_dir=cache_dir)
            all_events.extend(events)
        except Exception as exc:
            logger.warning("Failed to fetch ARC for year %s: %s", year, exc)

    # Filter: only events with dataset_id and reference period
    valid = [
        e for e in all_events
        if e["dataset_id"] is not None
        and e["ref_year"] is not None
        and e["ref_month_start"] is not None
    ]

    valid.sort(key=lambda e: e["release_date"])
    return valid
