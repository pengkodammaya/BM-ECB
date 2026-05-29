"""Tests for data loader."""

import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from nowcasting_toolbox.config import ToolboxConfig


def test_loaded_data_structure():
    """LoadedData should have required fields."""
    from nowcasting_toolbox.data.loader import LoadedData

    data = LoadedData(
        xest=np.zeros((10, 5)),
        datet=np.zeros((10, 2)),
        t_m=np.arange(10).reshape(-1, 1),
        groups=["a"] * 5,
        nameseries=["x1", "x2", "x3", "x4", "x5"],
        fullnames=["X1", "X2", "X3", "X4", "X5"],
        groups_name=["a"],
        blocks=np.ones((5, 1)),
        nM=4,
        nQ=1,
        startyear=2020,
        startmonth=1,
    )

    assert data.xest.shape == (10, 5)
    assert data.nM == 4
    assert data.nQ == 1


def test_load_data_excel_no_file():
    """load_data with excel source should require file_path."""
    from nowcasting_toolbox.data.loader import load_data

    config = ToolboxConfig()
    with pytest.raises(ValueError, match="file_path required"):
        load_data(config, source="excel")


def test_load_data_csv_no_file():
    """load_data with csv source should require file_path."""
    from nowcasting_toolbox.data.loader import load_data

    config = ToolboxConfig()
    with pytest.raises(ValueError, match="file_path required"):
        load_data(config, source="csv")


def test_load_data_parquet_no_file():
    """load_data with parquet source should require file_path."""
    from nowcasting_toolbox.data.loader import load_data

    config = ToolboxConfig()
    with pytest.raises(ValueError, match="file_path required"):
        load_data(config, source="parquet")


def test_load_data_unknown_source():
    """load_data with unknown source should raise ValueError."""
    from nowcasting_toolbox.data.loader import load_data

    config = ToolboxConfig()
    with pytest.raises(ValueError, match="Unknown source"):
        load_data(config, source="unknown")


def test_build_date_grid():
    """_build_date_grid should produce a valid date grid."""
    from nowcasting_toolbox.data.loader import _build_date_grid

    config = ToolboxConfig(startyear=2020, startmonth=1)
    df = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=24, freq="MS"),
        "value": range(24),
    })

    grid = _build_date_grid(config, [df])

    assert grid.shape[1] == 2
    assert len(grid) > 0
    assert grid[0, 0] == 2020
    assert grid[0, 1] == 1


def test_align_to_grid():
    """_align_to_grid should align data to grid."""
    from nowcasting_toolbox.data.loader import _align_to_grid

    df = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=12, freq="MS"),
        "value": range(12),
    })
    grid = np.array([[2020, m] for m in range(1, 13)])

    result = _align_to_grid(df, grid, "monthly", col="value")

    assert len(result) == 12
    assert result[0] == 0
    assert result[11] == 11


def test_find_date_index():
    """_find_date_index should find correct index."""
    from nowcasting_toolbox.data.loader import _find_date_index

    grid = np.array([[2020, m] for m in range(1, 13)], dtype=float)

    idx = _find_date_index(grid, 2020, 3)
    assert idx == 2

    idx = _find_date_index(grid, 2020, 1)
    assert idx == 0


def test_find_date_index_not_found():
    """_find_date_index should return 0 for missing date."""
    from nowcasting_toolbox.data.loader import _find_date_index

    grid = np.array([[2020, m] for m in range(1, 13)], dtype=float)

    idx = _find_date_index(grid, 2025, 1)
    assert idx == 0


def test_build_blocks():
    """_build_blocks should build one-hot matrix."""
    from nowcasting_toolbox.data.loader import _build_blocks

    groups = ["a", "a", "b", "c"]
    groups_name = ["a", "b", "c"]

    blocks = _build_blocks(groups, groups_name)

    assert blocks.shape == (4, 3)
    assert blocks[0, 0] == 1.0  # group a
    assert blocks[1, 0] == 1.0  # group a
    assert blocks[2, 1] == 1.0  # group b
    assert blocks[3, 2] == 1.0  # group c


def test_load_csv_file(tmp_path):
    """load_data should load CSV files."""
    from nowcasting_toolbox.data.loader import load_data

    # Create test CSV
    df = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=24, freq="MS"),
        "x1": np.random.randn(24),
        "x2": np.random.randn(24),
        "x3": np.random.randn(24),
        "gdp": np.random.randn(24),
    })
    csv_path = tmp_path / "test_data.csv"
    df.to_csv(csv_path, index=False)

    config = ToolboxConfig(startyear=2020, startmonth=1)
    data = load_data(config, source="csv", file_path=csv_path)

    assert data.xest.shape[0] > 0
    assert data.xest.shape[1] == 4
