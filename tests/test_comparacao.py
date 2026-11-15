# AI-assisted: generated with Claude (Anthropic) and reviewed by the Brasa team.
"""Tests for scripts/comparar_inpe.py (Issue 14).

Hand-made series only, small enough to check by hand. No network, no database,
no real data files. The quantities under test are rankings and correlations.
"""
import io

import pandas as pd
import pytest
from shapely.geometry import Polygon

from scripts.comparar_inpe import (
    annual_harmonized,
    annual_inpe,
    correlations,
    kendall_tau,
    markdown_table,
    pearson,
    rankings_table,
    spearman,
    top_n_agreement,
)

# --------------------------------------------------------------- séries à mão
# Cinco anos. O INPE e a nossa série concordam na ordem, em unidades diferentes:
#   2020 (1o) > 2019 (2o) > 2021 (3o) > 2018 (4o) > 2022 (5o)
INPE_SAME = pd.Series({2018: 200, 2019: 800, 2020: 1000, 2021: 400, 2022: 100}, name="focos_inpe")
OURS_SAME = pd.Series({2018: 1.5, 2019: 6.0, 2020: 7.5, 2021: 3.0, 2022: 0.5}, name="dias_com_fogo")

# Mesma série, com 2019 e 2021 trocados de lugar (uma inversão de pares).
OURS_SWAPPED = pd.Series({2018: 1.5, 2019: 3.0, 2020: 7.5, 2021: 6.0, 2022: 0.5})


def series(values: dict) -> pd.Series:
    return pd.Series(values).rename_axis("year")


# --------------------------------------------------------------- rankings
def test_rankings_table_ranks_the_worst_year_first():
    table = rankings_table(INPE_SAME, OURS_SAME)

    assert list(table.index) == [2018, 2019, 2020, 2021, 2022]
    assert table.index.name == "ano"
    assert table.loc[2020, "rank_inpe"] == 1
    assert table.loc[2020, "rank_harmonizado"] == 1
    assert table.loc[2022, "rank_inpe"] == 5
    assert list(table.rank_inpe) == [4, 2, 1, 3, 5]


def test_rankings_table_delta_is_zero_when_the_order_matches():
    table = rankings_table(INPE_SAME, OURS_SAME)

    assert (table.delta_rank == 0).all()


def test_rankings_table_delta_shows_the_swapped_years():
    table = rankings_table(INPE_SAME, OURS_SWAPPED)

    assert table.loc[2019, "delta_rank"] == 1  # era 2o no INPE, 3o no nosso
    assert table.loc[2021, "delta_rank"] == -1  # era 3o no INPE, 2o no nosso
    assert list(table.delta_rank[[2018, 2020, 2022]]) == [0, 0, 0]


def test_rankings_table_ties_share_the_lowest_rank():
    tied = series({2020: 10, 2021: 10, 2022: 1})
    table = rankings_table(tied, series({2020: 2.0, 2021: 1.0, 2022: 0.5}))

    assert list(table.rank_inpe) == [1, 1, 3]
    assert list(table.rank_harmonizado) == [1, 2, 3]


def test_rankings_table_keeps_only_the_years_present_in_both():
    table = rankings_table(series({2019: 5, 2020: 10, 2021: 1}),
                           series({2020: 2.0, 2021: 1.0, 2099: 9.0}))

    assert list(table.index) == [2020, 2021]


def test_rankings_table_rounds_the_harmonized_value():
    table = rankings_table(series({2020: 10}), series({2020: 7.6}))

    assert table.loc[2020, "dias_com_fogo"] == 8


# --------------------------------------------------------------- correlações
def test_perfect_agreement_is_one():
    assert pearson(INPE_SAME, INPE_SAME) == pytest.approx(1.0)
    assert spearman(INPE_SAME, OURS_SAME) == pytest.approx(1.0)
    assert kendall_tau(INPE_SAME, OURS_SAME) == pytest.approx(1.0)


def test_reversed_order_is_minus_one():
    reversed_values = series({2018: 1000, 2019: 400, 2020: 200, 2021: 800, 2022: 2000})

    assert spearman(INPE_SAME, reversed_values) == pytest.approx(-1.0)
    assert kendall_tau(INPE_SAME, reversed_values) == pytest.approx(-1.0)


def test_one_neighbour_swap_in_five_years():
    # 10 pares, 1 discordante: Kendall = (9 - 1) / 10 = 0.8
    # Spearman com postos diferindo de 1 em dois anos: 1 - 6*2/(5*24) = 0.9
    assert kendall_tau(INPE_SAME, OURS_SWAPPED) == pytest.approx(0.8)
    assert spearman(INPE_SAME, OURS_SWAPPED) == pytest.approx(0.9)


def test_spearman_ignores_the_unit_but_pearson_does_not():
    # a nossa unidade é "dias com fogo", a do INPE é "focos": só a ordem é comparável
    squashed = OURS_SAME**5

    assert spearman(INPE_SAME, squashed) == pytest.approx(1.0)
    assert kendall_tau(INPE_SAME, squashed) == pytest.approx(1.0)
    assert pearson(INPE_SAME, squashed) < 0.9


