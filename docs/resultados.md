# Brasa — doc de resultados

Resultados das validações da série harmonizada MODIS × VIIRS do Pantanal brasileiro.
Os números aqui vêm de rodar o código sobre o dado real, não de estimativa.

Índice:

- [1. Ranking dos anos: nossa série × INPE (BDQueimadas)](#1-ranking-dos-anos-nossa-série--inpe-bdqueimadas)

---

## 1. Ranking dos anos: nossa série × INPE (BDQueimadas)

*Issue 14. Rodado em 15/11/2026 com `scripts/comparar_inpe.py`.*

### Pergunta

A série harmonizada ordena os anos por fogo e o app mostra essa ordem como indicador ("pior ano").
Essa ordem se sustenta contra uma fonte externa e independente?

### Fontes e método

| | Lado INPE | Lado Brasa |
|---|---|---|
| Dado | focos do **satélite de referência** (Aqua, passagem da tarde) | série harmonizada C1-dia |
| Origem | BDQueimadas, `focos_br_ref_<ANO>.zip` do [dataserver do INPE](https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/anual/Brasil_sat_ref/) | `data/celulas_dia.csv.gz` (o mesmo que vai para `cell_days`) |
| Recorte | `bioma = 'Pantanal'` do próprio INPE | Pantanal do IBGE 2019 + buffer de 2 km |
| Unidade | focos (pixels) | dias com fogo por célula H3 res 7 (~5 km²), em equivalente-VIIRS |
| Filtros | nenhum (todas as confianças, todos os tipos) | `type = 0`, MODIS confiança ≥ 30, VIIRS nominal/alta |
| Período | 2003–2025 | 2003–2025 |

As duas unidades não são comparáveis em nível: um incêndio grande são dezenas de focos e um punhado de
dias com fogo. A comparação que interessa é de **ordem** — por isso a métrica principal é Spearman/Kendall
sobre os postos, e Pearson entra só como informação extra.

A coluna **focos no nosso limite** são os mesmos focos do INPE recortados pelo nosso polígono (IBGE + 2 km),
e serve para separar *diferença de fronteira* de *diferença de método*.

### Tabela dos dois rankings

Posto 1 = ano com mais fogo. CSV completo em [`ranking_inpe_vs_harmonizado.csv`](ranking_inpe_vs_harmonizado.csv).

| Ano | Focos INPE | Rank INPE | Focos no nosso limite | Dias com fogo | Rank harmonizado | Δ rank |
|---:|---:|---:|---:|---:|---:|---:|
| 2003 | 3.722 | 16 | 3.693 | 8.941 | 18 | +2 |
| 2004 | 8.688 | 6 | 8.675 | 19.408 | 6 | 0 |
| 2005 | 12.536 | 3 | 13.537 | 26.190 | 2 | −1 |
| 2006 | 3.173 | 19 | 3.422 | 7.670 | 19 | 0 |
| 2007 | 9.869 | 5 | 10.556 | 21.275 | 4 | −1 |
| 2008 | 4.545 | 14 | 5.021 | 11.292 | 14 | 0 |
| 2009 | 5.737 | 12 | 5.798 | 13.826 | 9 | −3 |
| 2010 | 8.020 | 8 | 8.695 | 18.318 | 7 | −1 |
| 2011 | 3.532 | 17 | 3.942 | 9.249 | 16 | −1 |
| 2012 | 7.447 | 9 | 7.550 | 13.524 | 10 | +1 |
| 2013 | 3.396 | 18 | 3.641 | 9.060 | 17 | −1 |
| 2014 | 1.567 | 22 | 1.640 | 4.403 | 21 | −1 |
| 2015 | 4.458 | 15 | 4.555 | 10.211 | 15 | 0 |
| 2016 | 5.184 | 13 | 5.749 | 13.101 | 11 | −2 |
| 2017 | 5.773 | 11 | 5.911 | 12.176 | 12 | +1 |
| 2018 | 1.691 | 20 | 1.837 | 4.692 | 20 | 0 |
| 2019 | 10.025 | 4 | 10.750 | 20.006 | 5 | +1 |
| 2020 | 22.116 | 1 | 22.673 | 43.386 | 1 | 0 |
| 2021 | 8.258 | 7 | 8.958 | 15.441 | 8 | +1 |
| 2022 | 1.637 | 21 | 1.681 | 4.238 | 22 | +1 |
| 2023 | 6.580 | 10 | 6.842 | 12.032 | 13 | +3 |
| 2024 | 14.498 | 2 | 15.180 | 23.186 | 3 | +1 |
| 2025 | 724 | 23 | 774 | 1.721 | 23 | 0 |

### Correlação

| Período | Anos | Pearson (valores) | Spearman (postos) | Kendall tau |
|---|---:|---:|---:|---:|
| **2003–2025 (tudo)** | 23 | **0,984** | **0,981** | **0,905** |
| 2003–2011 (nosso lado é MODIS-Aqua convertido) | 9 | 0,998 | 0,983 | 0,944 |
| 2012–2025 (nosso lado é VIIRS S-NPP observado) | 14 | 0,987 | 0,978 | 0,912 |

- **Concordância dos 5 piores anos: 5 de 5** — INPE: 2020, 2024, 2005, 2019, 2007; nossa série: 2020, 2005,
  2024, 2007, 2019. Mesmo conjunto, com trocas de posição dentro do grupo.
- **2020 é o pior ano e 2025 o melhor nos dois rankings**, sem empate nem ambiguidade.
- **Maior divergência: 3 posições** (2009 e 2023). Nenhum ano se desloca mais do que isso em 23.
- Usando a coluna "focos no nosso limite" em vez da coluna do INPE, as correlações praticamente não mudam
  (Pearson 0,983 · Spearman 0,980 · Kendall 0,897).

### Leitura dos resultados

**A ordem dos anos se sustenta.** O período que de fato testa a harmonização é 2012–2025, onde o nosso lado
é VIIRS observado e o do INPE segue sendo Aqua: ali o Spearman é 0,978. O trecho 2003–2011, onde os dois
lados nascem do mesmo sensor, funciona como piso de sanidade (0,983) e mostra que a conversão por `R_m` e a
agregação em dias-com-fogo não reordenam os anos.

**De onde vêm as divergências que sobraram:**

1. **Fronteira (IBGE × INPE).** O nosso limite pega em média **5,5% mais** focos que o rótulo `bioma` do INPE
   (de −0,8% em 2003 a +11,6% em 2011). É só fronteira: entre as duas contagens do INPE o Spearman é 0,996.
2. **Meio do ranking é apertado.** 2009 (13.826), 2012 (13.524), 2016 (13.101), 2017 (12.176) e 2023 (12.032)
   estão todos a menos de 13% um do outro, e é aí que estão todos os Δ de 2 e 3 posições. Nos extremos —
   os anos que o app chama de "pior ano" — os dois rankings coincidem.
3. **Saturação do MODIS nos anos grandes**, já documentada no README. A razão dias-com-fogo ÷ focos-INPE cai
   justamente nos anos de muito fogo (2024: 1,60 · 2021: 1,87 · 2020: 1,96) e sobe nos anos fracos
   (2014: 2,81 · 2018: 2,77). Isso explica as trocas dentro do top 5: 2005 e 2007 (MODIS convertido, sem
   saturação na contagem de focos do INPE) sobem uma posição contra 2024 e 2019.
4. **Filtros diferentes.** O INPE conta todos os focos do satélite de referência; nós descartamos
   `type ≠ 0` (vulcões, área urbana, offshore) e confiança baixa. Isso muda o nível, não a ordem.

**Limites desta validação.** Os dois lados compartilham o sensor MODIS-Aqua antes de 2012, então a
independência real só existe de 2012 em diante. E o INPE publica focos, não dias com fogo: a comparação é de
ranking, não de magnitude — para magnitude, a referência continua sendo a validação de 2019/2020 do README.

### Como reproduzir

```bash
# baixa os 23 zips anuais do INPE (~130 MB, cacheados em data/inpe_raw/, ignorado pelo git)
python scripts/comparar_inpe.py

# mesma tabela sem rede, a partir de data/inpe_pantanal_anual.csv (versionado)
python scripts/comparar_inpe.py --offline

# testes das funções de ranking e correlação
pytest tests/test_comparacao.py -v
```

Conferências feitas na rodada de 15/11/2026: 23 anos sem buraco e sem ano zerado; 2013 com 3.396 focos no
bioma Pantanal e 3.641 dentro do nosso limite; a coluna de dias com fogo bate com
`SELECT EXTRACT(YEAR FROM date), round(sum(harmonized_value)) FROM cell_days GROUP BY 1` do PostGIS
(diferença máxima de 1 unidade, arredondamento do tipo `REAL`).
