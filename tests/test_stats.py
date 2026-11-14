"""Tests for app/services/stats.py.

Hand-made series only, small enough to check by hand. No database, no fixtures
from real data. Contract keys are English; only the warnings are Portuguese.
"""
from datetime import date

import pytest

from app.services.stats import (
    NO_FIRE_WARNING,
    SMALL_AREA_WARNING,
    build_grid,
    build_stats,
    build_warnings,
    filter_period,
    indicators,
    last_month,
    monthly_medians,
    percentile,
    ratio,
    values_per_month,
)

# --------------------------------------------------------------- series A
# 2020-2023, cutoff at the end of the series.
#   month 8: 10, 0, 5, 0  -> [0, 0, 5, 10]     -> median 2.5 (even number of years)
#   month 9: 20, 30, 40, 10 -> [10, 20, 30, 40] -> median 25.0
#   every other month: all zeros                -> median 0.0
SERIES_A = [(2020, 8, 10.0), (2020, 9, 20.0), (2021, 9, 30.0),
            (2022, 8, 5.0), (2022, 9, 40.0), (2023, 9, 10.0)]
A_START, A_END = 2020, 2023
A_CUTOFF = date(2023, 12, 31)

# --------------------------------------------------------------- series B
# Cutoff in the middle of the last year (the 2026 scenario of section 9):
# 2023 only has months 1-6, so month 9 has three observed years, not four.
SERIES_B = [(2020, 3, 4.0), (2021, 3, 8.0), (2022, 3, 12.0), (2023, 3, 2.0),
            (2020, 9, 30.0), (2021, 9, 10.0), (2022, 9, 20.0)]
B_START, B_END = 2020, 2023
B_CUTOFF = date(2023, 6, 30)


def grid_a(cutoff=A_CUTOFF):
    return build_grid(SERIES_A, series_start_year=A_START,
                      series_end_year=A_END, cutoff_date=cutoff)


def grid_b():
    return build_grid(SERIES_B, series_start_year=B_START,
                      series_end_year=B_END, cutoff_date=B_CUTOFF)


def stats_a(start, end, **kwargs):
    kwargs.setdefault("cutoff_date", A_CUTOFF)
    kwargs.setdefault("area_km2", 1200.0)
    return build_stats(SERIES_A, start_date=start, end_date=end,
                       series_start_year=A_START, series_end_year=A_END, **kwargs)


# --------------------------------------------------------------- the grid
def test_grid_fills_zeros():
    grid = grid_a()
    assert len(grid) == 48                             # 4 years x 12 months
    assert grid["value"].loc[(2021, 8)] == 0.0
    assert grid["value"].loc[(2020, 8)] == 10.0
    assert grid["value"].sum() == 115.0


def test_grid_stops_at_the_cutoff_month():
    grid = grid_b()
    assert len(grid) == 42                             # 3 x 12 + 6
    assert (2023, 6) in grid.index
    assert (2023, 7) not in grid.index


# --------------------------------------------------------------- medians
def test_median_with_an_even_number_of_years():
    assert monthly_medians(grid_a())[8] == 2.5         # [0, 0, 5, 10]


def test_median_with_an_odd_number_of_years():
    grid = build_grid([(2020, 9, 20.0), (2021, 9, 30.0), (2022, 9, 40.0)],
                      series_start_year=2020, series_end_year=2022,
                      cutoff_date=date(2022, 12, 31))
    assert monthly_medians(grid)[9] == 30.0


def test_median_counts_zeros_so_the_ratio_is_null():
    # one single month with fire in three years: [0, 0, 10] -> median 0
    rows = [(2022, 9, 10.0)]
    grid = build_grid(rows, series_start_year=2020, series_end_year=2022,
                      cutoff_date=date(2022, 12, 31))
    medians, by_month = monthly_medians(grid), values_per_month(grid)

    assert medians[9] == 0.0
    assert ratio(10.0, medians[9]) is None
    assert ratio(0.0, medians[9]) is None
    assert percentile(0.0, by_month[9]) == 67          # 2 of 3 years
    assert percentile(10.0, by_month[9]) == 100


def test_months_after_the_cutoff_are_not_counted_as_zero():
    # september 2023 is not observed, so month 9 stays [10, 20, 30] -> 20.0,
    # not [0, 10, 20, 30] -> 15.0
    assert monthly_medians(grid_b())[9] == 20.0
    assert monthly_medians(grid_b())[3] == 6.0         # [2, 4, 8, 12], all four years


# --------------------------------------------------------------- percentile
def test_percentile_is_inclusive_and_peaks_at_100():
    by_month = values_per_month(grid_a())[9]           # [20, 30, 40, 10]
    assert percentile(20.0, by_month) == 50
    assert percentile(30.0, by_month) == 75
    assert percentile(40.0, by_month) == 100           # the series maximum
    assert percentile(10.0, by_month) == 25


