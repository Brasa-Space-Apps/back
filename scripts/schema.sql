CREATE EXTENSION IF NOT EXISTS postgis;
-- Harmonized series: one row per H3 cell per day with fire
CREATE TABLE IF NOT EXISTS cell_days (
    cell TEXT NOT NULL,
    -- H3 res 7 index
    date DATE NOT NULL,
    harmonized_value REAL NOT NULL,
    -- VIIRS-equivalent value (summed by the API)
    factor REAL NOT NULL,
    -- 1 for VIIRS, R_m for MODIS
    source TEXT NOT NULL,
    -- 'MODIS-Aqua' | 'VIIRS-SNPP'
    n_hotspots SMALLINT NOT NULL,
    frp_max REAL,
    PRIMARY KEY (cell, date)
);
CREATE INDEX IF NOT EXISTS idx_cell_days_date ON cell_days (date);
-- Original FIRMS hotspots that make up the series (used by CSV export)
CREATE TABLE IF NOT EXISTS raw_hotspots (
    id BIGSERIAL PRIMARY KEY,
    geom GEOMETRY(Point, 4326) NOT NULL,
    date DATE NOT NULL,
    time_utc CHAR(4) NOT NULL,
    -- HHMM
    satellite TEXT NOT NULL,
    -- 'Aqua' | 'SNPP'
    confidence TEXT NOT NULL,
    frp REAL,
    day_night CHAR(1) NOT NULL,
    -- 'D' | 'N'
    cell TEXT NOT NULL,
    -- links the hotspot to its cell-day
    factor REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_hotspots_geom ON raw_hotspots USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_raw_hotspots_date ON raw_hotspots (date);
-- Brazilian Pantanal boundary (IBGE 2019)
CREATE TABLE IF NOT EXISTS pantanal_boundary (
    id INT PRIMARY KEY,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);
-- The 12 monthly conversion factors (C1-day method)
CREATE TABLE IF NOT EXISTS factors (
    month SMALLINT PRIMARY KEY,
    r REAL NOT NULL,
    source TEXT
);