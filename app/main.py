import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import shape

from app import queries
from app.config import FRONT_ORIGINS, UNIT_LABEL
from app.db import pool
from app.routers import meta


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True)
    with pool.connection() as con:
        (boundary_geojson,) = con.execute(queries.PANTANAL_BOUNDARY).fetchone()
        start, end = con.execute(queries.PERIOD).fetchone()
        factors = con.execute(queries.FACTORS).fetchall()

    boundary_geom = json.loads(boundary_geojson)
    app.state.boundary = shape(boundary_geom)      
    app.state.series_start = start
    app.state.data_cutoff = end
    app.state.meta = {
        "period": {"start": start, "end": end},
        "data_cutoff": end,
        "unit": UNIT_LABEL,
        "pantanal_boundary": {"type": "Feature", "properties": {"name": "Pantanal"}, "geometry": boundary_geom},
        "factors": {str(m): round(r, 4) for m, r in factors},
    }
    yield
    pool.close()


app = FastAPI(title="Brasa API", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONT_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(meta.router)
#colocar os outros routers aqui quando estiverem prontos

@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}