def test_percentile_ties_share_the_same_value():
    by_month = values_per_month(grid_a())[8]           # [10, 0, 5, 0]
    assert percentile(10.0, by_month) == 100
    assert percentile(5.0, by_month) == 75
    assert percentile(0.0, by_month) == 50             # 2020 and 2023 both tie at 0


def test_percentile_denominator_is_per_month():
    by_month = values_per_month(grid_b())[9]           # only three observed years
    assert len(by_month) == 3
    assert percentile(30.0, by_month) == 100
    assert percentile(10.0, by_month) == 33
    assert percentile(20.0, by_month) == 67


def test_ratio_rounds_to_two_decimals():
    medians = monthly_medians(grid_a())
    assert ratio(20.0, medians[9]) == 0.8
    assert ratio(30.0, medians[9]) == 1.2
    assert ratio(40.0, medians[9]) == 1.6
    assert ratio(10.0, medians[9]) == 0.4
    assert ratio(10.0, medians[8]) == 4.0
    assert ratio(0.0, medians[8]) == 0.0
    assert ratio(2.0, monthly_medians(grid_b())[3]) == 0.33


# --------------------------------------------------------------- the period
def test_period_takes_whole_months_that_intersect():
    period = filter_period(grid_a(), date(2021, 6, 15), date(2022, 10, 5))
    assert len(period) == 17                           # 2021-06..12 plus 2022-01..10
    assert period.index[0] == (2021, 6)
    assert period.index[-1] == (2022, 10)


def test_filtering_does_not_change_the_medians():
    grid = grid_a()
    period = filter_period(grid, date(2021, 6, 15), date(2022, 10, 5))
    assert len(period) == 17
    # only two of the four september values are inside the period
    assert monthly_medians(grid)[9] == 25.0
    assert len(values_per_month(grid)[9]) == 4


def test_period_cannot_invent_months_past_the_cutoff():
    result = build_stats(SERIES_B, start_date=date(2023, 1, 1), end_date=date(2023, 12, 31),
                         series_start_year=B_START, series_end_year=B_END,
                         cutoff_date=B_CUTOFF, area_km2=1200.0)
    assert len(result["calendar"]) == 6                # january to june only
    assert result["indicators"]["total"] == 2.0
    assert result["indicators"]["annual_mean"] == 2.0
    assert result["indicators"]["worst_year"] == {"year": 2023, "value": 2.0}
    assert result["indicators"]["peak_month"] == {"year": 2023, "month": 3, "value": 2.0}


# --------------------------------------------------------------- indicators
def test_indicators_only_look_at_the_period():
    result = stats_a(date(2021, 6, 15), date(2022, 10, 5))["indicators"]
    assert result["total"] == 75.0                     # 30 + 5 + 40
    assert result["annual_mean"] == 37.5               # 2021 and 2022 -> two years
    assert result["worst_year"] == {"year": 2022, "value": 45.0}
    assert result["peak_month"] == {"year": 2022, "month": 9, "value": 40.0}


def test_typical_peak_month_comes_from_the_historical_median():
    assert stats_a(date(2021, 6, 15), date(2022, 10, 5))["indicators"][
        "typical_peak_month"] == 9                     # median 25.0 beats 2.5 and 0
    assert build_stats(SERIES_B, start_date=date(2023, 1, 1), end_date=date(2023, 6, 30),
                       series_start_year=B_START, series_end_year=B_END,
                       cutoff_date=B_CUTOFF, area_km2=1200.0)["indicators"][
        "typical_peak_month"] == 9                     # median 20.0 beats 6.0


def test_ties_go_to_the_most_recent():
    rows = [(2021, 9, 30.0), (2022, 8, 30.0)]
    result = build_stats(rows, start_date=date(2021, 1, 1), end_date=date(2022, 12, 31),
                         series_start_year=2021, series_end_year=2022,
                         cutoff_date=date(2022, 12, 31), area_km2=1200.0)["indicators"]
    assert result["worst_year"] == {"year": 2022, "value": 30.0}
    assert result["peak_month"] == {"year": 2022, "month": 8, "value": 30.0}
    # months 8 and 9 tie on median (15.0) and on mean (15.0): lowest month wins
    assert result["typical_peak_month"] == 8


def test_single_month_period():
    result = stats_a(date(2022, 9, 1), date(2022, 9, 30))
    assert len(result["calendar"]) == 1
    assert result["calendar"][0] == {"year": 2022, "month": 9, "value": 40.0}
    assert result["indicators"]["total"] == 40.0
    assert result["indicators"]["annual_mean"] == 40.0
    assert result["indicators"]["worst_year"] == {"year": 2022, "value": 40.0}
    assert result["indicators"]["peak_month"] == {"year": 2022, "month": 9, "value": 40.0}
    assert result["anomalies"] == [{"year": 2022, "month": 9, "value": 40.0,
                                    "median": 25.0, "ratio": 1.6, "percentile": 100}]


