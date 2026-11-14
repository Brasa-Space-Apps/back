"""
All API SQL in one place.

Rules:
- Always use named parameters (%(name)s). Never build SQL with f-strings.
- Python lists (list[str]) are adapted to Postgres arrays by psycopg,
  so "cell = ANY(%(cells)s)" works out of the box.
- The user's geometry arrives here ALREADY validated and clipped to the Pantanal
  (services/geometry.py), as GeoJSON text.
"""

# ---------------------------------------------------------------- /meta

# Pantanal boundary: drawn on the map and used to clip user areas. Loaded at startup.
# Params: none -> 1 row (geojson,)
PANTANAL_BOUNDARY = """
    SELECT ST_AsGeoJSON(geom) AS geojson
    FROM pantanal_boundary
    WHERE id = 1
"""

# Available period of the series (the "data cutoff" shown in the UI).
# Params: none -> 1 row (start, end)
PERIOD = """
    SELECT min(date) AS start, max(date) AS "end"
    FROM cell_days
"""

# The 12 conversion factors, for the methodology page.
# Params: none -> 12 rows (month, r)
FACTORS = """
    SELECT month, r
    FROM factors
    ORDER BY month
"""

# ---------------------------------------------------------------- /stats

# Harmonized series for the area by year and month, over the WHOLE history.
# Dates are intentionally not filtered: monthly medians use the full series.
# The requested period is applied later, in services/stats.py.
# Months without fire do NOT appear here: the service fills them with zero.
# Params: cells (list[str]) -> N rows (year, month, value)
SERIES_BY_CELLS = """
    SELECT EXTRACT(YEAR  FROM date)::int AS year,
           EXTRACT(MONTH FROM date)::int AS month,
           SUM(harmonized_value)::float  AS value
    FROM cell_days
    WHERE cell = ANY(%(cells)s)
    GROUP BY 1, 2
    ORDER BY 1, 2
"""

# ---------------------------------------------------------------- /density

# Fire days per hexagon in the requested period.
# The router turns each cell into a polygon with h3.cell_to_boundary.
# Params: cells (list[str]), start (date), end (date) -> N rows (cell, value)
DENSITY = """
    SELECT cell,
           SUM(harmonized_value)::float AS value
    FROM cell_days
    WHERE cell = ANY(%(cells)s)
      AND date BETWEEN %(start)s AND %(end)s
    GROUP BY cell
"""

# ---------------------------------------------------------------- /export

# Original hotspots inside the area and period, with the factor of their cell-day.
# Uses the GiST index on raw_hotspots.geom.
# Params: geometry (str, GeoJSON of the clipped area), start (date), end (date)
EXPORT_HOTSPOTS = """
    SELECT date,
           time_utc,
           round(ST_Y(geom)::numeric, 5) AS latitude,
           round(ST_X(geom)::numeric, 5) AS longitude,
           satellite,
           confidence,
           frp,
           day_night,
           cell AS h3,
           factor
    FROM raw_hotspots
    WHERE ST_Within(geom, ST_SetSRID(ST_GeomFromGeoJSON(%(geometry)s), 4326))
      AND date BETWEEN %(start)s AND %(end)s
    ORDER BY date, time_utc
"""

# Exported CSV header, same order as the columns above.
EXPORT_COLUMNS = [
    "date", "time_utc", "latitude", "longitude", "satellite",
    "confidence", "frp", "day_night", "h3", "factor",
]