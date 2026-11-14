from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class PreparedArea:
    """Resultado do pré-processamento da geometria enviada pelo usuário."""

    geojson: dict[str, Any]
    cells: list[str]
    km2: float
    clipped: bool
    n_cells: int


def prepare_area(
    geojson: dict[str, Any],
    boundary: BaseGeometry,
) -> PreparedArea:
    """Valida, corrige e recorta a geometria pelo Pantanal, gerando células H3 (res. 7) e área em km²."""
    raise NotImplementedError


def cell_polygon(cell: str) -> dict[str, Any]:
    """Converte um índice H3 em um polígono GeoJSON (Polygon)."""
    raise NotImplementedError
