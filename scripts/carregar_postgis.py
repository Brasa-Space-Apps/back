import argparse
import gzip
import io
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
BACK = AQUI.parent
RES_H3 = 7
INICIO, ANO_VIIRS = 2003, 2012


# ---------------------------------------------------------------- configuração
def ler_env(arquivo: Path) -> dict:
    env = {}
    if arquivo.exists():
        for linha in arquivo.read_text().splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def url_banco(arg: str | None) -> str:
    url = arg or os.environ.get("DATABASE_URL") or ler_env(BACK / ".env").get("DATABASE_URL")
    if not url:
        sys.exit("Defina DATABASE_URL (no .env, como variável de ambiente ou com --database-url).")
    return url


def preparar_focos(pasta: Path, fator_por_celula_dia: pd.DataFrame) -> pd.DataFrame:
    """Mesmos filtros do aplicar_harmonizacao.py; só os focos que entram na série."""
    import h3

    partes = []
    for padrao, sensor in [("modis_*.csv", "MODIS"), ("viirs-snpp_*.csv", "VIIRS")]:
        for arq in sorted(pasta.glob(padrao)):
            df = pd.read_csv(arq, dtype={"acq_time": str, "confidence": str},
                             usecols=["latitude", "longitude", "acq_date", "acq_time", "satellite",
                                      "confidence", "frp", "daynight", "type"])
            df["sensor"] = sensor
            partes.append(df)
    if not partes:
        sys.exit(f"Nenhum modis_*.csv ou viirs-snpp_*.csv em {pasta}")
    f = pd.concat(partes, ignore_index=True)

    f["sat"] = f.satellite.astype(str).map({"Aqua": "Aqua", "A": "Aqua", "N": "SNPP"})
    ano = f.acq_date.str[:4].astype(int)
    conf_num = pd.to_numeric(f.confidence, errors="coerce")
    ok_modis = (f.sensor == "MODIS") & (conf_num >= 30)
    ok_viirs = (f.sensor == "VIIRS") & f.confidence.str.lower().isin(["n", "h", "nominal", "high"])
    serie_aqua = (f.sat == "Aqua") & (f.daynight == "D") & (ano >= INICIO) & (ano < ANO_VIIRS)
    serie_snpp = (f.sat == "SNPP") & (ano >= ANO_VIIRS)
    f = f[(f["type"] == 0) & (ok_modis | ok_viirs) & (serie_aqua | serie_snpp)].copy()

    f["celula"] = [h3.latlng_to_cell(la, lo, RES_H3) for la, lo in zip(f.latitude, f.longitude)]
    f = f.merge(fator_por_celula_dia, left_on=["celula", "acq_date"], right_on=["celula", "data"], how="left")
    sem_fator = int(f.fator.isna().sum())
    if sem_fator:
        print(f"  aviso: {sem_fator:,} focos sem célula-dia correspondente (descartados). "
              "O celulas_dia.csv.gz e os CSVs são da mesma rodada?")
        f = f[f.fator.notna()]

    return pd.DataFrame({
        "geom": "SRID=4326;POINT(" + f.longitude.astype(str) + " " + f.latitude.astype(str) + ")",
        "data": f.acq_date,
        "hora_utc": f.acq_time.str.zfill(4),
        "satelite": f.sat,
        "confianca": f.confidence.astype(str),
        "frp": f.frp,
        "dia_noite": f.daynight,
        "celula": f.celula,
        "fator": f.fator.round(4),
    })


# ---------------------------------------------------------------- carga
def copiar(cur, tabela: str, colunas: list[str], fonte):
    """COPY de um arquivo (ou buffer) CSV com cabeçalho."""
    sql = f"COPY {tabela} ({', '.join(colunas)}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with cur.copy(sql) as copy:
        while bloco := fonte.read(1 << 20):
            copy.write(bloco)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=BACK / "data", type=Path)
    p.add_argument("--database-url", default=None)
    a = p.parse_args()

    import psycopg

    arq_celulas = a.data / "celulas_dia.csv.gz"
    arq_geojson = a.data / "pantanal.geojson"
    arq_fatores = a.data / "fatores_c1dia.csv"
    pasta_focos = a.data / "pantanal"
    for arq in (arq_celulas, arq_geojson, arq_fatores, pasta_focos):
        if not arq.exists():
            sys.exit(f"Não encontrei {arq}")

    inicio = time.time()
    print("Preparando os focos brutos...")
    cd = pd.read_csv(arq_celulas, usecols=["celula", "data", "fator"])
    if not cd.celula.astype(str).str.match(r"^[0-9a-f]{15}$").all():
        sys.exit("O celulas_dia.csv.gz não parece ter códigos H3. Gere de novo com o pacote h3 instalado.")
    focos = preparar_focos(pasta_focos, cd)
    print(f"  {len(focos):,} focos na série")

    buf_focos = io.BytesIO(focos.to_csv(index=False).encode())
    geometrias = [json.dumps(feat["geometry"]) for feat in json.loads(arq_geojson.read_text())["features"]]

    print("Conectando ao banco...")
    with psycopg.connect(url_banco(a.database_url)) as con, con.cursor() as cur:
        cur.execute("TRUNCATE celulas_dia, focos_brutos, limite_pantanal, fatores RESTART IDENTITY")

        print("Carregando celulas_dia...")
        with gzip.open(arq_celulas, "rb") as fh:
            copiar(cur, "celulas_dia",
                   ["celula", "data", "valor_harmonizado", "fator", "origem", "n_focos", "frp_max"], fh)

        print("Carregando focos_brutos...")
        copiar(cur, "focos_brutos", list(focos.columns), buf_focos)

        print("Carregando limite_pantanal...")
        cur.execute("""
            INSERT INTO limite_pantanal (id, geom)
            SELECT 1, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Union(
                       ST_SetSRID(ST_GeomFromGeoJSON(g), 4326))), 3))
            FROM unnest(%s::text[]) AS g
        """, (geometrias,))

        print("Carregando fatores...")
        fat = pd.read_csv(arq_fatores)
        cur.executemany("INSERT INTO fatores (mes, r, origem) VALUES (%s, %s, %s)",
                        list(zip(fat.mes.astype(int), fat.R.astype(float), fat.origem.astype(str))))
        con.commit()

        con.autocommit = True
        for t in ("celulas_dia", "focos_brutos", "limite_pantanal", "fatores"):
            cur.execute(f"ANALYZE {t}")

        print("\n=== Conferência ===")
        for t in ("celulas_dia", "focos_brutos", "limite_pantanal", "fatores"):
            cur.execute(f"SELECT count(*) FROM {t}")
            print(f"  {t:16s} {cur.fetchone()[0]:>10,} linhas")
        cur.execute("SELECT round(ST_Area(geom::geography) / 1e6) FROM limite_pantanal")
        print(f"  área do Pantanal: {cur.fetchone()[0]:,.0f} km²")
        cur.execute("SELECT min(data), max(data) FROM celulas_dia")
        print("  período: %s a %s" % cur.fetchone())
        cur.execute("""SELECT EXTRACT(YEAR FROM data)::int, round(sum(valor_harmonizado))::int
                       FROM celulas_dia GROUP BY 1 ORDER BY 2 DESC LIMIT 5""")
        print("  5 anos com mais fogo: " + ", ".join(f"{a} ({v:,})" for a, v in cur.fetchall()))

    print(f"\nPronto em {time.time() - inicio:,.0f} s")


if __name__ == "__main__":
    main()