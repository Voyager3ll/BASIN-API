"""BASIN HTTP API.

Run with:  uvicorn basin.api.main:app --reload
Docs at:   http://localhost:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query

from .. import __version__, hypoxia, scenario
from ..practices import CATALOG, Practice
from ..registry import Registry
from ..swat.dataset import SwatDataset

registry = Registry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not registry.datasets:
        registry.load()
    yield


app = FastAPI(
    title="BASIN API",
    version=__version__,
    description="SWAT-driven scenario analysis for basin-wide nutrient reduction in the UMRB.",
    lifespan=lifespan,
)


def _dataset(name: str) -> SwatDataset:
    try:
        return registry.get(name)
    except KeyError:
        raise HTTPException(404, f"dataset {name!r} not found") from None


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__, "datasets": list(registry.datasets)}


@app.get("/datasets")
def list_datasets():
    return [ds.summary() for ds in registry.datasets.values()]


@app.get("/datasets/{name}")
def get_dataset(name: str):
    return _dataset(name).summary()


@app.get("/practices", response_model=list[Practice])
def list_practices():
    return list(CATALOG.values())


@app.get("/datasets/{name}/baseline/{level}")
def baseline(name: str, level: Literal["hru", "subbasin", "county", "basin"]):
    """Baseline loads (no practices) at one spatial level."""
    res = scenario.run(_dataset(name), scenario.ScenarioRequest(name="baseline", levels=[level]))
    return res[level]


@app.get("/datasets/{name}/counties/{fips}")
def county(name: str, fips: str):
    rows = [c for c in baseline(name, "county") if c["county_fips"] == fips]
    if not rows:
        raise HTTPException(404, f"county {fips!r} not in dataset")
    return rows[0]


@app.get("/datasets/{name}/outlet/timeseries")
def outlet_timeseries(name: str, period: Literal["month", "year"] = Query("month")):
    ds = _dataset(name)
    r = ds.rch[(ds.rch["rch"] == ds.outlet_reach) & (ds.rch["period"] == period)]
    cols = ["year", "month", "flow_out_cms", "no3_out_kg", "orgn_out_kg", "orgp_out_kg", "minp_out_kg"]
    cols = [c for c in cols if c in r.columns and not (period == "year" and c == "month")]
    return r[cols].astype(object).where(r[cols].notna(), None).to_dict(orient="records")


@app.post("/datasets/{name}/scenarios")
def run_scenario(name: str, req: scenario.ScenarioRequest):
    try:
        return scenario.run(_dataset(name), req)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@app.get("/hypoxia/params", response_model=hypoxia.HypoxiaParams)
def hypoxia_params():
    return hypoxia.HypoxiaParams()
