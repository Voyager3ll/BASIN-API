from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from basin.api.main import app, registry
from basin.swat.parsers import read_output_hru, read_output_rch

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_parse_periods():
    hru = read_output_hru(SAMPLE / "output.hru")
    assert set(hru["period"]) == {"month", "year", "average"}
    months = hru[hru["period"] == "month"]
    assert months["year"].min() == 2015 and months["month"].max() == 12
    rch = read_output_rch(SAMPLE / "output.rch")
    # Average rows carry MON = 5.0 (years simulated) and must not be read as May.
    assert (rch[(rch["period"] == "month") & (rch["month"] == 5)]["year"].notna()).all()


def test_monthly_sums_match_annual():
    rch = read_output_rch(SAMPLE / "output.rch")
    out = rch[rch["rch"] == 12]
    m = out[out["period"] == "month"].groupby("year")["no3_out_kg"].sum()
    y = out[out["period"] == "year"].set_index("year")["no3_out_kg"]
    assert (abs(m - y) / y < 1e-3).all()


def test_datasets(client):
    ds = client.get("/datasets").json()
    assert ds[0]["name"] == "sample" and ds[0]["n_hru"] == 60 and ds[0]["synthetic"]


def test_baseline_levels_consistent(client):
    basin = client.get("/datasets/sample/baseline/basin").json()
    counties = client.get("/datasets/sample/baseline/county").json()
    subs = client.get("/datasets/sample/baseline/subbasin").json()
    total = basin["baseline_tn_kg"]
    assert sum(c["baseline_tn_kg"] for c in counties) == pytest.approx(total, rel=1e-6)
    assert sum(s["baseline_tn_kg"] for s in subs) == pytest.approx(total, rel=1e-6)
    assert basin["tn_reduction_pct"] == 0


def test_scenario_reduces_loads(client):
    req = {"name": "cc50", "practices": [{"practice": "cover_crop", "adoption": 0.5}]}
    res = client.post("/datasets/sample/scenarios", json=req).json()
    assert 0 < res["basin"]["tn_reduction_pct"] < 31 * 0.5 + 1e-9
    assert res["outlet"]["scenario_tn_kg"] < res["outlet"]["baseline_tn_kg"]
    assert res["hypoxia"]["scenario_area_km2"] < res["hypoxia"]["baseline_area_km2"]
    assert res["cost"]["usd_per_kg_tn_delivered"] > 0


def test_county_targeting_only_touches_that_county(client):
    req = {"practices": [{"practice": "wetland", "adoption": 1.0, "where": {"counties": ["27001"]}}],
           "levels": ["county"]}
    res = client.post("/datasets/sample/scenarios", json=req).json()
    by = {c["county_fips"]: c["tn_reduction_pct"] for c in res["county"]}
    assert by["27001"] > 0
    assert all(v == 0 for k, v in by.items() if k != "27001")


def test_unknown_practice(client):
    r = client.post("/datasets/sample/scenarios", json={"practices": [{"practice": "nope", "adoption": 0.1}]})
    assert r.status_code == 422


def test_outlet_timeseries(client):
    ts = client.get("/datasets/sample/outlet/timeseries?period=month").json()
    assert len(ts) == 60 and ts[4]["month"] == 5
