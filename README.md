# brasa

**The fire history of the Brazilian Pantanal, in one click.**

Brasa is a web application that turns two decades of NASA satellite fire detections into a single, consistent fire-activity calendar. Draw an area on the map of the Brazilian Pantanal, pick a period, and get a dashboard with the fire history of that area since 2003: which months burn the most, which years were the worst, and how the latest month compares with the historical median.

Built for the **2026 NASA Space Apps Challenge**, challenge 15: _Harmonization of MODIS and VIIRS Hot Spots_.

**Links:** [GitHub organization](https://github.com/Brasa-Space-Apps) · [Front end](https://github.com/Brasa-Space-Apps/front) · [Live API](https://back-mrhi.onrender.com/docs) · Demo: `[ADD DEMO URL]`

> The API runs on a free hosting tier that sleeps after 15 minutes without use: the first request after a pause can take up to a minute.

---

## The problem

Satellites have been detecting active fires for more than twenty years, but the record is split between two sensors that cannot be compared directly:

|             | MODIS (Aqua)               | VIIRS (S-NPP)           |
| ----------- | -------------------------- | ----------------------- |
| Record      | 2002 →                     | 2012 →                  |
| Pixel size  | ~1 km                      | 375 m                   |
| Sensitivity | misses small or cool fires | detects many more fires |

Joining the two series naively creates a **false jump in 2012**: the number of detections rises because the sensor changed, not because more land burned. Fire managers are left without a consistent picture of when and where burning happens.

## Our approach

All the science happens **once, offline**, in a Python pipeline. The API only queries and sums data that is already harmonized, so each request is a lookup, not a recomputation.

1. **Clip** — NASA FIRMS hotspots are clipped to the Brazilian Pantanal (IBGE 2019 biome boundary, 2 km buffer).
2. **Filter** — vegetation fires only (`type = 0`); MODIS confidence ≥ 30; VIIRS confidence nominal or high.
3. **Reference satellites** — only **Aqua (MODIS)** and **S-NPP (VIIRS)**. Their daytime overpasses are only minutes apart (median 13:37 for Aqua and 13:29 for S-NPP, local time), so both see the afternoon fire peak under the same conditions. Terra, NOAA-20 and NOAA-21 are left out on purpose: mixing them would create new false jumps (e.g. in 2018).
4. **Common grid** — hotspots become **H3 resolution-7 cell-days** (~5 km² hexagons): _"did this hexagon have fire on this day?"_. A large fire that shows up as dozens of VIIRS pixels and a few MODIS pixels counts once for both. This alone cuts the VIIRS/MODIS gap from **7.2×** (pixels) to **2.7×** (cell-days) in 2020.
5. **Calibration (C1-day)** — during 2012–2021 both sensors were operating. For each calendar month we compute
   `R_m = Σ S-NPP cell-days (day + night) ÷ Σ Aqua cell-days (daytime only)`,
   calibrated on 2012–2018 + 2021. Months with fewer than 30 Aqua cell-days fall back to a seasonal factor.
6. **Harmonized series** — 2003–2011: each daytime Aqua cell-day is worth `R_m`; 2012 onward: each S-NPP cell-day is worth 1. The unit is **"fire days (per ~5 km² area)"**, in VIIRS-equivalent terms.

### Validation

We hid 2019 and 2020 from the calibration, predicted the S-NPP series from Aqua alone, and compared it with what S-NPP actually observed.

| Method                             | 2019 bias | 2020 bias | Mean \|bias\| | Mean NRMSE |
| ---------------------------------- | --------- | --------- | ------------- | ---------- |
| **C1-day (chosen)**                | +12.5%    | **−4.2%** | **8.4%**      | **0.18**   |
| C1 (day + night together)          | +15.5%    | +3.8%     | 9.7%          | 0.21       |
| C2 (log regression)                | +1.9%     | −18.6%    | 10.3%         | 0.19       |
| C1 with separate day/night factors | +37.7%    | +40.9%    | 39.3%         | 0.68       |

- Monthly correlation ≥ 0.99 and the peak month is right for every method in the test years.
- **Saturation is real**: the VIIRS/MODIS ratio drops in big fire years (correlation −0.79 between fire volume and ratio).
- Separate day/night factors were discarded: MODIS sees too little fire at night for a stable factor.
- After 2022 Aqua's orbit drifts, so those years are not used for calibration. They do not affect the series, which uses observed S-NPP from 2012 on.
- **Year ranking matches INPE's.** Against the annual hotspot counts of INPE's reference satellite in the Pantanal (BDQueimadas, 2003–2025): Spearman 0.981, Kendall 0.905, the same five worst years, no year more than three positions apart. Details in [`docs/resultados.md`](docs/resultados.md).

**Monthly factors (H3 res 7):** Jan 3.52 · Feb 4.67 · Mar 4.19 · Apr 4.29 · May 3.93 · Jun 3.48 · Jul 2.69 · Aug 2.61 · Sep 2.90 · Oct 3.39 · Nov 4.10 · Dec 4.05

**Result:** a single series from 2003 to 2025 (231,014 cell-days) with no step in 2012. In the overlap years, converted MODIS tracks observed VIIRS year by year.

## What the app shows

- **Indicators** — total fire days, annual mean, worst year, peak month and typical peak month.
- **Burning calendar** — year × month heatmap.
- **Anomalies** — each month against the historical median of the same month (ratio and percentile), including the latest month in the data.
- **Density map** — fire days per hexagon inside the drawn area.
- **CSV export** — the original FIRMS hotspots of the area and period, each with the harmonization factor applied to its cell-day.

---

## Architecture

```
NASA FIRMS (CSV)          IBGE biome boundary
        │                         │
        └──── pipeline (Python, offline) ────┐
              clip · filter · H3 · C1-day     │
                                              ▼
                                   PostGIS (cell_days, raw_hotspots,
                                            pantanal_boundary, factors)
                                              │
                                     FastAPI (/meta /stats /density /export)
                                              │
                                     Next.js front-end (map + dashboard)
```

**Stack:** Python 3.12 · pandas · GeoPandas · h3-py 4 · shapely · pyproj · PostgreSQL + PostGIS (Docker locally, Neon in production) · FastAPI + Pydantic v2 · psycopg 3 · pytest · Docker · Next.js + TypeScript · MapLibre GL · ECharts.

### API

| Endpoint        | Input                                | Output                                                              |
| --------------- | ------------------------------------ | ------------------------------------------------------------------- |
| `GET /meta`     | —                                    | period, data cutoff, unit, Pantanal boundary, factors               |
| `POST /stats`   | `{ geometry, start_date, end_date }` | area, period, indicators, calendar, anomalies, last month, warnings |
| `POST /density` | same                                 | GeoJSON FeatureCollection of H3 hexagons with fire days             |
| `POST /export`  | same                                 | CSV of the original hotspots                                        |

Interactive documentation at `/docs` when the API is running, and live at https://back-mrhi.onrender.com/docs.

### Repository layout (back-end)

```
back/
├── app/
│   ├── main.py            # app, CORS, startup cache (boundary, period, factors)
│   ├── config.py          # settings from .env
│   ├── db.py              # connection pool
│   ├── queries.py         # all SQL
│   ├── schemas.py         # API contract (Pydantic)
│   ├── services/
│   │   ├── geometry.py    # validate, clip to the Pantanal, polygon → H3 cells, km²
│   │   └── stats.py       # zero-filled grid, medians, percentiles, indicators
│   └── routers/           # meta, stats, density, export
├── scripts/
│   ├── schema.sql
│   ├── load_postgis.py
│   └── comparar_inpe.py   # year ranking vs INPE's reference satellite (BDQueimadas)
├── data/                  # processed data loaded into PostGIS
├── docs/                  # results doc (validations run on the real data)
├── tests/                 # test_geometry, test_stats, test_routes, test_comparacao
└── docker-compose.yml
```

---

## Running locally

```bash
# 1. database
docker compose up -d

# 2. Python environment
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 3. load the processed data
python scripts/load_postgis.py

# 4. API
uvicorn app.main:app --reload        # http://localhost:8000/docs

# 5. tests
pytest -v
```

The route tests run against the local database; if it is not reachable they are skipped.

### Deployment

- **Database:** Neon (PostgreSQL + PostGIS). Load it with `python scripts/load_postgis.py --database-url "<neon url>"`.
- **API:** Render web service. Build: `pip install -r requirements.lock.txt`. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Environment: `DATABASE_URL`, `FRONT_ORIGIN` (comma-separated list of allowed front-end origins), `PYTHON_VERSION=3.12.3`. Health check: `/health`.
- Never commit connection strings: keep them in `.env` (ignored by git) or in the host's environment settings.

### Regenerating the data (optional)

The `pipeline/` scripts rebuild everything from the raw FIRMS files:

```bash
cd pipeline
python recortar_pantanal.py --entrada <firms_folder> --saida dados/pantanal --limite Biomas_250mil.zip
python explorar_pantanal.py --dados dados/pantanal --saida saida
python validar_harmonizacao.py --mensal saida/razoes_mensais_por_ano.csv --saida saida
python aplicar_harmonizacao.py --dados dados/pantanal --saida saida
```

---

## Limitations and next steps

- **Data cutoff: 31 Dec 2025.** S-NPP data ends on 2 Nov 2026. Extending the series means calibrating NOAA-20 against S-NPP over their overlap (2018 →), with the same C1-day method.
- **Small areas** (< ~500 km²) carry more uncertainty before 2012; the API returns a warning. The threshold is provisional.
- **Fire days, not burned area.** Converting to km² burned (MCD64A1 / VNP64A1 + MapBiomas Fogo) is a natural next step, but out of scope for this weekend.
- **Not comparable to INPE hotspot counts in absolute terms.** Brasa counts harmonized cell-days, not hotspots; only the year ranking is compared (see Validation).

---

## Data sources

- **NASA FIRMS** — MODIS Collection 6.1 (Aqua) and VIIRS 375 m (S-NPP) active fire archives. https://firms.modaps.eosdis.nasa.gov
- **IBGE** — _Biomas e Sistema Costeiro-Marinho do Brasil_, 1:250,000 (2019). https://www.ibge.gov.br/geociencias/
- **INPE / Programa Queimadas (BDQueimadas)** — annual hotspots of the reference satellite, used to
  cross-check the year ranking. https://terrabrasilis.dpi.inpe.br/queimadas/portal/
- **H3** — Uber's hexagonal hierarchical spatial index. https://h3geo.org

---

## Use of AI (Super Intelligence)

This project was developed with the assistance of AI tools, as allowed by the NASA Space Apps rules. We list where and how they were used.

**Tool:** Claude (Anthropic), used as a chat assistant and as a coding assistant.

| Part                   | How AI was used                                                                                                                                                                       | Human role                                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Research               | Finding data sources (FIRMS, IBGE, INPE), summarizing harmonization approaches, checking hosting options                                                                              | The team chose the approach and checked the sources                                                     |
| Method                 | Comparing harmonization techniques and proposing the validation design                                                                                                                | The team decided on A + B + C1; the C1-day variant was chosen because it won the validation on our data |
| `pipeline/`            | Code generated by AI from the method defined by the team                                                                                                                              | Run by the team on the real data; results checked against expected behaviour                            |
| `app/` (API)           | Skeleton, routes, SQL queries and schemas generated by AI                                                                                                                             | Reviewed, adapted and integrated by the team                                                            |
| `app/services/`        | Written by the team with AI assistance                                                                                                                                                | Unit tests written and checked by the team                                                              |
| `tests/`               | Partly generated by AI, partly written by the team                                                                                                                                    | All tests pass against the real database                                                                |
| Docs, logo and figures | Drafts of requirements, guides and this README; the Brasa logo and the explanatory figures (validation chart, monthly factors, cell-day schematic, architecture) were drafted with AI | Edited by the team. Logo and figures are marked as AI-generated wherever they appear                    |

Files generated or substantially assisted by AI carry a header comment:

```python
# AI-assisted: generated with Claude (Anthropic) and reviewed by the Brasa team.
```

The data, the numbers in this README and the validation results come from running the code on the real NASA FIRMS data, not from the AI.

---

## Team

`[ADD NAMES AND ROLES]`

## License

`[ADD LICENSE, e.g. MIT]`
