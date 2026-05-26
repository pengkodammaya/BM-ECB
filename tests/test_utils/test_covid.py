"""Tests for COVID correction module."""
import numpy as np
import pytest
from nowcasting_toolbox.utils.covid import correct_covid, get_covid_dummies


def test_mode_0_no_change():
    X = np.random.randn(50, 5)
    datet = np.column_stack([np.repeat(2018, 50), np.tile(np.arange(1, 13), 5)[:50]])
    X_corr = correct_covid(X, datet, mode=0)
    assert np.allclose(X, X_corr)


def test_mode_2_nan_block():
    X = np.ones((36, 3))  # 2018-2020, 3 years
    datet = np.column_stack([
        np.repeat([2018, 2019, 2020], 12),
        np.tile(np.arange(1, 13), 3),
    ])
    X_corr = correct_covid(X, datet, mode=2)

    # Rows 0-11=2018, 12-23=2019, 24-35=2020
    # Feb 2020 = row 25, Sep 2020 = row 32
    # NaN block: rows 25 through 32 (8 rows)
    assert np.all(np.isnan(X_corr[25:33]))
    assert not np.any(np.isnan(X_corr[:25]))  # before Feb 2020
    assert not np.any(np.isnan(X_corr[33:]))  # after Sep 2020


def test_mode_3_outlier_replacement():
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (50, 2))
    X[25, 0] = 15.0  # ~15 sigma outlier, should be detected
    datet = np.column_stack([np.repeat(2020, 50), np.tile(np.arange(1, 13), 5)[:50]])
    X_corr = correct_covid(X, datet, mode=3, threshold=5.0)
    assert np.isnan(X_corr[25, 0])
    assert not np.isnan(X_corr[0, 0])


def test_covid_dummies_mode_1():
    datet = np.column_stack([
        np.repeat(2020, 12),
        np.arange(1, 13),
    ])
    dummies = get_covid_dummies(datet, mode=1)
    assert dummies.shape == (4, 2)  # 4 quarter-end months, 2 dummies
    
    # June 2020 = row 1 (months 3, 6, 9, 12)
    assert dummies[1, 0] == 1.0  # June dummy


def test_covid_dummies_mode_4():
    datet = np.column_stack([
        np.repeat(2020, 12),
        np.arange(1, 13),
    ])
    dummies = get_covid_dummies(datet, mode=4)
    assert dummies.shape == (4, 2)
    assert dummies[0, 0] == 1.0  # March dummy
    assert dummies[1, 1] == 1.0  # June dummy


def test_mode_1_returns_unchanged_data():
    X = np.random.randn(10, 3)
    datet = np.column_stack([np.repeat(2020, 10), np.arange(1, 11)])
    X_corr = correct_covid(X, datet, mode=1)
    assert np.allclose(X, X_corr)  # dummies don't modify X
