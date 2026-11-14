"""Pure statistics for POST /stats: no database, no FastAPI.

Input is the WHOLE series of the selected cells as (year, month, value) rows,
exactly what queries.SERIES_BY_CELLS returns. Months without fire are absent
from it; this module fills them with zero, computes medians and percentiles
over the full series, and only then applies the requested period.

The period is assumed valid and touching the series: start > end is a 422 from
the Pydantic model and a period outside the data is a 400 from routers/common.

Contract keys are English (section 7); only `warnings` strings are Portuguese.
The metric is "fire days (per ~5 km2 area)", never "hotspots".
"""
from collections.abc import Iterable
from datetime import date

import pandas as pd

from app.config import SMALL_AREA_THRESHOLD_KM2

MONTHS = range(1, 13)

# User-facing text, in Portuguese. The 2012 in the caveat is the year VIIRS
# joins the series (scripts/load_postgis.py), so it is fixed; the area
# threshold behind it is not.
SMALL_AREA_WARNING = "Área pequena: os anos antes de 2012 têm incerteza maior."
NO_FIRE_WARNING = "Nenhum dia com fogo no período selecionado."

VALUE_DECIMALS, RATIO_DECIMALS = 1, 2


def build_grid(
    rows: Iterable[tuple[int, int, float]],
    *,
    series_start_year: int,
    series_end_year: int,
    cutoff_date: date,
) -> pd.DataFrame:
    """Full year x month grid with zeros where there was no fire.

    Months after cutoff_date are left out entirely: not observed is not zero,
    and filling them would drag those months' medians and percentiles down.
    Returns a DataFrame indexed by (year, month) with a single "value" column.
    """
    observed = [
        (year, month)
        for year in range(series_start_year, series_end_year + 1)
        for month in MONTHS
        if (year, month) <= (cutoff_date.year, cutoff_date.month)
    ]
    index = pd.MultiIndex.from_tuples(observed, names=["year", "month"])

    frame = pd.DataFrame(list(rows), columns=["year", "month", "value"]).astype(
        {"year": "int64", "month": "int64", "value": "float64"})

    # reindex also drops anything outside the series or after the cutoff
    return (frame.groupby(["year", "month"])["value"].sum()
            .reindex(index, fill_value=0.0)
            .to_frame("value"))


def values_per_month(grid: pd.DataFrame) -> dict[int, list[float]]:
    """Every observed year's value for each calendar month, zeros included."""
    return {int(month): [float(v) for v in values]
            for month, values in grid["value"].groupby(level="month")}


def monthly_medians(grid: pd.DataFrame) -> dict[int, float]:
    """Median of each calendar month across every observed year, zeros included.

    This is the historical baseline and never depends on the requested period.
    """
    return {int(month): float(values.median())
            for month, values in grid["value"].groupby(level="month")}


def percentile(value: float, month_values: Iterable[float]) -> int:
    """Share of years whose value is <= `value`, in percent.

    Inclusive and counts the year itself, so the series maximum is always 100.
    Rounded to an integer.
    """
    values = list(month_values)
    if not values:
        return 0
    return round(100 * sum(1 for v in values if v <= value) / len(values))


def ratio(value: float, median: float) -> float | None:
    """value / median, or None when the median is 0."""
    if median == 0:
        return None
    return round(value / median, RATIO_DECIMALS)


def filter_period(grid: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    """Months intersecting [start_date, end_date].

    The data is monthly, so a partial month comes whole: asking for 20-30/09
    returns all of September.
    """
    start = (start_date.year, start_date.month)
    end = (end_date.year, end_date.month)
    return grid[[start <= (year, month) <= end for year, month in grid.index]]


def indicators(period: pd.DataFrame, grid: pd.DataFrame, medians: dict[int, float]) -> dict:
    """total, annual_mean, worst_year, peak_month, typical_peak_month.

    The first four come from `period`; typical_peak_month comes from the whole
    series, so it survives a period with no fire. annual_mean divides by the
    number of distinct calendar years in the period, so a partial year counts
    as one. Ties go to the most recent year/month, and typical_peak_month
    breaks ties by the month's series mean and then by the lowest month number.

    worst_year and peak_month are None when the period has no fire at all:
    reporting the first year of the series as the "worst" would be a lie.
    """
    total = float(period["value"].sum())
    years = {year for year, _ in period.index}
    annual_mean = total / len(years) if years else 0.0

    worst_year = peak_month = None
    if total > 0:
        by_year = period["value"].groupby(level="year").sum()
        year, value = max(((int(y), float(v)) for y, v in by_year.items()),
                          key=lambda item: (item[1], item[0]))
        worst_year = {"year": year, "value": round(value, VALUE_DECIMALS)}

        (peak_y, peak_m), peak_v = max(
            (((int(y), int(m)), float(v)) for (y, m), v in period["value"].items()),
            key=lambda item: (item[1], item[0]))
        peak_month = {"year": peak_y, "month": peak_m,
                      "value": round(peak_v, VALUE_DECIMALS)}

    typical_peak_month = None
    if float(grid["value"].sum()) > 0:
        means = {int(month): float(values.mean())
                 for month, values in grid["value"].groupby(level="month")}
        typical_peak_month = max(
            medians, key=lambda month: (medians[month], means[month], -month))

    return {
        "total": round(total, VALUE_DECIMALS),
        "annual_mean": round(annual_mean, VALUE_DECIMALS),
        "worst_year": worst_year,
        "peak_month": peak_month,
        "typical_peak_month": typical_peak_month,
    }


def comparison(
    year: int,
    month: int,
    value: float,
    values_by_month: dict[int, list[float]],
    medians: dict[int, float],
) -> dict:
    """{year, month, value, median, ratio, percentile} for a single month."""
    value, median = float(value), medians[int(month)]
    return {
        "year": int(year),
        "month": int(month),
        "value": round(value, VALUE_DECIMALS),
        "median": round(median, VALUE_DECIMALS),
        "ratio": ratio(value, median),
        "percentile": percentile(value, values_by_month[int(month)]),
    }


def last_month(
    grid: pd.DataFrame,
    values_by_month: dict[int, list[float]],
    medians: dict[int, float],
    cutoff_date: date,
) -> dict:
    """The cutoff month (RF14), always reported even outside the requested period.

    It is the dashboard's "current month", so the period the user asked for does
    not apply to it. A cutoff month without fire reports 0.0 against its own
    historical median.
    """
    key = (cutoff_date.year, cutoff_date.month)
    value = float(grid["value"].loc[key]) if key in grid.index else 0.0
    return comparison(key[0], key[1], value, values_by_month, medians)


def build_warnings(area_km2: float, total: float, threshold_km2: float) -> list[str]:
    """User-facing caveats, in Portuguese: small area (pre-2012) and no fire."""
    warnings = []
    if area_km2 < threshold_km2:
        warnings.append(SMALL_AREA_WARNING)
    if total == 0:
        warnings.append(NO_FIRE_WARNING)
    return warnings


def build_stats(
    rows: Iterable[tuple[int, int, float]],
    *,
    start_date: date,
    end_date: date,
    series_start_year: int,
    series_end_year: int,
    cutoff_date: date,
    area_km2: float,
    small_area_threshold_km2: float = SMALL_AREA_THRESHOLD_KM2,
) -> dict:
    """Everything POST /stats returns except `area` and `period`.

    `rows` is the whole series of the selected cells; the series bounds and the
    cutoff come from the caller (the /meta values cached in app.state), never
    from constants in here.

    -> {"indicators": {...}, "calendar": [...], "anomalies": [...],
        "last_month": {...}, "warnings": [...]}
    """
    grid = build_grid(rows, series_start_year=series_start_year,
                      series_end_year=series_end_year, cutoff_date=cutoff_date)
    medians = monthly_medians(grid)
    values_by_month = values_per_month(grid)

    period = filter_period(grid, start_date, end_date)
    computed = indicators(period, grid, medians)

    return {
        "indicators": computed,
        "calendar": [{"year": int(year), "month": int(month),
                      "value": round(float(value), VALUE_DECIMALS)}
                     for (year, month), value in period["value"].items()],
        "anomalies": [comparison(year, month, value, values_by_month, medians)
                      for (year, month), value in period["value"].items()],
        "last_month": last_month(grid, values_by_month, medians, cutoff_date),
        "warnings": build_warnings(area_km2, computed["total"], small_area_threshold_km2),
    }
