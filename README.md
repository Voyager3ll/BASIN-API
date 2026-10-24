# BASIN API (prototype)

**B**asin-wide **A**nalysis for **S**tewardship & **I**ntegrated **N**utrient management.

A SWAT-driven API for scenario analysis of on-farm conservation practices in the
Upper Mississippi River Basin (UMRB), aggregating from field (HRU) to subbasin,
county, and basin scale, with a first-order Gulf hypoxia response. It is a
separate codebase from DAWN; see [docs/DESIGN.md](docs/DESIGN.md).

> The bundled `data/sample` dataset is **synthetic**. Practice efficiencies,
> costs, and hypoxia parameters are placeholders to be replaced during refinement.

## Quick start

```bash
pip install -e ".[dev]"
python scripts/make_sample_data.py      # regenerate synthetic sample (already committed)
pytest
uvicorn basin.api.main:app --reload     # docs at http://localhost:8000/docs
```

Point at real SWAT runs with `BASIN_DATA_DIR=/path/to/datasets`; every
subdirectory with a `dataset.json` is loaded.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Status and loaded datasets |
| GET | `/datasets`, `/datasets/{name}` | Dataset summaries, outlet loads |
| GET | `/practices` | Practice catalog (efficiencies, eligibility, cost) |
| GET | `/datasets/{name}/baseline/{hru\|subbasin\|county\|basin}` | Baseline TN/TP loads |
| GET | `/datasets/{name}/counties/{fips}` | One county's baseline |
| GET | `/datasets/{name}/outlet/timeseries?period=month\|year` | Outlet reach series |
| POST | `/datasets/{name}/scenarios` | Run a practice scenario |
| GET | `/hypoxia/params` | Default hypoxia model parameters |

Example scenario:

```bash
curl -X POST localhost:8000/datasets/sample/scenarios -H 'content-type: application/json' -d '{
  "name": "cover crops + MRTN + targeted wetlands",
  "levels": ["county", "basin"],
  "practices": [
    {"practice": "cover_crop", "adoption": 0.4},
    {"practice": "n_rate_mrtn", "adoption": 0.8},
    {"practice": "wetland", "adoption": 0.2, "where": {"counties": ["19001", "19003"]}}
  ]
}'
```

The response has loads by level (baseline, scenario, % reduction, yields,
treated practice-hectares, cost), delivered load at the basin outlet, hypoxic
area estimate and progress to the Hypoxia Task Force 45% goal, and cost per kg
of delivered TN reduced.

## Layout

```
basin/
  swat/parsers.py   SWAT2012 output.hru / output.sub / output.rch readers
  swat/dataset.py   one SWAT run + crosswalks, average-annual and outlet loads
  practices.py      practice catalog
  scenario.py       practice application and field -> basin aggregation
  hypoxia.py        Gulf hypoxia response
  registry.py       loads datasets from BASIN_DATA_DIR
  api/main.py       FastAPI app
scripts/make_sample_data.py
data/sample/        synthetic SWAT2012 run (12 subbasins, 60 HRUs, 6 counties)
```
