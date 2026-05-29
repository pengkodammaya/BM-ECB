"""Tests for variable selection."""

import numpy as np
import pandas as pd
import pytest

from nowcasting_toolbox.selection.variable_selection import select_variables


def _make_selection_data(n_samples=20, n_features=8, seed=42):
    """Create synthetic data for variable selection testing."""
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(
        rng.normal(0, 1, (n_samples, n_features)),
        columns=[f"x{i}" for i in range(n_features)],
    )
    y = rng.normal(0, 1, n_samples)
    return X, y


def test_select_variables_correlation():
    """Correlation method should return ranked variables."""
    X, y = _make_selection_data()
    result = select_variables(X, y, method="correlation", n_select=5)

    assert "rank" in result.columns
    assert "variable" in result.columns
    assert "score" in result.columns
    assert len(result) == 5


def test_select_variables_tstat():
    """t-stat method should return ranked variables."""
    X, y = _make_selection_data()
    result = select_variables(X, y, method="tstat", n_select=5)

    assert "rank" in result.columns
    assert "variable" in result.columns
    assert "score" in result.columns
    assert len(result) == 5


def test_select_variables_lars():
    """LARS method should return ranked variables."""
    X, y = _make_selection_data()
    result = select_variables(X, y, method="lars", n_select=5)

    assert "rank" in result.columns
    assert "variable" in result.columns
    assert "score" in result.columns
    assert len(result) == 5


def test_select_variables_rank_order():
    """Results should be sorted by rank."""
    X, y = _make_selection_data()
    result = select_variables(X, y, method="correlation", n_select=5)

    ranks = result["rank"].tolist()
    assert ranks == sorted(ranks)


def test_select_variables_n_select():
    """Should return requested number of variables."""
    X, y = _make_selection_data()
    result = select_variables(X, y, method="correlation", n_select=3)

    assert len(result) == 3


def test_select_variables_invalid_method():
    """Invalid method should raise ValueError."""
    X, y = _make_selection_data()
    with pytest.raises(ValueError):
        select_variables(X, y, method="invalid")


def test_select_variables_scores_finite():
    """Scores should be finite for correlation method."""
    X, y = _make_selection_data()
    result = select_variables(X, y, method="correlation", n_select=5)

    # Correlation scores can be negative
    assert all(np.isfinite(result["score"]))


def test_select_variables_known_relationship():
    """Should detect known linear relationship."""
    rng = np.random.default_rng(42)
    n = 100
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    noise = rng.normal(0, 0.1, n)
    y = 2 * x1 + 0.5 * x2 + noise

    X = pd.DataFrame({
        "x1": x1,
        "x2": x2,
        "noise": rng.normal(0, 1, n),
    })

    result = select_variables(X, y, method="correlation", n_select=3)

    # x1 should be top-ranked
    assert result.iloc[0]["variable"] == "x1"
