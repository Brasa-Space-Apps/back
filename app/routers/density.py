from fastapi import APIRouter, Request

from app import queries
from app.db import pool
from app.routers.common import area_or_400, check_dates
from app.schemas import AreaQuery
from app.services.geometry import cell_polygon

router = APIRouter(tags=["density"])


@router.post("/density")
def post_density(q: AreaQuery, request: Request):
    """Fire days per H3 hexagon inside the area, as a GeoJSON FeatureCollection."""
    check_dates(q, request)
    area = area_or_400(q, request)

    with pool.connection() as con:
        rows = con.execute(
            queries.DENSITY, {"cells": area.cells, "start": q.start_date, "end": q.end_date}
        ).fetchall()

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"h3": cell, "value": round(value, 1)},
                "geometry": cell_polygon(cell),
            }
            for cell, value in rows
        ],
    }