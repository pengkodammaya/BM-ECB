"""Tests for backtest engine."""

import numpy as np
import pandas as pd
import pytest
from datetime import date

from nowcasting_toolbox.config import ToolboxConfig


def _make_backtest_data(T=36, N=4, seed=42):
    """Create synthetic data for backtesting."""
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, (T, N))
    # Make last column (GDP) quarterly
    X[:, -1] = np.nan
    for t in range(2, T, 3):
        X[t, -1] = rng.normal(0, 1)

    datet = np.array([[2020 + (t + 1) // 12, (t % 12) + 1] for t in range(T)], dtype=float)
    return X, datet


def test_find_idx():
    """_find_idx should find correct index."""
    from nowcasting_toolbox.eval.backtest import _find_idx

    datet = np.array([[2020, m] for m in range(1, 13)], dtype=float)

    idx = _find_idx(datet, 2020, 3)
    assert idx == 2

    idx = _find_idx(datet, 2020, 12)
    assert idx == 11


def test_find_idx_not_found():
    """_find_idx should return last index for missing date."""
    from nowcasting_toolbox.eval.backtest import _find_idx

    datet = np.array([[2020, m] for m in range(1, 13)], dtype=float)

    idx = _find_idx(datet, 2025, 1)
    assert idx == 11  # returns last index


def test_build_vintage_builder():
    """_build_vintage_builder should return None when ARC unavailable."""
    from nowcasting_toolbox.eval.backtest import _build_vintage_builder

    # This may return None if ARC data is not cached
    builder = _build_vintage_builder()
    # We just check it doesn't crash
    assert builder is None or hasattr(builder, 'build')


def test_apply_ragged_edge_truncates():
    """_apply_ragged_edge should truncate data at time t."""
    from nowcasting_toolbox.eval.backtest import _apply_ragged_edge
    from datetime import date

    X, datet = _make_backtest_data(T=24, N=3)
    t = 10
    vintage_date = date(2020, 11, 15)

    X_vint = _apply_ragged_edge(X, datet, t, None, ["x1", "x2", "gdp"], vintage_date)

    assert X_vint.shape[0] == t + 1
    assert X_vint.shape[1] == X.shape[1]


def test_apply_ragged_edge_with_builder():
    """_apply_ragged_edge should handle vintage builder gracefully."""
    from nowcasting_toolbox.eval.backtest import _apply_ragged_edge
    from unittest.mock import MagicMock

    X, datet = _make_backtest_data(T=24, N=3)
    t = 10
    vintage_date = date(2020, 11, 15)

    # Mock vintage builder (isinstance check will fail, so it falls through to raw data)
    mock_builder = MagicMock()

    X_vint = _apply_ragged_edge(X, datet, t, mock_builder, ["x1", "x2", "gdp"], vintage_date)

    assert X_vint.shape[0] == t + 1


def test_run_backtest_basic():
    """run_backtest should return DataFrame with expected columns."""
    from nowcasting_toolbox.eval.backtest import run_backtest

    X, datet = _make_backtest_data(T=36, N=4)
    config = ToolboxConfig()
    config.eval.eval_startyear = 2021
    config.eval.eval_startmonth = 1
    config.eval.eval_endyear = 2021
    config.eval.eval_endmonth = 6

    df = run_backtest(config, X, datet)

    assert isinstance(df, pd.DataFrame)
    assert "vintage_date" in df.columns
    assert "actual_gdp" in df.columns
    assert len(df) > 0


def test_run_backtest_has_nowcast_columns():
    """run_backtest output should have nowcast columns."""
    from nowcasting_toolbox.eval.backtest import run_backtest

    X, datet = _make_backtest_data(T=36, N=4)
    config = ToolboxConfig()
    config.eval.eval_startyear = 2021
    config.eval.eval_startmonth = 1
    config.eval.eval_endyear = 2021
    config.eval.eval_endmonth = 3

    df = run_backtest(config, X, datet)

    assert "nowcast_dfm" in df.columns or "nowcast_bvar" in df.columns


def test_default_dataset_ids():
    """DEFAULT_DATASET_IDS should have expected entries."""
    from nowcasting_toolbox.eval.backtest import DEFAULT_DATASET_IDS

    assert "ipi" in DEFAULT_DATASET_IDS
    assert "gdp" in DEFAULT_DATASET_IDS
    assert len(DEFAULT_DATASET_IDS) >= 10
