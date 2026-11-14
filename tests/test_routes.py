import csv
import io

import pytest
from fastapi.testclient import TestClient

from app import queries
from app.main import app

# areas used in the tests
# Near Corumbá, well inside the Brazilian Pantanal
CORUMBA = {"type": "Polygon", "coordinates": [[
    [-57.4, -19.2], [-57.0, -19.2], [-57.0, -18.8], [-57.4, -18.8], [-57.4, -19.2]]]}

# Starts inside the Pantanal and runs far east, onto the plateau: must be clipped
HALF_OUTSIDE = {"type": "Polygon", "coordinates": [[
    [-57.0, -19.2], [-50.0, -19.2], [-50.0, -18.8], [-57.0, -18.8], [-57.0, -19.2]]]}

# Around Brasília: nowhere near the Pantanal
OUTSIDE = {"type": "Polygon", "coordinates": [[
    [-48.0, -16.0], [-47.5, -16.0], [-47.5, -15.5], [-48.0, -15.5], [-48.0, -16.0]]]}

# About 1 km x 1 km inside the Pantanal: smaller than one H3 res 7 hexagon
TINY = {"type": "Polygon", "coordinates": [[
    [-57.20, -19.00], [-57.19, -19.00], [-57.19, -18.99], [-57.20, -18.99], [-57.20, -19.00]]]}

FULL = {"start_date": "2003-01-01", "end_date": "2025-12-31"}


def body(geometry, start="2003-01-01", end="2025-12-31"):
    return {"geometry": geometry, "start_date": start, "end_date": end}


@pytest.fixture(scope="module")
def client():
    """Starts the app once for the whole file (runs the lifespan: pool + cache)."""
    try:
        with TestClient(app) as c:
            yield c
    except Exception as e:  # database down, not loaded, wrong DATABASE_URL...
        pytest.skip(f"Database not available for route tests: {e}")


# ---------------------------------------------------------------- /health and /meta
def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_meta(client):
    r = client.get("/meta")
    assert r.status_code == 200
    m = r.json()
    assert set(m) == {"period", "data_cutoff", "unit", "pantanal_boundary", "factors"}
    assert m["period"]["start"] == "2003-01-01"
    assert m["data_cutoff"] == m["period"]["end"]
    assert m["pantanal_boundary"]["type"] == "Feature"
    assert m["pantanal_boundary"]["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert set(m["factors"]) == {str(i) for i in range(1, 13)}
    assert all(f > 1 for f in m["factors"].values())     # VIIRS always sees more than MODIS


# ---------------------------------------------------------------- input errors (422)
def test_point_geometry_is_rejected(client):
    r = client.post("/stats", json=body({"type": "Point", "coordinates": [-57.2, -19.0]}))
    assert r.status_code == 422


def test_start_after_end_is_rejected(client):
    r = client.post("/stats", json=body(CORUMBA, start="2020-12-31", end="2020-01-01"))
    assert r.status_code == 422


def test_missing_field_is_rejected(client):
    r = client.post("/stats", json={"geometry": CORUMBA, "start_date": "2020-01-01"})
    assert r.status_code == 422


# ---------------------------------------------------------------- business errors (400)
def test_period_outside_the_data(client):
    r = client.post("/stats", json=body(CORUMBA, start="1990-01-01", end="1995-12-31"))
    assert r.status_code == 400
    assert "Período fora dos dados" in r.json()["detail"]


@pytest.mark.parametrize("route", ["/stats", "/density", "/export"])
def test_area_outside_the_pantanal(client, route):
    r = client.post(route, json=body(OUTSIDE))
    assert r.status_code == 400
    assert r.json()["detail"] == "Área fora do Pantanal brasileiro"


# ---------------------------------------------------------------- /stats
def test_stats_contract(client):
    r = client.post("/stats", json=body(CORUMBA))
    assert r.status_code == 200
    s = r.json()
    assert set(s) == {"area", "period", "indicators", "calendar", "anomalies", "last_month", "warnings"}
    assert set(s["area"]) == {"km2", "clipped", "n_cells"}
    assert set(s["indicators"]) == {"total", "annual_mean", "worst_year", "peak_month", "typical_peak_month"}
    assert set(s["anomalies"][0]) == {"year", "month", "value", "median", "ratio", "percentile"}


def test_stats_full_series(client):
    s = client.post("/stats", json=body(CORUMBA)).json()
    n_months = len(s["calendar"])
    assert n_months == 23 * 12                         # 2003-2025, every month, zeros included
    assert len(s["anomalies"]) == n_months             # anomalies cover every month of the period
    assert s["area"]["n_cells"] > 0
    assert s["area"]["km2"] > 0
    assert s["indicators"]["total"] > 0
    assert s["indicators"]["typical_peak_month"] in (7, 8, 9, 10)   # dry season


def test_stats_period_is_clamped_to_the_series(client):
    s = client.post("/stats", json=body(CORUMBA, start="2000-01-01", end="2004-12-31")).json()
    assert s["period"]["start"] == "2003-01-01"
    assert len(s["calendar"]) == 2 * 12                # 2003 and 2004 only


def test_stats_clipped_area(client):
    s = client.post("/stats", json=body(HALF_OUTSIDE)).json()
    assert s["area"]["clipped"] is True
    assert any("recortada" in w for w in s["warnings"])


def test_stats_tiny_area(client):
    s = client.post("/stats", json=body(TINY)).json()
    assert s["area"]["n_cells"] >= 1                   # falls back to the centre hexagon
    assert any("Área pequena" in w for w in s["warnings"])


# ---------------------------------------------------------------- /density
def test_density(client):
    r = client.post("/density", json=body(CORUMBA, start="2020-01-01", end="2020-12-31"))
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) > 0
    f = fc["features"][0]
    assert set(f["properties"]) == {"h3", "value"}
    assert f["geometry"]["type"] == "Polygon"
    ring = f["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]                          # closed ring
    assert -60 < ring[0][0] < -54 and -23 < ring[0][1] < -15   # [lng, lat] order, inside the Pantanal


# ---------------------------------------------------------------- /export
def test_export_csv(client):
    r = client.post("/export", json=body(CORUMBA, start="2020-09-01", end="2020-09-30"))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="brasa_hotspots_2020-09-01_2020-09-30.csv"' in r.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == queries.EXPORT_COLUMNS
    assert len(rows) > 1                                # September 2020 near Corumbá had fire
    assert all(row[0].startswith("2020-09") for row in rows[1:])