# AI-assisted: generated with Claude (Anthropic) and reviewed by the Brasa team.
"""
Brasa - compara o ranking anual da nossa série harmonizada com o do INPE (Issue 14).

Lado do INPE: focos anuais do satélite de referência (Aqua tarde) do BDQueimadas,
baixados de dataserver-coids.inpe.br (focos_br_ref_<ANO>.zip). Duas contagens:
  focos_inpe            -> bioma = 'Pantanal', como o INPE publica
  focos_no_nosso_limite -> os mesmos focos recortados pelo limite IBGE 2019 + 2 km
                           (a pegada da nossa série), para separar diferença de
                           fronteira de diferença de método.

Nosso lado: soma anual de valor_harmonizado de data/celulas_dia.csv.gz
(unidade "dias com fogo"), o mesmo dado que vai para cell_days no PostGIS.

Focos e dias com fogo têm unidades diferentes: a comparação que importa é de
ORDEM (Spearman/Kendall sobre os postos), não de nível.

Escreve:
  data/inpe_pantanal_anual.csv           (ano, focos_inpe, focos_no_nosso_limite)
  docs/ranking_inpe_vs_harmonizado.csv   (tabela lado a lado completa)
e imprime a tabela em markdown + as correlações, pronto para colar no doc.

Install: pip install -r requirements.txt
Usage (de back/):
  python scripts/comparar_inpe.py
  python scripts/comparar_inpe.py --offline          # sem rede, usa o CSV agregado
  python scripts/comparar_inpe.py --anos 2003-2011
"""
import argparse
import io
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

HERE = Path(__file__).resolve().parent
BACK = HERE.parent

INPE_URL = ("https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/anual/"
            "Brasil_sat_ref/focos_br_ref_{year}.zip")
INPE_ENCODING = "latin-1"  # os CSVs do BDQueimadas não são UTF-8
BIOMA = "Pantanal"
# mesmo buffer que recortar_pantanal.py usou para montar a série
BUFFER_M = 2000
# SIRGAS 2000 / Brazil Polyconic: métrica e boa para o Brasil inteiro
PROJECTED_CRS = "EPSG:5880"
FIRST_YEAR, LAST_YEAR = 2003, 2025
TOP_N = 5


# ---------------------------------------------------------------- limite
def buffered_boundary(geojson_path: Path, meters: float = BUFFER_M) -> BaseGeometry:
    """Limite do Pantanal (IBGE 2019) com buffer, na pegada usada pela série."""
    import json

    gj = json.loads(geojson_path.read_text())
    geoms = [shape(feat["geometry"]) for feat in gj["features"]]
    boundary = shapely.union_all(geoms)
    if not meters:
        return boundary

    to_m = Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True)
    to_deg = Transformer.from_crs(PROJECTED_CRS, "EPSG:4326", always_xy=True)
    projected = shapely.transform(
        boundary, lambda xy: np.column_stack(to_m.transform(xy[:, 0], xy[:, 1])))
    return shapely.transform(
        projected.buffer(meters),
        lambda xy: np.column_stack(to_deg.transform(xy[:, 0], xy[:, 1])))


# ---------------------------------------------------------------- séries anuais
def annual_inpe(focos: pd.DataFrame, boundary: BaseGeometry) -> pd.DataFrame:
    """Focos do INPE por ano: os rotulados como Pantanal e os dentro do nosso limite.

    `focos` é um CSV do BDQueimadas como vem (campos com espaços sobrando).
    Indexado por ano, colunas focos_inpe e focos_no_nosso_limite.
    """
    df = pd.DataFrame({
        "year": pd.to_datetime(focos["data_pas"]).dt.year,
        "bioma": focos["bioma"].astype(str).str.strip(),
        "lat": pd.to_numeric(focos["lat"], errors="coerce"),
        "lon": pd.to_numeric(focos["lon"], errors="coerce"),
    }).dropna(subset=["lat", "lon"])

    shapely.prepare(boundary)
    inside = shapely.intersects(boundary, shapely.points(df.lon.to_numpy(), df.lat.to_numpy()))

    return pd.DataFrame({
        "focos_inpe": (df.bioma == BIOMA).groupby(df.year).sum(),
        "focos_no_nosso_limite": pd.Series(inside, index=df.index).groupby(df.year).sum(),
    }).astype("int64").rename_axis("year")


def annual_harmonized(cells_file: Path) -> pd.Series:
    """Soma anual de valor_harmonizado ("dias com fogo") da série harmonizada."""
    cells = pd.read_csv(cells_file, usecols=["data", "valor_harmonizado"])
    year = pd.to_datetime(cells["data"]).dt.year
    return (cells["valor_harmonizado"].groupby(year).sum()
            .rename("dias_com_fogo").rename_axis("year"))


# ---------------------------------------------------------------- rankings
def _ranks(values: pd.Series) -> pd.Series:
    """Posto 1 = pior ano (mais fogo). Empates ficam com o menor posto."""
    return values.rank(ascending=False, method="min").astype("int64")


def rankings_table(inpe: pd.Series, harmonized: pd.Series) -> pd.DataFrame:
    """Os dois rankings lado a lado, só com os anos presentes em ambos."""
    inpe, harmonized = inpe.astype("float64"), harmonized.astype("float64")
    years = inpe.index.intersection(harmonized.index).sort_values()
    inpe, harmonized = inpe.loc[years], harmonized.loc[years]

    table = pd.DataFrame({
        "focos_inpe": inpe.astype("int64"),
        "rank_inpe": _ranks(inpe),
        "dias_com_fogo": harmonized.round(0).astype("int64"),
        "rank_harmonizado": _ranks(harmonized),
    }, index=years.rename("ano"))
    table["delta_rank"] = table.rank_harmonizado - table.rank_inpe
    return table


# ---------------------------------------------------------------- correlações
def pearson(a: pd.Series, b: pd.Series) -> float:
    """Correlação linear entre os valores anuais."""
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if len(x) < 2 or x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def spearman(a: pd.Series, b: pd.Series) -> float:
    """Pearson sobre os postos: invariante a qualquer transformação monotônica.

    É a métrica principal porque focos e dias com fogo não estão na mesma unidade.
    Empates entram com posto médio (sem scipy no ambiente).
    """
    return pearson(pd.Series(np.asarray(a, dtype=float)).rank(),
                   pd.Series(np.asarray(b, dtype=float)).rank())


def kendall_tau(a: pd.Series, b: pd.Series) -> float:
    """Tau-b: pares de anos concordantes menos discordantes, normalizado."""
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    dx = np.sign(x[:, None] - x[None, :])
    dy = np.sign(y[:, None] - y[None, :])
    upper = np.triu(np.ones_like(dx, dtype=bool), k=1)
    concordant = float((dx * dy)[upper].sum())
    n_x = float((dx[upper] != 0).sum())
    n_y = float((dy[upper] != 0).sum())
    if n_x == 0 or n_y == 0:
        return float("nan")
    return concordant / np.sqrt(n_x * n_y)


def top_n_agreement(table: pd.DataFrame, n: int = TOP_N) -> int:
    """Quantos dos n piores anos do INPE também estão nos n piores da nossa série."""
    top_inpe = set(table.index[table.rank_inpe <= n])
    top_harmonized = set(table.index[table.rank_harmonizado <= n])
    return len(top_inpe & top_harmonized)


def correlations(table: pd.DataFrame) -> dict[str, float]:
    """As três correlações de um trecho da tabela, sobre focos x dias com fogo."""
    inpe, harmonized = table.focos_inpe, table.dias_com_fogo
    return {
        "pearson": pearson(inpe, harmonized),
        "spearman": spearman(inpe, harmonized),
        "kendall": kendall_tau(inpe, harmonized),
    }