def test_correlations_survive_ties_and_short_series():
    flat = series({2020: 5, 2021: 5, 2022: 5})
    varied = series({2020: 1.0, 2021: 2.0, 2022: 3.0})

    assert pd.isna(pearson(flat, varied))
    assert pd.isna(kendall_tau(flat, varied))
    assert pd.isna(spearman(flat, varied))


def test_correlations_reads_the_table_columns():
    result = correlations(rankings_table(INPE_SAME, OURS_SAME))

    assert set(result) == {"pearson", "spearman", "kendall"}
    assert result["spearman"] == pytest.approx(1.0)


# --------------------------------------------------------------- top N
def test_top_n_agreement_counts_the_shared_worst_years():
    table = rankings_table(INPE_SAME, OURS_SAME)

    assert top_n_agreement(table, 5) == 5
    assert top_n_agreement(table, 3) == 3  # 2020, 2019, 2021 nos dois
    assert top_n_agreement(table, 1) == 1


def test_top_n_agreement_drops_a_year_that_leaves_the_top():
    # 2021 sobe para 1o lugar no nosso lado e 2020 cai para fora do top 2
    ours = series({2018: 1.5, 2019: 6.0, 2020: 0.1, 2021: 9.0, 2022: 0.5})
    table = rankings_table(INPE_SAME, ours)

    assert top_n_agreement(table, 2) == 1  # só 2019 está no top 2 dos dois


# --------------------------------------------------------------- entradas
# Quadrado de 1 grau em volta de Corumbá, no lugar do limite do Pantanal.
BOUNDARY = Polygon([(-58.0, -20.0), (-57.0, -20.0), (-57.0, -19.0), (-58.0, -19.0)])

# CSV do BDQueimadas como ele vem: espaços sobrando e campos em latin-1.
INPE_CSV = """id_bdq,foco_id,lat,lon,data_pas,pais,estado,municipio,bioma
 1 , a ,  -19.5000 ,  -57.5000 ,2013-08-01 17:00:00,Brasil,MATO GROSSO DO SUL,CORUMBA, Pantanal
 2 , b ,  -19.6000 ,  -57.6000 ,2013-08-02 17:00:00,Brasil,MATO GROSSO DO SUL,CORUMBA,Pantanal
 3 , c ,  -19.7000 ,  -57.7000 ,2013-09-01 17:00:00,Brasil,MATO GROSSO DO SUL,CORUMBA,Cerrado
 4 , d ,  -13.0000 ,  -46.0000 ,2013-10-06 17:28:00,Brasil,GOIAS,NOVA ROMA,Cerrado
 5 , e ,  -20.5000 ,  -57.5000 ,2013-08-03 17:00:00,Brasil,MATO GROSSO DO SUL,AQUIDAUANA,Pantanal
"""


def read_inpe_csv(text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(text), dtype=str)


def test_annual_inpe_counts_the_biome_label_and_our_clip_independently():
    counts = annual_inpe(read_inpe_csv(INPE_CSV), BOUNDARY)

    # focos 1, 2 e 5 têm bioma Pantanal (o 1 com espaços em volta)
    assert counts.loc[2013, "focos_inpe"] == 3
    # dentro do quadrado: 1, 2 e 3 (o 3 é Cerrado para o INPE, o 5 cai ao sul)
    assert counts.loc[2013, "focos_no_nosso_limite"] == 3
    assert list(counts.index) == [2013]
    assert counts.index.name == "year"


def test_annual_inpe_splits_by_year():
    rows = INPE_CSV.replace("2013-09-01", "2014-09-01")
    counts = annual_inpe(read_inpe_csv(rows), BOUNDARY)

    assert list(counts.index) == [2013, 2014]
    assert counts.loc[2014, "focos_inpe"] == 0
    assert counts.loc[2014, "focos_no_nosso_limite"] == 1


def test_annual_inpe_drops_rows_without_coordinates():
    rows = INPE_CSV.replace(" 2 , b ,  -19.6000 ,  -57.6000 ", " 2 , b ,   ,   ")
    counts = annual_inpe(read_inpe_csv(rows), BOUNDARY)

    assert counts.loc[2013, "focos_inpe"] == 2
    assert counts.loc[2013, "focos_no_nosso_limite"] == 2


def test_annual_harmonized_sums_the_value_by_year(tmp_path):
    cells = tmp_path / "celulas_dia.csv.gz"
    pd.DataFrame({
        "celula": ["87a8400c1ffffff"] * 4,
        "data": ["2003-01-01", "2003-08-15", "2004-09-01", "2004-09-02"],
        "valor_harmonizado": [3.5, 2.5, 1.0, 2.0],
    }).to_csv(cells, index=False)

    annual = annual_harmonized(cells)

    assert annual.loc[2003] == pytest.approx(6.0)
    assert annual.loc[2004] == pytest.approx(3.0)
    assert annual.name == "dias_com_fogo"


# --------------------------------------------------------------- saída
def test_markdown_table_has_a_row_per_year():
    lines = markdown_table(
        rankings_table(INPE_SAME, OURS_SAME).assign(focos_no_nosso_limite=0)).splitlines()

    assert lines[0].startswith("| Ano |")
    assert len(lines) == 2 + 5  # cabeçalho + separador + 5 anos
    assert "| 2020 |" in lines[4]
