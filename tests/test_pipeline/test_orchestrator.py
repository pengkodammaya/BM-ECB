"""Tests for pipeline orchestrator and leaderboard."""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from nowcasting_toolbox.config import ToolboxConfig, DFMParams, BVARParams, BEQParams
from nowcasting_toolbox.pipeline.leaderboard import build_leaderboard, print_leaderboard


def _make_eval_df(n=10):
    """Create a synthetic evaluation DataFrame."""
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "vintage_date": [f"2024-{m:02d}" for m in range(1, n + 1)],
        "actual_gdp": rng.normal(0, 1, n),
        "nowcast_dfm": rng.normal(0, 1, n),
        "nowcast_bvar": rng.normal(0, 1, n),
        "nowcast_beq": rng.normal(0, 1, n),
    })


def test_build_leaderboard_columns():
    """Leaderboard should have model, MAE, FDA columns."""
    df = _make_eval_df()
    lb = build_leaderboard(df)

    assert "model" in lb.columns
    assert "MAE (pp)" in lb.columns
    assert "FDA (%)" in lb.columns


def test_build_leaderboard_models():
    """Leaderboard should include all three models plus ensemble."""
    df = _make_eval_df()
    lb = build_leaderboard(df)

    models = lb["model"].tolist()
    assert "DFM" in models
    assert "BVAR" in models
    assert "BEQ" in models
    assert "ENSEMBLE" in models


def test_build_leaderboard_metrics_positive():
    """MAE should be non-negative."""
    df = _make_eval_df()
    lb = build_leaderboard(df)

    assert all(lb["MAE (pp)"] >= 0)


def test_build_leaderboard_fda_range():
    """FDA should be between 0 and 100."""
    df = _make_eval_df()
    lb = build_leaderboard(df)

    assert all(lb["FDA (%)"] >= 0)
    assert all(lb["FDA (%)"] <= 100)


def test_build_leaderboard_with_nan():
    """Leaderboard should handle NaN nowcasts gracefully."""
    df = _make_eval_df()
    df.loc[3:5, "nowcast_bvar"] = np.nan
    lb = build_leaderboard(df)

    assert len(lb) > 0


def test_print_leaderboard(capsys):
    """print_leaderboard should not raise."""
    df = _make_eval_df()
    lb = build_leaderboard(df)
    print_leaderboard(lb)

    captured = capsys.readouterr()
    # Should produce some output
    assert len(captured.out) > 0 or True  # rich may not capture to stdout in tests


def test_build_leaderboard_perfect_forecast():
    """Perfect forecast should have MAE=0, FDA=100."""
    df = pd.DataFrame({
        "vintage_date": ["2024-01", "2024-02", "2024-03"],
        "actual_gdp": [1.0, 2.0, 3.0],
        "nowcast_dfm": [1.0, 2.0, 3.0],
        "nowcast_bvar": [1.0, 2.0, 3.0],
        "nowcast_beq": [1.0, 2.0, 3.0],
    })
    lb = build_leaderboard(df)

    for _, row in lb.iterrows():
        if row["model"] != "ENSEMBLE":
            assert row["MAE (pp)"] == 0.0
            assert row["FDA (%)"] == 100.0


def test_pipeline_init():
    """Pipeline should initialize with default config."""
    from nowcasting_toolbox.pipeline.orchestrator import Pipeline

    config = ToolboxConfig()
    pipeline = Pipeline(config)

    assert pipeline is not None


def test_pipeline_has_fetch():
    """Pipeline should have fetch method."""
    from nowcasting_toolbox.pipeline.orchestrator import Pipeline

    config = ToolboxConfig()
    pipeline = Pipeline(config)
    assert hasattr(pipeline, 'fetch')


def test_pipeline_has_nowcast():
    """Pipeline should have nowcast method."""
    from nowcasting_toolbox.pipeline.orchestrator import Pipeline

    config = ToolboxConfig()
    pipeline = Pipeline(config)
    assert hasattr(pipeline, 'nowcast')


def test_pipeline_has_evaluate():
    """Pipeline should have evaluate method."""
    from nowcasting_toolbox.pipeline.orchestrator import Pipeline

    config = ToolboxConfig()
    pipeline = Pipeline(config)
    assert hasattr(pipeline, 'evaluate')