# ---------------------------------------------------------------- download
def download(year: int, cache: Path) -> bytes:
    """Zip anual do INPE, do cache local ou da rede (o cache é ignorado pelo git)."""
    path = cache / f"focos_br_ref_{year}.zip"
    if path.exists():
        return path.read_bytes()

    url = INPE_URL.format(year=year)
    print(f"  {year}: baixando {url}")
    with urllib.request.urlopen(url, timeout=300) as response:
        data = response.read()
    cache.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def read_inpe_zip(data: bytes) -> pd.DataFrame:
    """CSV de dentro do zip anual, sem descompactar em disco."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    (name,) = [n for n in archive.namelist() if n.lower().endswith(".csv")]
    with archive.open(name) as fh:
        return pd.read_csv(fh, encoding=INPE_ENCODING, dtype=str,
                           usecols=["lat", "lon", "data_pas", "bioma"])


def inpe_series(years: range, cache: Path, boundary: BaseGeometry) -> pd.DataFrame:
    """Baixa e agrega os focos do INPE ano a ano (um zip por vez na memória)."""
    parts = []
    for year in years:
        counts = annual_inpe(read_inpe_zip(download(year, cache)), boundary)
        counts = counts.loc[counts.index == year]  # ignora linhas de borda de outro ano
        if counts.empty:
            sys.exit(f"Nenhum foco de {year} no arquivo do INPE desse ano.")
        print("  %d: %6d focos no bioma Pantanal, %6d no nosso limite"
              % (year, counts.focos_inpe.iloc[0], counts.focos_no_nosso_limite.iloc[0]))
        parts.append(counts)
    return pd.concat(parts).sort_index()


# ---------------------------------------------------------------- saída
def markdown_table(table: pd.DataFrame) -> str:
    """Tabela lado a lado em markdown, pronta para o doc de resultados."""
    header = ("| Ano | Focos INPE | Rank INPE | Focos no nosso limite | "
              "Dias com fogo | Rank harmonizado | Δ rank |")
    lines = [header, "|---:|---:|---:|---:|---:|---:|---:|"]
    for year, row in table.iterrows():
        lines.append("| %d | %s | %d | %s | %s | %d | %+d |" % (
            year, f"{row.focos_inpe:,}".replace(",", "."), row.rank_inpe,
            f"{row.focos_no_nosso_limite:,}".replace(",", "."),
            f"{row.dias_com_fogo:,}".replace(",", "."),
            row.rank_harmonizado, row.delta_rank))
    return "\n".join(lines)


def report(table: pd.DataFrame, periods: dict[str, pd.DataFrame]) -> str:
    """Correlações do período inteiro e dos sub-períodos, em markdown."""
    lines = ["| Período | Anos | Pearson (valores) | Spearman (postos) | Kendall tau |",
             "|---|---:|---:|---:|---:|"]
    for label, part in periods.items():
        c = correlations(part)
        lines.append("| %s | %d | %.3f | %.3f | %.3f |"
                     % (label, len(part), c["pearson"], c["spearman"], c["kendall"]))
    lines.append("")
    lines.append("Concordância dos %d piores anos: %d de %d."
                 % (TOP_N, top_n_agreement(table), TOP_N))
    return "\n".join(lines)


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--data", default=BACK / "data", type=Path)
    p.add_argument("--docs", default=BACK / "docs", type=Path)
    p.add_argument("--cache", default=None, type=Path, help="zips do INPE (default: <data>/inpe_raw)")
    p.add_argument("--anos", default=f"{FIRST_YEAR}-{LAST_YEAR}", help="ex.: 2003-2025")
    p.add_argument("--offline", action="store_true",
                   help="não usa a rede: lê inpe_pantanal_anual.csv já versionado")
    a = p.parse_args()

    # a tabela sai em markdown com "Δ rank"; o console do Windows é cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    first, last = (int(y) for y in a.anos.split("-"))
    years = range(first, last + 1)
    cache = a.cache or a.data / "inpe_raw"
    cells_file = a.data / "celulas_dia.csv.gz"
    boundary_file = a.data / "pantanal.geojson"
    inpe_file = a.data / "inpe_pantanal_anual.csv"
    for path in (cells_file, boundary_file):
        if not path.exists():
            sys.exit(f"Não encontrado: {path}")

    start = time.time()
    if a.offline:
        if not inpe_file.exists():
            sys.exit(f"Não encontrado: {inpe_file} (rode sem --offline uma vez)")
        print(f"Lendo os focos do INPE de {inpe_file.name} (offline)...")
        inpe = pd.read_csv(inpe_file).rename(columns={"ano": "year"}).set_index("year")
        inpe = inpe.loc[inpe.index.isin(years)]
    else:
        print(f"Focos do satélite de referência do INPE, {first}-{last}...")
        inpe = inpe_series(years, cache, buffered_boundary(boundary_file))

    print("Somando a série harmonizada por ano...")
    harmonized = annual_harmonized(cells_file)
    table = rankings_table(inpe.focos_inpe, harmonized)
    table["focos_no_nosso_limite"] = inpe.focos_no_nosso_limite
    table = table[["focos_inpe", "rank_inpe", "focos_no_nosso_limite",
                   "dias_com_fogo", "rank_harmonizado", "delta_rank"]]

    overlap = table.loc[table.index < 2012]
    viirs = table.loc[table.index >= 2012]
    periods = {f"{table.index.min()}-{table.index.max()} (tudo)": table}
    if len(overlap) >= 2:
        periods[f"{overlap.index.min()}-{overlap.index.max()} (MODIS-Aqua convertido)"] = overlap
    if len(viirs) >= 2:
        periods[f"{viirs.index.min()}-{viirs.index.max()} (VIIRS S-NPP observado)"] = viirs

    if not a.offline:
        inpe.rename_axis("ano").to_csv(inpe_file)
        print(f"Escrito {inpe_file}")
    a.docs.mkdir(parents=True, exist_ok=True)
    ranking_file = a.docs / "ranking_inpe_vs_harmonizado.csv"
    table.to_csv(ranking_file)
    print(f"Escrito {ranking_file}")

    print("\n" + markdown_table(table))
    print("\n" + report(table, periods))

    print("\n=== Check ===")
    print(f"  anos: {len(table)} ({table.index.min()}-{table.index.max()})")
    missing = sorted(set(years) - set(table.index))
    print(f"  anos faltando: {missing if missing else 'nenhum'}")
    print(f"  anos sem foco: {sorted(table.index[table.focos_inpe == 0]) or 'nenhum'}")
    worst_inpe = list(table.sort_values("rank_inpe").index[:TOP_N])
    worst_ours = list(table.sort_values("rank_harmonizado").index[:TOP_N])
    print(f"  {TOP_N} piores anos INPE:        {worst_inpe}")
    print(f"  {TOP_N} piores anos harmonizado: {worst_ours}")
    print(f"  maior divergência de posto: {int(table.delta_rank.abs().max())} "
          f"(ano {int(table.delta_rank.abs().idxmax())})")
    print(f"\nPronto em {time.time() - start:,.0f} s")


if __name__ == "__main__":
    main()