# --------------------------------------------------------------- last_month
def test_last_month_is_the_cutoff_month():
    grid = grid_a()
    assert last_month(grid, values_per_month(grid), monthly_medians(grid), A_CUTOFF) == {
        "year": 2023, "month": 12, "value": 0.0,
        "median": 0.0, "ratio": None, "percentile": 100}


def test_last_month_shows_up_outside_the_period():
    cutoff = date(2023, 9, 30)
    result = stats_a(date(2021, 6, 15), date(2022, 10, 5), cutoff_date=cutoff)
    assert result["last_month"] == {"year": 2023, "month": 9, "value": 10.0,
                                    "median": 25.0, "ratio": 0.4, "percentile": 25}
    # the cutoff also shortens the grid: 2020-2022 in full plus 2023-01..09
    grid = grid_a(cutoff)
    assert len(grid) == 45
    assert (2023, 10) not in grid.index


def test_last_month_with_a_mid_year_cutoff():
    grid = grid_b()
    assert last_month(grid, values_per_month(grid), monthly_medians(grid), B_CUTOFF) == {
        "year": 2023, "month": 6, "value": 0.0,
        "median": 0.0, "ratio": None, "percentile": 100}


# --------------------------------------------------------------- warnings
def test_small_area_warning_fires_below_the_threshold():
    assert build_warnings(120.0, 75.0, 500.0) == [SMALL_AREA_WARNING]


def test_small_area_warning_stays_quiet_above_the_threshold():
    assert build_warnings(1200.0, 75.0, 500.0) == []


def test_small_area_threshold_is_configurable():
    assert build_warnings(120.0, 75.0, 50.0) == []
    result = stats_a(date(2021, 6, 15), date(2022, 10, 5),
                     area_km2=120.0, small_area_threshold_km2=50.0)
    assert result["warnings"] == []
    result = stats_a(date(2021, 6, 15), date(2022, 10, 5), area_km2=120.0)
    assert result["warnings"] == [SMALL_AREA_WARNING]


# --------------------------------------------------------------- edge cases
def test_empty_series():
    result = build_stats([], start_date=date(2021, 1, 1), end_date=date(2022, 12, 31),
                         series_start_year=A_START, series_end_year=A_END,
                         cutoff_date=A_CUTOFF, area_km2=1200.0)

    assert len(result["calendar"]) == 24
    assert all(month["value"] == 0.0 for month in result["calendar"])
    assert result["indicators"] == {"total": 0.0, "annual_mean": 0.0, "worst_year": None,
                                    "peak_month": None, "typical_peak_month": None}
    assert all(month["median"] == 0.0 and month["ratio"] is None
               for month in result["anomalies"])
    assert result["last_month"] == {"year": 2023, "month": 12, "value": 0.0,
                                    "median": 0.0, "ratio": None, "percentile": 100}
    assert NO_FIRE_WARNING in result["warnings"]


def test_period_without_fire_keeps_the_typical_peak_month():
    # 2020 has no fire, but the series does: typical_peak_month survives
    result = stats_a(date(2020, 1, 1), date(2020, 7, 31))["indicators"]
    assert result["total"] == 0.0
    assert result["worst_year"] is None
    assert result["peak_month"] is None
    assert result["typical_peak_month"] == 9


def test_indicators_on_an_all_zero_grid():
    grid = build_grid([], series_start_year=2020, series_end_year=2021,
                      cutoff_date=date(2021, 12, 31))
    result = indicators(grid, grid, monthly_medians(grid))
    assert result["typical_peak_month"] is None


# --------------------------------------------------------------- contract
def test_output_contract():
    result = stats_a(date(2021, 6, 15), date(2022, 10, 5), area_km2=120.0)

    assert set(result) == {"indicators", "calendar", "anomalies", "last_month", "warnings"}
    assert set(result["indicators"]) == {"total", "annual_mean", "worst_year",
                                         "peak_month", "typical_peak_month"}
    assert set(result["indicators"]["worst_year"]) == {"year", "value"}
    assert set(result["indicators"]["peak_month"]) == {"year", "month", "value"}
    assert set(result["calendar"][0]) == {"year", "month", "value"}
    assert set(result["anomalies"][0]) == {"year", "month", "value", "median",
                                           "ratio", "percentile"}
    assert set(result["last_month"]) == {"year", "month", "value", "median",
                                         "ratio", "percentile"}
    # area and period belong to the router, not to this service
    assert "area" not in result and "period" not in result

    for month in result["anomalies"]:
        assert isinstance(month["year"], int) and isinstance(month["month"], int)
        assert isinstance(month["percentile"], int)
        assert month["ratio"] is None or isinstance(month["ratio"], float)
    assert all(isinstance(text, str) for text in result["warnings"])


@pytest.mark.parametrize("month", list(range(1, 13)))
def test_every_month_of_the_series_has_a_median(month):
    assert month in monthly_medians(grid_a())
