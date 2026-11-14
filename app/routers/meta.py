from fastapi import APIRouter, Request

from app.schemas import Meta

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=Meta)
def get_meta(request: Request):
    return request.app.state.meta