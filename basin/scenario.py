"""Scenario engine: apply practices to HRUs and aggregate field -> basin.

HRUs are the field-scale unit. Each HRU is split across counties by the
subbasin-county area fractions, giving "units" (hru x county) so a practice
targeted at a county only touches that county's share of a subbasin.

Practices stack multiplicatively on the remaining load:

    factor = prod(1 - adoption_i * eff_i)

Edge-of-field reductions reach the basin outlet through each subbasin's
delivery ratio. The May NO3+NO2 flux at the outlet is assumed to change by the
same fraction as delivered TN, which is a prototype simplification.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from . import hypoxia
from .hypoxia import HypoxiaParams
from .practices import CATALOG
from .swat.dataset import SwatDataset

Level = Literal["hru", "subbasin", "county", "basin"]


class Targeting(BaseModel):
    counties: list[str] | None = Field(None, description="County FIPS codes")
    subbasins: list[int] | None = None
    lulc: list[str] | None = Field(None, description="Restrict below the practice's eligible land uses")


class PracticeApplication(BaseModel):
    practice: str
    adoption: float = Field(..., ge=0.0, le=1.0, description="Share of eligible area adopting")
    where: Targeting = Targeting()


class ScenarioRequest(BaseModel):
    name: str = "scenario"
    practices: list[PracticeApplication] = []
    levels: list[Level] = ["subbasin", "county", "basin"]
    hypoxia: HypoxiaParams = HypoxiaParams()


def units(ds: SwatDataset) -> pd.DataFrame:
    u = ds.hru[["hru", "sub", "lulc", "area_ha", "tn_kg", "tp_kg"]].merge(
        ds.sub_county, on="sub", how="left"
    )
    for col in ["area_ha", "tn_kg", "tp_kg"]:
        u[col] = u[col] * u["area_fraction"]
    return u.merge(ds.delivery, on="sub", how="left")


def run(ds: SwatDataset, req: ScenarioRequest) -> dict:
    for app in req.practices:
        if app.practice not in CATALOG:
            raise ValueError(f"unknown practice {app.practice!r}")

    u = units(ds)
    u["tn_factor"] = 1.0
    u["tp_factor"] = 1.0
    u["cost_usd"] = 0.0
    u["treated_ha"] = 0.0

    for app in req.practices:
        p = CATALOG[app.practice]
        mask = u["lulc"].isin(p.eligible_lulc)
        if app.where.lulc:
            mask &= u["lulc"].isin(app.where.lulc)
        if app.where.counties:
            mask &= u["county_fips"].isin(app.where.counties)
        if app.where.subbasins:
            mask &= u["sub"].isin(app.where.subbasins)
        u.loc[mask, "tn_factor"] *= 1.0 - app.adoption * p.tn_eff
        u.loc[mask, "tp_factor"] *= 1.0 - app.adoption * p.tp_eff
        ha = u.loc[mask, "area_ha"] * app.adoption
        u.loc[mask, "treated_ha"] += ha
        u.loc[mask, "cost_usd"] += ha * p.cost_usd_ha

    u["tn_scn_kg"] = u["tn_kg"] * u["tn_factor"]
    u["tp_scn_kg"] = u["tp_kg"] * u["tp_factor"]
    u["tn_delivered_kg"] = (u["tn_kg"] - u["tn_scn_kg"]) * u["dr_n"]
    u["tp_delivered_kg"] = (u["tp_kg"] - u["tp_scn_kg"]) * u["dr_p"]

    result = {"name": req.name, "dataset": ds.name, "units": "kg/yr (average annual)"}
    for level in req.levels:
        result[level] = _aggregate(u, level)

    base_tn, base_tp = ds.outlet["tn_kg_yr"], ds.outlet["tp_kg_yr"]
    scn_tn = float(base_tn - u["tn_delivered_kg"].sum())
    scn_tp = float(base_tp - u["tp_delivered_kg"].sum())
    may = ds.outlet["may_nox_kg"]
    scn_may = float(may * scn_tn / base_tn) if may else None
    result["outlet"] = {
        "reach": ds.outlet_reach,
        "baseline_tn_kg": base_tn, "scenario_tn_kg": scn_tn,
        "baseline_tp_kg": base_tp, "scenario_tp_kg": scn_tp,
        "tn_reduction_pct": _pct(base_tn, scn_tn), "tp_reduction_pct": _pct(base_tp, scn_tp),
        "baseline_may_nox_kg": may, "scenario_may_nox_kg": scn_may,
    }
    result["hypoxia"] = hypoxia.estimate(may, scn_may, base_tn, scn_tn, req.hypoxia)
    total_cost = float(u["cost_usd"].sum())
    n_cut = float(u["tn_delivered_kg"].sum())
    result["cost"] = {
        "total_usd_yr": round(total_cost, 0),
        "usd_per_kg_tn_delivered": round(total_cost / n_cut, 2) if n_cut > 0 else None,
    }
    return result


_GROUP_KEYS = {
    "hru": ["hru", "sub", "lulc"],
    "subbasin": ["sub"],
    "county": ["county_fips", "county_name", "state"],
}


def _aggregate(u: pd.DataFrame, level: Level) -> list[dict] | dict:
    cols = ["area_ha", "treated_ha", "tn_kg", "tn_scn_kg", "tp_kg", "tp_scn_kg",
            "tn_delivered_kg", "tp_delivered_kg", "cost_usd"]
    if level == "basin":
        g = u[cols].sum().to_frame().T
    else:
        g = u.groupby(_GROUP_KEYS[level], as_index=False)[cols].sum()
    g["tn_reduction_pct"] = [_pct(b, s) for b, s in zip(g["tn_kg"], g["tn_scn_kg"])]
    g["tp_reduction_pct"] = [_pct(b, s) for b, s in zip(g["tp_kg"], g["tp_scn_kg"])]
    g["tn_yield_kg_ha"] = g["tn_kg"] / g["area_ha"]
    g["tp_yield_kg_ha"] = g["tp_kg"] / g["area_ha"]
    g = g.rename(columns={"tn_kg": "baseline_tn_kg", "tn_scn_kg": "scenario_tn_kg",
                          "tp_kg": "baseline_tp_kg", "tp_scn_kg": "scenario_tp_kg"})
    records = g.round(3).to_dict(orient="records")
    return records[0] if level == "basin" else records


def _pct(base: float, scn: float) -> float:
    return round(100 * (base - scn) / base, 2) if base else 0.0
