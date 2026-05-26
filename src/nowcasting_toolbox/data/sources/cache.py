"""Local cache layer for API-fetched data.

Uses Parquet files with TTL-based expiry. Provides:

- ``put(dataset_id, df)`` -> write to cache
- ``get(dataset_id)`` -> read if fresh, return None if stale
- ``is_fresh(dataset_id)`` -> check TTL
- ``invalidate(dataset_id)`` -> force delete
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data/malaysia")
DEFAULT_TTL_HOURS = 6


class DataCache:
    """Parquet-based cache with TTL.

    Parameters
    ----------
    cache_dir : Path
        Directory for stored Parquet files.
    ttl_hours : int
        Time-to-live in hours. 0 = cache forever.
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        ttl_hours: int = DEFAULT_TTL_HOURS,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl = timedelta(hours=ttl_hours) if ttl_hours > 0 else None
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, dataset_id: str) -> Optional[pd.DataFrame]:
        """Return cached DataFrame if fresh, else None."""
        path = self._path(dataset_id)
        if not path.exists():
            return None
        if self.ttl is not None:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            age = datetime.now(timezone.utc) - mtime
            if age > self.ttl:
                logger.debug("Cache expired for %s (age=%s)", dataset_id, age)
                return None
        try:
            df = pd.read_parquet(path)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
            logger.debug("Cache HIT for %s (%d rows)", dataset_id, len(df))
            return df
        except Exception as exc:
            logger.warning("Failed to read cache for %s: %s", dataset_id, exc)
            return None

    def put(self, dataset_id: str, df: pd.DataFrame) -> None:
        """Write DataFrame to cache."""
        if df is None or df.empty:
            return
        path = self._path(dataset_id)
        df.to_parquet(path, index=False)
        logger.debug("Cached %s -> %s (%d rows)", dataset_id, path, len(df))

    def is_fresh(self, dataset_id: str) -> bool:
        """Check whether a cached dataset is still within TTL."""
        return self.get(dataset_id) is not None

    def invalidate(self, dataset_id: str) -> None:
        """Delete cached file for a dataset."""
        path = self._path(dataset_id)
        if path.exists():
            path.unlink()
            logger.debug("Invalidated cache for %s", dataset_id)

    def invalidate_all(self) -> None:
        """Delete all cached files."""
        for path in self.cache_dir.glob("*.parquet"):
            path.unlink()
        logger.debug("Invalidated all caches")

    def list_cached(self) -> list[str]:
        """Return list of cached dataset IDs."""
        return [p.stem for p in self.cache_dir.glob("*.parquet")]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _path(self, dataset_id: str) -> Path:
        safe = dataset_id.replace("/", "_").replace("\\", "_")
        return self.cache_dir / f"{safe}.parquet"
