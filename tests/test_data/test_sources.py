"""Tests for data source clients with mocked HTTP responses."""
import json
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock


class TestOpenDOSMClient:
    """Tests for OpenDOSMClient with mocked HTTP responses."""

    def test_fetch_returns_dataframe(self):
        """fetch() returns a DataFrame with expected columns."""
        from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"date": "2024-01-01", "value": 100.0},
            {"date": "2024-02-01", "value": 101.0},
        ]
        mock_response.raise_for_status = MagicMock()

        client = OpenDOSMClient()
        with patch.object(client._client, 'get', return_value=mock_response):
            df = client.fetch("test_dataset")

        assert isinstance(df, pd.DataFrame)
        assert "date" in df.columns
        assert "value" in df.columns
        assert len(df) == 2

    def test_fetch_empty_response(self):
        """fetch() returns empty DataFrame for empty response."""
        from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        client = OpenDOSMClient()
        with patch.object(client._client, 'get', return_value=mock_response):
            df = client.fetch("test_dataset")

        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_fetch_with_value_wrapper(self):
        """fetch() handles {'value': [...]} response format."""
        from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {"date": "2024-01-01", "index": 100.0},
                {"date": "2024-02-01", "index": 101.0},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        client = OpenDOSMClient()
        with patch.object(client._client, 'get', return_value=mock_response):
            df = client.fetch("ipi")

        assert isinstance(df, pd.DataFrame)
        assert "date" in df.columns
        assert "index" in df.columns

    def test_fetch_retry_config(self):
        """fetch() has configurable timeout."""
        from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient

        # Test that client accepts timeout parameter
        client = OpenDOSMClient(timeout=60.0)
        assert client._client is not None
        client.close()


class TestCache:
    """Tests for DataCache with mocked file operations."""

    def test_cache_put_get(self):
        """Cache stores and retrieves DataFrames."""
        from nowcasting_toolbox.data.sources.cache import DataCache

        cache = DataCache(ttl_hours=1)
        df = pd.DataFrame({"date": ["2024-01-01"], "value": [100.0]})
        cache.put("test", df)

        result = cache.get("test")
        assert result is not None
        assert len(result) == 1

    def test_cache_miss(self):
        """Cache returns None for missing keys."""
        from nowcasting_toolbox.data.sources.cache import DataCache

        cache = DataCache(ttl_hours=1)
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_expiry(self):
        """Cache returns None for expired entries."""
        from nowcasting_toolbox.data.sources.cache import DataCache
        import time

        # Use a very short TTL (in hours, but we'll manipulate the timestamp)
        cache = DataCache(ttl_hours=0.0001)  # ~0.36 seconds
        df = pd.DataFrame({"date": ["2024-01-01"], "value": [100.0]})
        cache.put("test", df)

        # Wait for expiry
        time.sleep(0.5)

        result = cache.get("test")
        assert result is None


class TestARCVintageBuilder:
    """Tests for ARCVintageBuilder."""

    def test_build_returns_correct_shape(self):
        """build() returns array with same shape as input."""
        from nowcasting_toolbox.eval.vintage import ARCVintageBuilder
        from datetime import date

        T, N = 24, 4
        X = np.random.default_rng(42).normal(0, 1, (T, N))
        datet = np.array([[2022, m] for m in range(1, 13)] + [[2023, m] for m in range(1, 13)])

        schedule = [
            {"release_date": date(2022, 2, 10), "dataset_id": "ipi", "ref_year": 2022, "ref_month": 1},
            {"release_date": date(2022, 3, 10), "dataset_id": "ipi", "ref_year": 2022, "ref_month": 2},
        ]

        vb = ARCVintageBuilder(schedule=schedule)
        result = vb.build(X.copy(), datet, date(2022, 6, 15), var_names=["v0", "v1", "v2", "v3"])

        assert result.shape == (T, N)

    def test_build_masks_future_data(self):
        """build() applies fallback lags when no schedule match."""
        from nowcasting_toolbox.eval.vintage import ARCVintageBuilder
        from datetime import date

        T, N = 12, 2
        X = np.ones((T, N))
        datet = np.array([[2022, m] for m in range(1, 13)])

        # No schedule - uses fallback lags (30 days default)
        vb = ARCVintageBuilder(schedule=[])
        result = vb.build(X.copy(), datet, date(2022, 1, 15),
                         var_names=["v0", "v1"])

        # With vintage date Jan 15, January data should be masked
        # (released ~30 days after month end = ~Feb 1)
        assert np.isnan(result[0, 0])  # Jan masked
        # But previous months should be visible
        # (None exist in this test, so all NaN is fine)
        assert result.shape == (T, N)

    def test_build_empty_schedule(self):
        """build() with empty schedule returns data unchanged."""
        from nowcasting_toolbox.eval.vintage import ARCVintageBuilder
        from datetime import date

        T, N = 12, 2
        X = np.ones((T, N))
        datet = np.array([[2022, m] for m in range(1, 13)])

        vb = ARCVintageBuilder(schedule=[])
        result = vb.build(X.copy(), datet, date(2022, 6, 15), var_names=["v0", "v1"])

        # Without schedule, data should still be returned (no masking)
        assert result.shape == (T, N)


class TestTransforms:
    """Tests for data transformations."""

    def test_transform_level(self):
        """Level transform returns input unchanged."""
        from nowcasting_toolbox.data.transforms import transform_series

        x = np.array([1.0, 2.0, 3.0])
        result = transform_series(x, 0, "monthly")
        np.testing.assert_array_equal(result, x)

    def test_transform_mom(self):
        """MoM transform computes dlog differences."""
        from nowcasting_toolbox.data.transforms import transform_series

        x = np.array([100.0, 101.0, 102.0])
        result = transform_series(x, 1, "monthly")

        # First value should be NaN (needs lag)
        assert np.isnan(result[0])
        # Subsequent values should be dlog differences
        assert not np.isnan(result[1])

    def test_transform_yoy_quarterly(self):
        """YoY transform uses lag=4 for quarterly data."""
        from nowcasting_toolbox.data.transforms import transform_series

        x = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        result = transform_series(x, 4, "quarterly")

        # First 4 values should be NaN (lag=4)
        assert all(np.isnan(result[:4]))
        # Subsequent values should be finite
        assert not np.isnan(result[4])


class TestVariableSelection:
    """Tests for variable selection methods."""

    def test_correlation_ranking(self):
        """Correlation ranking returns correct shape."""
        from nowcasting_toolbox.selection.variable_selection import select_variables

        rng = np.random.default_rng(42)
        X = rng.normal(0, 1, (50, 5))
        y = X[:, 0] * 2 + rng.normal(0, 0.1, 50)

        result = select_variables(X, y, method="correlation", n_select=3)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert "variable" in result.columns
        assert "score" in result.columns

    def test_tstat_ranking(self):
        """t-stat ranking returns correct shape."""
        from nowcasting_toolbox.selection.variable_selection import select_variables

        rng = np.random.default_rng(42)
        X = rng.normal(0, 1, (50, 5))
        y = X[:, 0] * 2 + rng.normal(0, 0.1, 50)

        result = select_variables(X, y, method="tstat", n_select=3)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3

    def test_lars_ranking(self):
        """LARS ranking returns correct shape."""
        from nowcasting_toolbox.selection.variable_selection import select_variables

        rng = np.random.default_rng(42)
        X = rng.normal(0, 1, (50, 5))
        y = X[:, 0] * 2 + rng.normal(0, 0.1, 50)

        result = select_variables(X, y, method="lars", n_select=3)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
