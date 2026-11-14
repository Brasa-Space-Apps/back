import json
from pathlib import Path

import h3
import pytest
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from app.services.geometry import AreaOutsidePantanalError, cell_polygon, prepare_area

PANTANAL_GEOJSON = Path(__file__).resolve().parents[1] / "data" / "pantanal.geojson"


@pytest.fixture(scope="module")
def pantanal_boundary():
    data = json.loads(PANTANAL_GEOJSON.read_text(encoding="utf-8"))
    features = data.get("features", [data])
    geoms = [shape(f.get("geometry", f)) for f in features]
    return unary_union(geoms)


def test_polygon_inside_pantanal(pantanal_boundary):
    geojson = {
        "type": "Polygon",
        "coordinates": [
            [
                [-57.4, -19.0],
                [-57.1, -19.0],
                [-57.1, -18.8],
                [-57.4, -18.8],
                [-57.4, -19.0],
            ]
        ],
    }

    result = prepare_area(geojson, pantanal_boundary)

    assert result.clipped is False
    assert result.n_cells == len(result.cells)
    assert result.n_cells > 0
    assert result.km2 > 0
    assert all(h3.get_resolution(c) == 7 for c in result.cells)


def test_polygon_partially_outside_pantanal_is_clipped(pantanal_boundary):
    # Caixa grande que cruza a borda oeste do Pantanal
    geojson = {
        "type": "Polygon",
        "coordinates": [
            [
                [-60.0, -19.5],
                [-57.0, -19.5],
                [-57.0, -18.5],
                [-60.0, -18.5],
                [-60.0, -19.5],
            ]
        ],
    }

    result = prepare_area(geojson, pantanal_boundary)

    assert result.clipped is True
    assert result.n_cells > 0
    assert result.km2 > 0


def test_polygon_outside_pantanal_raises_error(pantanal_boundary):
    # São Paulo (fora do Pantanal)
    geojson = {
        "type": "Polygon",
        "coordinates": [
            [
                [-46.8, -23.7],
                [-46.5, -23.7],
                [-46.5, -23.4],
                [-46.8, -23.4],
                [-46.8, -23.7],
            ]
        ],
    }

    with pytest.raises(AreaOutsidePantanalError):
        prepare_area(geojson, pantanal_boundary)


def test_self_intersecting_polygon_is_repaired(pantanal_boundary):
    # Polígono em formato "gravata-borboleta" (auto-interseção) dentro do Pantanal
    geojson = {
        "type": "Polygon",
        "coordinates": [
            [
                [-57.4, -19.0],
                [-57.2, -18.8],
                [-57.2, -19.0],
                [-57.4, -18.8],
                [-57.4, -19.0],
            ]
        ],
    }

    result = prepare_area(geojson, pantanal_boundary)

    assert result.clipped is False
    assert result.n_cells > 0
    assert result.km2 > 0


def test_tiny_polygon_uses_representative_point_fallback(pantanal_boundary):
    # Polígono muito menor que um hexágono H3 res 7 (~5 km²)
    geojson = {
        "type": "Polygon",
        "coordinates": [
            [
                [-57.2500, -18.9000],
                [-57.2480, -18.9000],
                [-57.2480, -18.8980],
                [-57.2500, -18.8980],
                [-57.2500, -18.9000],
            ]
        ],
    }

    result = prepare_area(geojson, pantanal_boundary)

    assert result.clipped is False
    assert result.n_cells == 1
    assert len(result.cells) == 1
    assert h3.get_resolution(result.cells[0]) == 7
    assert 0 < result.km2 < 1


def test_multipolygon_inside_pantanal(pantanal_boundary):
    geojson = {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [
                    [-57.4, -19.0],
                    [-57.3, -19.0],
                    [-57.3, -18.9],
                    [-57.4, -18.9],
                    [-57.4, -19.0],
                ]
            ],
            [
                [
                    [-57.1, -18.7],
                    [-57.0, -18.7],
                    [-57.0, -18.6],
                    [-57.1, -18.6],
                    [-57.1, -18.7],
                ]
            ],
        ],
    }

    result = prepare_area(geojson, pantanal_boundary)

    assert result.clipped is False
    assert result.n_cells > 0
    assert result.geojson["type"] == "MultiPolygon"


def test_cell_polygon_returns_valid_closed_geojson():
    cell = h3.latlng_to_cell(-18.9, -57.3, 7)
    poly = cell_polygon(cell)

    assert poly["type"] == "Polygon"
    assert len(poly["coordinates"]) == 1
    ring = poly["coordinates"][0]
    assert len(ring) == 7  # 6 vértices + ponto de fechamento
    assert ring[0] == ring[-1]
    assert shape(poly).is_valid


def test_cell_polygon_contains_cell_center():
    cell = h3.latlng_to_cell(-18.9, -57.3, 7)
    poly = cell_polygon(cell)
    lat, lng = h3.cell_to_latlng(cell)

    assert shape(poly).contains(Point(lng, lat))


def test_cell_polygon_invalid_cell_raises_value_error():
    with pytest.raises(ValueError):
        cell_polygon("invalid_h3_index")
