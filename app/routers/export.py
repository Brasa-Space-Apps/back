import csv
import io
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app import queries
from app.db import pool
from app.routers.common import area_or_400, check_dates
from app.schemas import AreaQuery

router = APIRouter(tags=["export"])


@router.post("/export")
def post_export(q: AreaQuery, request: Request):
    check_dates(q, request)
    area = area_or_400(q, request)
    params = {
        "geometry": json.dumps(area.geojson),   
        "start": q.start_date,
        "end": q.end_date,
    }

    def rows():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(queries.EXPORT_COLUMNS)
        yield buf.getvalue()
        with pool.connection() as con, con.cursor() as cur:
            cur.execute(queries.EXPORT_HOTSPOTS, params)
            while batch := cur.fetchmany(5000):
                buf.seek(0)
                buf.truncate()
                writer.writerows(batch)
                yield buf.getvalue()

    filename = f"brasa_hotspots_{q.start_date}_{q.end_date}.csv"
    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )