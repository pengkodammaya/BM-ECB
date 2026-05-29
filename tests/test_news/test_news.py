"""Tests for news decomposition."""

import numpy as np
import pytest

from nowcasting_toolbox.news.base import compute_news


def _make_news_data(T=20, N=4, seed=42):
    """Create synthetic data for news testing."""
    rng = np.random.default_rng(seed)
    X_old = rng.normal(0, 1, (T, N))
    X_new = X_old.copy()
    # Change a few values in the new vintage
    X_new[-1, 0] += 0.5
    X_new[-1, 1] -= 0.3

    # Mock state-space matrices (simplified)
    A = np.eye(N) * 0.5  # transition
    C = np.eye(N)  # observation
    Q = np.eye(N) * 0.1  # transition noise
    R = np.eye(N) * 0.01  # observation noise

    var_names = [f"x{i}" for i in range(N)]
    group_names = ["group1"] * N

    return X_old, X_new, A, C, Q, R, var_names, group_names


def test_compute_news_returns_dict():
    """compute_news should return a dictionary."""
    X_old, X_new, A, C, Q, R, var_names, group_names = _make_news_data()

    result = compute_news(
        X_old, X_new, A, C, Q, R,
        var_names=var_names,
        group_names=group_names,
        gdp_col=-1,
        target_quarter_end_idx=len(X_old) - 1,
    )

    assert isinstance(result, dict)


def test_compute_news_has_keys():
    """Result should have expected keys."""
    X_old, X_new, A, C, Q, R, var_names, group_names = _make_news_data()

    result = compute_news(
        X_old, X_new, A, C, Q, R,
        var_names=var_names,
        group_names=group_names,
        gdp_col=-1,
        target_quarter_end_idx=len(X_old) - 1,
    )

    assert "old_nowcast_pct" in result
    assert "new_nowcast_pct" in result
    assert "total_change_pp" in result
    assert "news_table" in result


def test_compute_news_total_change():
    """Total change should equal sum of contributions."""
    X_old, X_new, A, C, Q, R, var_names, group_names = _make_news_data()

    result = compute_news(
        X_old, X_new, A, C, Q, R,
        var_names=var_names,
        group_names=group_names,
        gdp_col=-1,
        target_quarter_end_idx=len(X_old) - 1,
    )

    contributions = sum(row["contribution_pp"] for row in result["news_table"])
    assert abs(contributions - result["total_change_pp"]) < 1e-4


def test_compute_news_table_structure():
    """News table rows should have expected fields."""
    X_old, X_new, A, C, Q, R, var_names, group_names = _make_news_data()

    result = compute_news(
        X_old, X_new, A, C, Q, R,
        var_names=var_names,
        group_names=group_names,
        gdp_col=-1,
        target_quarter_end_idx=len(X_old) - 1,
    )

    for row in result["news_table"]:
        assert "series" in row
        assert "group" in row
        assert "contribution_pp" in row
        assert "direction" in row
