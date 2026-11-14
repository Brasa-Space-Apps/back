CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS celulas_dia (
    celula TEXT NOT NULL,
    -- código H3 res 7
    data DATE NOT NULL,
    valor_harmonizado REAL NOT NULL,
    fator REAL NOT NULL,
    origem TEXT NOT NULL,
    -- 'MODIS-Aqua' | 'VIIRS-SNPP'
    n_focos SMALLINT NOT NULL,
    frp_max REAL,
    PRIMARY KEY (celula, data)
);
CREATE INDEX IF NOT EXISTS idx_celulas_dia_data ON celulas_dia (data);
CREATE TABLE IF NOT EXISTS focos_brutos (
    id BIGSERIAL PRIMARY KEY,
    geom GEOMETRY(Point, 4326) NOT NULL,
    data DATE NOT NULL,
    hora_utc CHAR(4) NOT NULL,
    satelite TEXT NOT NULL,
    -- 'Aqua' | 'SNPP'
    confianca TEXT NOT NULL,
    frp REAL,
    dia_noite CHAR(1) NOT NULL,
    celula TEXT NOT NULL,
    fator REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_focos_geom ON focos_brutos USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_focos_data ON focos_brutos (data);
CREATE TABLE IF NOT EXISTS limite_pantanal (
    id INT PRIMARY KEY,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE TABLE IF NOT EXISTS fatores (
    mes SMALLINT PRIMARY KEY,
    r REAL NOT NULL,
    origem TEXT
);