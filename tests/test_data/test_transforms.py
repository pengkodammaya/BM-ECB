"""Tests for data transforms and calendar utilities."""
import numpy as np
import pytest
from nowcasting_toolbox.data.transforms import transform_series
from nowcasting_toolbox.data.calendar import generate_dates, month_of_quarter, date_find, add_months


def test_transform_level():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = transform_series(x, 0)
    assert np.allclose(x, y)


def test_transform_mom():
    x = np.array([100.0, 102.0, 105.0])
    y = transform_series(x, 1)
    assert np.isnan(y[0])
    assert abs(y[1] - np.log(102/100)) < 0.001
    assert abs(y[2] - np.log(105/102)) < 0.001


def test_transform_diff():
    x = np.array([1.0, 3.0, 6.0])
    y = transform_series(x, 2)
    assert np.isnan(y[0])
    assert y[1] == 2.0
    assert y[2] == 3.0


def test_transform_yoy():
    x = np.array([100.0, 102.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0])
    y = transform_series(x, 4, freq="monthly")
    assert np.all(np.isnan(y[:12]))
    assert not np.isnan(y[12])


def test_transform_yoy_quarterly():
    x = np.array([100.0, 102.0, 105.0, 107.0, 110.0])
    y = transform_series(x, 4, freq="quarterly")
    assert np.all(np.isnan(y[:4]))
    assert not np.isnan(y[4])


def test_generate_dates():
    datet = generate_dates(2020, 1, 2020, 6)
    assert len(datet) == 6
    assert datet[0, 0] == 2020 and datet[0, 1] == 1
    assert datet[-1, 0] == 2020 and datet[-1, 1] == 6


def test_month_of_quarter():
    assert month_of_quarter(1) == 1
    assert month_of_quarter(3) == 3
    assert month_of_quarter(4) == 1
    assert month_of_quarter(12) == 3


def test_date_find():
    datet = generate_dates(2020, 1, 2020, 12)
    assert date_find(datet, 2020, 1) == 0
    assert date_find(datet, 2020, 6) == 5
    assert date_find(datet, 2020, 13) == -1


def test_add_months():
    y, m = add_months(2020, 1, 3)
    assert y == 2020 and m == 4
    y, m = add_months(2020, 11, 2)
    assert y == 2021 and m == 1
