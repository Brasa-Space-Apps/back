from fastapi import APIRouter, Request

from app import queries
from app.db import pool
from app.routers.common import area_or_400, check_dates
from app.schemas import AreaQuery, Stats
from app.services.stats import build_stats

router = APIRouter(tags=["stats"])


@router.post("/stats", response_model=Stats)
def post_stats(q: AreaQuery, request: Request):
    """Indicators, calendar and anomalies for the drawn area."""
    check_dates(q, request)
    area = area_or_400(q, request)
    series_start = request.app.state.series_start
    cutoff = request.app.state.data_cutoff

    with pool.connection() as con:
        rows = con.execute(queries.SERIES_BY_CELLS, {"cells": area.cells}).fetchall()

    result = build_stats(
        rows,
        start_date=q.start_date,
        end_date=q.end_date,
        series_start_year=series_start.year,
        series_end_year=cutoff.year,
        cutoff_date=cutoff,
        area_km2=area.km2,
    )
    if area.clipped:
        result["warnings"].insert(0, "A área foi recortada pelo limite do Pantanal brasileiro.")

    result["area"] = {"km2": round(area.km2, 1), "clipped": area.clipped, "n_cells": area.n_cells}
    result["period"] = {"start": max(q.start_date, series_start), "end": min(q.end_date, cutoff)}
    return result