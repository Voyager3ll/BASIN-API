"""Parsers for SWAT2012 text outputs (output.hru, output.sub, output.rch).

SWAT2012 writes fixed-width tables with a free-text banner, a column header
line, and one row per spatial unit per print period. The MON column holds the
month (1-12) for monthly rows, the calendar year for annual summary rows, and
the number of simulated years for the final average-annual rows.

Parsing splits on whitespace, which holds for the default SWAT2012 print
formats. If a project emits values that run together, swap in a fixed-width
reader here; the rest of the code only depends on the returned DataFrames.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Leading label tokens SWAT writes on data rows but not in the header line.
_ROW_LABELS = {"BIGSUB", "REACH", "HRU"}

# Columns used downstream, mapped to short, stable names.
HRU_COLUMNS = {
    "LULC": "lulc",
    "HRU": "hru",
    "GIS": "gis",
    "SUB": "sub",
    "MGT": "mgt",
    "MON": "mon",
    "AREAkm2": "area_km2",
    "WYLDmm": "wyld_mm",
    "SYLDt/ha": "syld_t_ha",
    "ORGNkg/ha": "orgn_kg_ha",
    "NSURQkg/ha": "nsurq_kg_ha",
    "NLATQkg/ha": "nlatq_kg_ha",
    "NO3GWkg/ha": "no3gw_kg_ha",
    "TNO3kg/ha": "tno3_kg_ha",
    "ORGPkg/ha": "orgp_kg_ha",
    "SEDPkg/ha": "sedp_kg_ha",
    "SOLPkg/ha": "solp_kg_ha",
}

SUB_COLUMNS = {
    "SUB": "sub",
    "GIS": "gis",
    "MON": "mon",
    "AREAkm2": "area_km2",
    "WYLDmm": "wyld_mm",
    "SYLDt/ha": "syld_t_ha",
    "ORGNkg/ha": "orgn_kg_ha",
    "ORGPkg/ha": "orgp_kg_ha",
    "NSURQkg/ha": "nsurq_kg_ha",
    "SOLPkg/ha": "solp_kg_ha",
    "SEDPkg/ha": "sedp_kg_ha",
    "LATNO3kg/h": "latno3_kg_ha",
    "GWNO3kg/ha": "gwno3_kg_ha",
}

RCH_COLUMNS = {
    "RCH": "rch",
    "GIS": "gis",
    "MON": "mon",
    "AREAkm2": "area_km2",
    "FLOW_OUTcms": "flow_out_cms",
    "SED_OUTtons": "sed_out_t",
    "ORGN_OUTkg": "orgn_out_kg",
    "ORGP_OUTkg": "orgp_out_kg",
    "NO3_OUTkg": "no3_out_kg",
    "NH4_OUTkg": "nh4_out_kg",
    "NO2_OUTkg": "no2_out_kg",
    "MINP_OUTkg": "minp_out_kg",
}


def _read_table(path: Path, header_key: str, columns: dict[str, str]) -> pd.DataFrame:
    lines = Path(path).read_text().splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.split()[:1] == [header_key])
    except StopIteration:
        raise ValueError(f"{path}: no header line starting with {header_key!r}") from None

    header = lines[start].split()
    rows = []
    for ln in lines[start + 1:]:
        tokens = ln.split()
        if not tokens:
            continue
        if tokens[0] in _ROW_LABELS and tokens[0] not in header:
            tokens = tokens[1:]
        if len(tokens) != len(header):
            raise ValueError(
                f"{path}: row has {len(tokens)} fields, header has {len(header)}: {ln[:60]!r}"
            )
        rows.append(tokens)

    df = pd.DataFrame(rows, columns=header)
    keep = [c for c in columns if c in df.columns]
    df = df[keep].rename(columns=columns)
    for col in df.columns:
        if col != "lulc":
            df[col] = pd.to_numeric(df[col])
    return _label_periods(df)


def _label_periods(df: pd.DataFrame) -> pd.DataFrame:
    """Split MON into period type, year, and month.

    Monthly rows are assigned the year of the annual summary row that follows
    them, which is how SWAT2012 orders a monthly print.
    """
    mon = df["mon"]
    period = pd.Series("month", index=df.index)
    is_year = mon >= 1800
    period[is_year] = "year"
    # The trailing average-annual rows carry the number of years in MON, which
    # can look like a month, so anything after the last annual row is average.
    if is_year.any():
        period[df.index > is_year[is_year].index[-1]] = "average"
    df = df.assign(period=period)

    year = pd.Series(pd.NA, index=df.index, dtype="Int64")
    year[period == "year"] = mon[period == "year"].astype(int)
    year = year.bfill()
    year[period == "average"] = pd.NA
    df["year"] = year
    df["month"] = mon.where(period == "month").astype("Int64")
    return df.drop(columns="mon")


def read_output_hru(path: Path) -> pd.DataFrame:
    return _read_table(path, "LULC", HRU_COLUMNS)


def read_output_sub(path: Path) -> pd.DataFrame:
    return _read_table(path, "SUB", SUB_COLUMNS)


def read_output_rch(path: Path) -> pd.DataFrame:
    return _read_table(path, "RCH", RCH_COLUMNS)
