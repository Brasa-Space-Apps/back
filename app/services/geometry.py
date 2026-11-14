from dataclasses import dataclass
from typing import Any

import h3
from pyproj import Geod
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry

H3_RESOLUTION = 7
WGS84_GEOD = Geod(ellps="WGS84")


class AreaOutsidePantanalError(ValueError):
    """Levantada quando a geometria não possui interseção válida com o Pantanal."""


@dataclass(frozen=True)
class PreparedArea:
    """Resultado do pré-processamento da geometria enviada pelo usuário."""

    geojson: dict[str, Any]
    cells: list[str]
    km2: float
    clipped: bool
    n_cells: int


def _extract_polygonal(geom: BaseGeometry) -> BaseGeometry | None:
    """Extrai apenas componentes poligonais com área positiva de uma geometria."""
    if geom.is_empty:
        return None
    if isinstance(geom, Polygon):
        return geom if geom.area > 0 else None
    if isinstance(geom, MultiPolygon):
        polys = [p for p in geom.geoms if p.area > 0]
        if not polys:
            return None
        return polys[0] if len(polys) == 1 else MultiPolygon(polys)

    # GeometryCollection pode surgir após make_valid() ou intersection()
    polys = []
    for part in getattr(geom, "geoms", ()):
        extracted = _extract_polygonal(part)
        if isinstance(extracted, Polygon):
            polys.append(extracted)
        elif isinstance(extracted, MultiPolygon):
            polys.extend(extracted.geoms)
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else MultiPolygon(polys)


def prepare_area(
    geojson: dict[str, Any],
    boundary: BaseGeometry,
) -> PreparedArea:
    """Valida, corrige e recorta a geometria pelo Pantanal, gerando células H3 (res. 7) e área em km²."""
    raw_geom = shape(geojson)
    valid_geom = _extract_polygonal(make_valid(raw_geom))
    if valid_geom is None:
        raise AreaOutsidePantanalError("Área fora do Pantanal brasileiro")

    clipped_geom = _extract_polygonal(valid_geom.intersection(boundary))
    if clipped_geom is None:
        raise AreaOutsidePantanalError("Área fora do Pantanal brasileiro")

    clipped = not valid_geom.covered_by(boundary)

    area_m2, _ = WGS84_GEOD.geometry_area_perimeter(clipped_geom)
    km2 = abs(area_m2) / 1_000_000

    clipped_geojson = mapping(clipped_geom)
    cells = sorted(set(h3.geo_to_cells(clipped_geojson, H3_RESOLUTION)))
    if not cells:
        pt = clipped_geom.representative_point()
        cells = [h3.latlng_to_cell(pt.y, pt.x, H3_RESOLUTION)]

    return PreparedArea(
        geojson=clipped_geojson,
        cells=cells,
        km2=km2,
        clipped=clipped,
        n_cells=len(cells),
    )


def cell_polygon(cell: str) -> dict[str, Any]:
    """Converte um índice H3 em um polígono GeoJSON (Polygon)."""
    raise NotImplementedError
