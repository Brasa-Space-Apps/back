from fastapi import HTTPException, Request

from app.schemas import AreaQuery
from app.services.geometry import AreaOutsidePantanalError, PreparedArea, prepare_area


def check_dates(q: AreaQuery, request: Request) -> None:
    start, cutoff = request.app.state.series_start, request.app.state.data_cutoff
    if q.end_date < start or q.start_date > cutoff:
        raise HTTPException(400, f"Período fora dos dados disponíveis ({start} a {cutoff})")


def area_or_400(q: AreaQuery, request: Request) -> PreparedArea:
    try:
        return prepare_area(q.geometry, request.app.state.boundary)
    except AreaOutsidePantanalError as e:
        raise HTTPException(400, str(e))