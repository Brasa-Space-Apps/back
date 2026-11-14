from datetime import date
from typing import Any

from pydantic import BaseModel, Field, model_validator


# input
class AreaQuery(BaseModel):
    geometry: dict[str, Any] = Field(description="GeoJSON Polygon or MultiPolygon (geometry only, not a Feature)")
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def check(self):
        if self.geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("geometry must be a GeoJSON Polygon or MultiPolygon")
        if self.start_date > self.end_date:
            raise ValueError("start_date must be before end_date")
        return self


# output
class Period(BaseModel):
    start: date
    end: date


class Meta(BaseModel):
    period: Period
    data_cutoff: date
    unit: str
    pantanal_boundary: dict[str, Any]  
    factors: dict[str, float]         


class Area(BaseModel):
    km2: float
    clipped: bool
    n_cells: int


class YearValue(BaseModel):
    year: int
    value: float


class MonthValue(BaseModel):
    year: int
    month: int
    value: float


class Indicators(BaseModel):
    total: float
    annual_mean: float
    worst_year: YearValue | None
    peak_month: MonthValue | None
    typical_peak_month: int | None


class Anomaly(MonthValue):
    median: float
    ratio: float | None
    percentile: int


class Stats(BaseModel):
    area: Area
    period: Period
    indicators: Indicators
    calendar: list[MonthValue]
    anomalies: list[Anomaly]
    last_month: Anomaly | None
    warnings: list[str]