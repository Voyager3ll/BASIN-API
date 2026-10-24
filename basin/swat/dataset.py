"""Load one SWAT run plus the crosswalks BASIN needs to aggregate it.

A dataset directory holds:

    dataset.json           name, description, outlet_reach, synthetic flag
    output.hru             SWAT2012 HRU output
    output.sub             SWAT2012 subbasin output (optional, used for checks)
    output.rch             SWAT2012 reach output
    subbasin_county.csv    sub, county_fips, county_name, state, area_fraction
    delivery_ratio.csv     optional: sub, dr_n, dr_p (edge-of-field to outlet)

Loads are reported in kg/yr (average annual) unless a name says otherwise.
Reach mass fields are treated as period totals, which is how SWAT2012 writes
monthly and annual reach loads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .parsers import read_output_hru, read_output_rch, read_output_sub

KM2_TO_HA = 100.0
N_YIELD_COLS = ["orgn_kg_ha", "nsurq_kg_ha", "nlatq_kg_ha", "no3gw_kg_ha", "tno3_kg_ha"]
P_YIELD_COLS = ["orgp_kg_ha", "sedp_kg_ha", "solp_kg_ha"]


def _average_annual(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Average-annual rows if SWAT printed them, else the mean of yearly rows."""
    avg = df[df["period"] == "average"]
    if avg.empty:
        avg = df[df["period"] == "year"].groupby(keys, as_index=False).mean(numeric_only=True)
    return avg.reset_index(drop=True)


@dataclass
class SwatDataset:
    name: str
    path: Path
    meta: dict
    hru: pd.DataFrame            # one row per HRU, average annual, with tn_kg / tp_kg
    rch: pd.DataFrame            # all reach rows as parsed
    sub: pd.DataFrame | None
    sub_county: pd.DataFrame
    delivery: pd.DataFrame       # sub, dr_n, dr_p
    outlet_reach: int
    outlet: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "SwatDataset":
        path = Path(path)
        meta = json.loads((path / "dataset.json").read_text())

        hru_raw = read_output_hru(path / "output.hru")
        hru = _average_annual(hru_raw, ["hru"])
        hru["lulc"] = hru["hru"].map(hru_raw.drop_duplicates("hru").set_index("hru")["lulc"])
        for col in N_YIELD_COLS + P_YIELD_COLS:
            if col not in hru:
                hru[col] = 0.0
        hru["area_ha"] = hru["area_km2"] * KM2_TO_HA
        hru["tn_kg_ha"] = hru[N_YIELD_COLS].sum(axis=1)
        hru["tp_kg_ha"] = hru[P_YIELD_COLS].sum(axis=1)
        hru["tn_kg"] = hru["tn_kg_ha"] * hru["area_ha"]
        hru["tp_kg"] = hru["tp_kg_ha"] * hru["area_ha"]
        hru["sub"] = hru["sub"].astype(int)
        hru["hru"] = hru["hru"].astype(int)

        rch = read_output_rch(path / "output.rch")
        sub = read_output_sub(path / "output.sub") if (path / "output.sub").exists() else None

        sub_county = pd.read_csv(path / "subbasin_county.csv", dtype={"county_fips": str})
        _check_fractions(sub_county)

        outlet_reach = int(meta.get("outlet_reach") or rch.loc[rch["area_km2"].idxmax(), "rch"])
        ds = cls(
            name=meta["name"], path=path, meta=meta, hru=hru, rch=rch, sub=sub,
            sub_county=sub_county, delivery=pd.DataFrame(), outlet_reach=outlet_reach,
        )
        ds.outlet = ds._outlet_loads()
        ds.delivery = ds._delivery_ratios(path / "delivery_ratio.csv")
        return ds

    def _outlet_loads(self) -> dict:
        r = self.rch[self.rch["rch"] == self.outlet_reach].copy()
        r["tn_kg"] = r[["orgn_out_kg", "no3_out_kg", "nh4_out_kg", "no2_out_kg"]].sum(axis=1)
        r["tp_kg"] = r[["orgp_out_kg", "minp_out_kg"]].sum(axis=1)
        r["nox_kg"] = r[["no3_out_kg", "no2_out_kg"]].sum(axis=1)
        years = r[r["period"] == "year"]
        may = r[(r["period"] == "month") & (r["month"] == 5)]
        return {
            "reach": self.outlet_reach,
            "years": sorted(int(y) for y in years["year"].dropna().unique()),
            "tn_kg_yr": float(years["tn_kg"].mean()),
            "tp_kg_yr": float(years["tp_kg"].mean()),
            "may_nox_kg": float(may["nox_kg"].mean()) if not may.empty else None,
        }

    def _delivery_ratios(self, csv: Path) -> pd.DataFrame:
        subs = sorted(self.hru["sub"].unique())
        if csv.exists():
            dr = pd.read_csv(csv)
            return dr.set_index("sub").reindex(subs).fillna(1.0).reset_index()
        # Fallback: one basin-wide ratio, outlet load over summed edge-of-field load.
        dr_n = min(1.0, self.outlet["tn_kg_yr"] / self.hru["tn_kg"].sum())
        dr_p = min(1.0, self.outlet["tp_kg_yr"] / self.hru["tp_kg"].sum())
        return pd.DataFrame({"sub": subs, "dr_n": dr_n, "dr_p": dr_p})

    def summary(self) -> dict:
        return {
            "name": self.name,
            "description": self.meta.get("description", ""),
            "synthetic": bool(self.meta.get("synthetic", False)),
            "swat_version": self.meta.get("swat_version", "2012"),
            "n_hru": int(len(self.hru)),
            "n_subbasins": int(self.hru["sub"].nunique()),
            "n_counties": int(self.sub_county["county_fips"].nunique()),
            "area_km2": float(self.hru["area_km2"].sum()),
            "outlet": self.outlet,
        }


def _check_fractions(sub_county: pd.DataFrame) -> None:
    totals = sub_county.groupby("sub")["area_fraction"].sum()
    bad = totals[(totals - 1.0).abs() > 0.01]
    if not bad.empty:
        raise ValueError(f"subbasin_county.csv: area_fraction does not sum to 1 for subs {list(bad.index)}")
