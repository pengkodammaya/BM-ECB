"""Tests for data calendar and pipeline utilities."""
import numpy as np
import pytest
import pandas as pd


class TestDataCalendar:
    """Tests for data.calendar module."""

    def test_generate_dates(self):
        """generate_dates returns correct shape."""
        from nowcasting_toolbox.data.calendar import generate_dates

        datet = generate_dates(2020, 1, 2022, 12)
        assert datet.shape[1] == 2
        assert datet[0, 0] == 2020
        assert datet[0, 1] == 1
        assert datet[-1, 0] == 2022
        assert datet[-1, 1] == 12

    def test_generate_dates_single_year(self):
        """generate_dates works for single year."""
        from nowcasting_toolbox.data.calendar import generate_dates

        datet = generate_dates(2024, 1, 2024, 12)
        assert len(datet) == 12

    def test_generate_dates_partial_year(self):
        """generate_dates works for partial year."""
        from nowcasting_toolbox.data.calendar import generate_dates

        datet = generate_dates(2024, 3, 2024, 8)
        assert len(datet) == 6
        assert datet[0, 1] == 3
        assert datet[-1, 1] == 8


class TestPipelineOrchestrator:
    """Tests for pipeline.orchestrator module."""

    def test_pipeline_result_structure(self):
        """PipelineResult has expected fields."""
        from nowcasting_toolbox.pipeline.orchestrator import PipelineResult
        from nowcasting_toolbox.config import ToolboxConfig
        from nowcasting_toolbox.data.loader import LoadedData

        config = ToolboxConfig()
        data = LoadedData(
            xest=np.array([[1.0, 2.0], [3.0, 4.0]]),
            datet=np.array([[2024, 1], [2024, 2]]),
            t_m=np.array([[1], [2]]),
            groups=["group1", "target"],
            nameseries=["x1", "gdp"],
            fullnames=["x1", "gdp"],
            groups_name=["group1", "target"],
            blocks=np.ones((2, 1)),
            nM=1,
            nQ=1,
            startyear=2024,
            startmonth=1,
            transf_m=[1],
            transf_q=[3],
        )

        result = PipelineResult(config=config, data=data)
        assert result.config is config
        assert result.data is data
        assert result.dfm_result is None
        assert result.bvar_result is None
        assert result.beq_result is None


class TestLeaderboard:
    """Tests for pipeline.leaderboard module."""

    def test_build_leaderboard_empty(self):
        """build_leaderboard handles empty input."""
        from nowcasting_toolbox.pipeline.leaderboard import build_leaderboard

        # build_leaderboard expects specific columns, so use a valid empty df
        df = pd.DataFrame(columns=["vintage_date", "actual_gdp", "nowcast_dfm", "nowcast_bvar", "nowcast_beq"])
        result = build_leaderboard(df)
        assert isinstance(result, pd.DataFrame)

    def test_print_leaderboard_empty(self):
        """print_leaderboard handles empty DataFrame."""
        from nowcasting_toolbox.pipeline.leaderboard import print_leaderboard

        df = pd.DataFrame()
        # Should not raise
        print_leaderboard(df)


class TestNewsModule:
    """Tests for news.base module."""

    def test_compute_news_returns_dict(self):
        """compute_news returns expected structure."""
        from nowcasting_toolbox.news.base import compute_news

        T, N = 20, 4
        X_old = np.random.default_rng(42).normal(0, 1, (T, N))
        X_new = X_old.copy()
        X_new[-1, 0] = X_old[-1, 0] + 0.5  # One variable changed

        A = np.eye(N * 2) * 0.5
        C = np.eye(N, N * 2)
        Q = np.eye(N * 2) * 0.1
        R = np.eye(N) * 0.1

        result = compute_news(
            X_old, X_new, A, C, Q, R,
            var_names=["x0", "x1", "x2", "gdp"],
            group_names=["g1", "g1", "g2", "target"],
            gdp_col=-1,
            target_quarter_end_idx=T-1,
        )

        assert isinstance(result, dict)
        assert "old_nowcast_pct" in result
        assert "new_nowcast_pct" in result
        assert "total_change_pp" in result
        assert "news_table" in result
