"""
Brasa - loads the processed data into PostGIS.

Reads back/data:
  celulas_dia.csv.gz   -> cell_days          (harmonized series)
  pantanal/*.csv       -> raw_hotspots       (only hotspots that make up the series)
  pantanal.geojson     -> pantanal_boundary
  fatores_c1dia.csv    -> factors

Safe to run many times: tables are truncated before loading.

Install: pip install "psycopg[binary]" pandas h3
Usage (from back/):
  python scripts/load_postgis.py
  python scripts/load_postgis.py --data data --database-url postgresql://...
"""
import argparse
import gzip
import io
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
BACK = HERE.parent
H3_RES = 7
SERIES_START, VIIRS_START = 2003, 2012


# ---------------------------------------------------------------- config
def read_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def database_url(arg: str | None) -> str:
    url = arg or os.environ.get("DATABASE_URL") or read_env(BACK / ".env").get("DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL (in .env, as an environment variable, or with --database-url).")
    return url


# ---------------------------------------------------------------- hotspots
def prepare_hotspots(folder: Path, factor_by_cell_day: pd.DataFrame) -> pd.DataFrame:
    """Same filters as aplicar_harmonizacao.py; keeps only hotspots that make up the series."""
    import h3

    parts = []
    for pattern, sensor in [("modis_*.csv", "MODIS"), ("viirs-snpp_*.csv", "VIIRS")]:
        for path in sorted(folder.glob(pattern)):
            df = pd.read_csv(path, dtype={"acq_time": str, "confidence": str},
                             usecols=["latitude", "longitude", "acq_date", "acq_time", "satellite",
                                      "confidence", "frp", "daynight", "type"])
            df["sensor"] = sensor
            parts.append(df)
    if not parts:
        sys.exit(f"No modis_*.csv or viirs-snpp_*.csv found in {folder}")
    f = pd.concat(parts, ignore_index=True)

    f["sat"] = f.satellite.astype(str).map({"Aqua": "Aqua", "A": "Aqua", "N": "SNPP"})
    year = f.acq_date.str[:4].astype(int)
    conf_num = pd.to_numeric(f.confidence, errors="coerce")
    ok_modis = (f.sensor == "MODIS") & (conf_num >= 30)
    ok_viirs = (f.sensor == "VIIRS") & f.confidence.str.lower().isin(["n", "h", "nominal", "high"])
    aqua_series = (f.sat == "Aqua") & (f.daynight == "D") & (year >= SERIES_START) & (year < VIIRS_START)
    snpp_series = (f.sat == "SNPP") & (year >= VIIRS_START)
    f = f[(f["type"] == 0) & (ok_modis | ok_viirs) & (aqua_series | snpp_series)].copy()

    f["cell"] = [h3.latlng_to_cell(la, lo, H3_RES) for la, lo in zip(f.latitude, f.longitude)]
    f = f.merge(factor_by_cell_day, left_on=["cell", "acq_date"], right_on=["cell", "date"], how="left")
    missing = int(f.factor.isna().sum())
    if missing:
        print(f"  warning: {missing:,} hotspots without a matching cell-day (dropped). "
              "Are celulas_dia.csv.gz and the CSVs from the same run?")
        f = f[f.factor.notna()]

    return pd.DataFrame({
        "geom": "SRID=4326;POINT(" + f.longitude.astype(str) + " " + f.latitude.astype(str) + ")",
        "date": f.acq_date,
        "time_utc": f.acq_time.str.zfill(4),
        "satellite": f.sat,
        "confidence": f.confidence.astype(str),
        "frp": f.frp,
        "day_night": f.daynight,
        "cell": f.cell,
        "factor": f.factor.round(4),
    })


# ---------------------------------------------------------------- load
def copy_csv(cur, table: str, columns: list[str], source):
    """COPY from a CSV file (or buffer) with a header row. Columns map by position."""
    sql = f"COPY {table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with cur.copy(sql) as copy:
        while chunk := source.read(1 << 20):
            copy.write(chunk)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=BACK / "data", type=Path)
    p.add_argument("--database-url", default=None)
    a = p.parse_args()

    import psycopg

    cells_file = a.data / "celulas_dia.csv.gz"
    boundary_file = a.data / "pantanal.geojson"
    factors_file = a.data / "fatores_c1dia.csv"
    hotspots_folder = a.data / "pantanal"
    for path in (cells_file, boundary_file, factors_file, hotspots_folder):
        if not path.exists():
            sys.exit(f"Not found: {path}")

    start = time.time()
    print("Preparing raw hotspots...")
    # the pipeline output keeps Portuguese headers; rename them here
    cd = pd.read_csv(cells_file, usecols=["celula", "data", "fator"]).rename(
        columns={"celula": "cell", "data": "date", "fator": "factor"})
    if not cd.cell.astype(str).str.match(r"^[0-9a-f]{15}$").all():
        sys.exit("celulas_dia.csv.gz does not look like H3 indexes. Regenerate it with the h3 package installed.")
    hotspots = prepare_hotspots(hotspots_folder, cd)
    print(f"  {len(hotspots):,} hotspots in the series")

    hotspots_buf = io.BytesIO(hotspots.to_csv(index=False).encode())
    geometries = [json.dumps(feat["geometry"]) for feat in json.loads(boundary_file.read_text())["features"]]

    print("Connecting to the database...")
    with psycopg.connect(database_url(a.database_url)) as con, con.cursor() as cur:
        cur.execute("TRUNCATE cell_days, raw_hotspots, pantanal_boundary, factors RESTART IDENTITY")

        print("Loading cell_days...")
        with gzip.open(cells_file, "rb") as fh:
            copy_csv(cur, "cell_days",
                     ["cell", "date", "harmonized_value", "factor", "source", "n_hotspots", "frp_max"], fh)

        print("Loading raw_hotspots...")
        copy_csv(cur, "raw_hotspots", list(hotspots.columns), hotspots_buf)

        print("Loading pantanal_boundary...")
        cur.execute("""
            INSERT INTO pantanal_boundary (id, geom)
            SELECT 1, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Union(
                       ST_SetSRID(ST_GeomFromGeoJSON(g), 4326))), 3))
            FROM unnest(%s::text[]) AS g
        """, (geometries,))

        print("Loading factors...")
        fac = pd.read_csv(factors_file)
        cur.executemany("INSERT INTO factors (month, r, source) VALUES (%s, %s, %s)",
                        list(zip(fac.mes.astype(int), fac.R.astype(float), fac.origem.astype(str))))
        con.commit()

        con.autocommit = True
        tables = ("cell_days", "raw_hotspots", "pantanal_boundary", "factors")
        for t in tables:
            cur.execute(f"ANALYZE {t}")

        print("\n=== Check ===")
        for t in tables:
            cur.execute(f"SELECT count(*) FROM {t}")
            print(f"  {t:18s} {cur.fetchone()[0]:>10,} rows")
        cur.execute("SELECT round(ST_Area(geom::geography) / 1e6) FROM pantanal_boundary")
        print(f"  Pantanal area: {cur.fetchone()[0]:,.0f} km²")
        cur.execute("SELECT min(date), max(date) FROM cell_days")
        print("  period: %s to %s" % cur.fetchone())
        cur.execute("""SELECT EXTRACT(YEAR FROM date)::int, round(sum(harmonized_value))::int
                       FROM cell_days GROUP BY 1 ORDER BY 2 DESC LIMIT 5""")
        print("  top 5 fire years: " + ", ".join(f"{y} ({v:,})" for y, v in cur.fetchall()))

    print(f"\nDone in {time.time() - start:,.0f} s")


if __name__ == "__main__":
    main()