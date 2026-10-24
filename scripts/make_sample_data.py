"""Generate a small synthetic SWAT2012 dataset in data/sample/.

The numbers are made up but shaped like a corn-belt watershed so the API can be
exercised end to end before real UMRB SWAT runs are plugged in.

    python scripts/make_sample_data.py
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample"
YEARS = list(range(2015, 2020))
N_SUB = 12
SEASON = [0.03, 0.04, 0.10, 0.15, 0.17, 0.15, 0.09, 0.05, 0.04, 0.05, 0.07, 0.06]

# lulc: (share of subbasin area, TN components kg/ha/yr, TP components kg/ha/yr)
LANDUSE = {
    "CORN": (0.38, dict(orgn=5.0, nsurq=2.0, nlatq=3.0, no3gw=5.0, tno3=15.0), dict(orgp=0.6, sedp=0.4, solp=0.2)),
    "SOYB": (0.32, dict(orgn=4.0, nsurq=1.0, nlatq=2.0, no3gw=4.0, tno3=9.0), dict(orgp=0.5, sedp=0.3, solp=0.2)),
    "PAST": (0.12, dict(orgn=1.5, nsurq=0.5, nlatq=1.0, no3gw=1.5, tno3=0.5), dict(orgp=0.15, sedp=0.1, solp=0.05)),
    "FRSD": (0.10, dict(orgn=0.8, nsurq=0.2, nlatq=0.5, no3gw=0.5, tno3=0.0), dict(orgp=0.05, sedp=0.03, solp=0.02)),
    "URML": (0.08, dict(orgn=2.0, nsurq=3.0, nlatq=1.0, no3gw=2.0, tno3=0.0), dict(orgp=0.3, sedp=0.2, solp=0.1)),
}
N_KEYS = ["orgn", "nsurq", "nlatq", "no3gw", "tno3"]
P_KEYS = ["orgp", "sedp", "solp"]
COUNTIES = [
    ("19001", "Sample County A", "IA"), ("19003", "Sample County B", "IA"),
    ("19005", "Sample County C", "IA"), ("27001", "Sample County D", "MN"),
    ("27003", "Sample County E", "MN"), ("55001", "Sample County F", "WI"),
]

BANNER = [
    " SWAT Sep 7 VER 2012/Rev 664",
    " BASIN synthetic sample dataset (not real model output)",
    "",
    " General Input/Output section (file.cio):",
    " ",
    "",
    " UNIT",
    " TIME",
]


def fmt(v: float) -> str:
    return f"{v:10.4E}" if abs(v) >= 1e5 else f"{v:10.3f}"


def periods():
    """Yield (mon_value, year, month) in SWAT2012 monthly print order."""
    for y in YEARS:
        for m in range(1, 13):
            yield m, y, m
        yield y, y, None
    yield float(len(YEARS)), None, None


def main() -> None:
    rnd = random.Random(42)
    OUT.mkdir(parents=True, exist_ok=True)

    hrus = []
    hru_id = 0
    for sub in range(1, N_SUB + 1):
        sub_area = rnd.uniform(300, 900)
        for lulc, (share, n, p) in LANDUSE.items():
            hru_id += 1
            scale = rnd.uniform(0.7, 1.3)
            hrus.append(dict(hru=hru_id, sub=sub, lulc=lulc, area=sub_area * share,
                             n={k: v * scale for k, v in n.items()},
                             p={k: v * scale for k, v in p.items()}))
    year_mult = {y: rnd.uniform(0.75, 1.25) for y in YEARS}

    def yld(h, key, comp, year, month):
        annual = h[key][comp]
        if year is None:
            return annual * sum(year_mult.values()) / len(YEARS)
        annual *= year_mult[year]
        return annual if month is None else annual * SEASON[month - 1]

    # output.hru
    cols = ["LULC", "HRU", "GIS", "SUB", "MGT", "MON", "AREAkm2", "WYLDmm", "SYLDt/ha",
            "ORGNkg/ha", "ORGPkg/ha", "SEDPkg/ha", "NSURQkg/ha", "NLATQkg/ha", "NO3GWkg/ha",
            "SOLPkg/ha", "TNO3kg/ha"]
    lines = BANNER + ["".join(f"{c:>12}" for c in cols)]
    for mon, y, m in periods():
        for h in hrus:
            v = {k: yld(h, "n", k, y, m) for k in N_KEYS} | {k: yld(h, "p", k, y, m) for k in P_KEYS}
            wyld = 250.0 * (year_mult[y] if y else 1.0) * (SEASON[m - 1] if m else 1.0)
            row = [h["lulc"], h["hru"], f"{h['sub']:05d}{h['hru']:04d}", h["sub"], 1, mon,
                   h["area"], wyld, 0.5 * (SEASON[m - 1] if m else 1.0),
                   v["orgn"], v["orgp"], v["sedp"], v["nsurq"], v["nlatq"], v["no3gw"], v["solp"], v["tno3"]]
            lines.append("".join(f"{x:>12}" if isinstance(x, (str, int)) else f"{fmt(x):>12}" for x in row))
    (OUT / "output.hru").write_text("\n".join(lines) + "\n")

    # output.sub (area-weighted HRU yields)
    cols = ["SUB", "GIS", "MON", "AREAkm2", "WYLDmm", "SYLDt/ha", "ORGNkg/ha", "ORGPkg/ha",
            "NSURQkg/ha", "SOLPkg/ha", "SEDPkg/ha", "LATNO3kg/h", "GWNO3kg/ha"]
    lines = BANNER + ["      " + "".join(f"{c:>12}" for c in cols)]
    for mon, y, m in periods():
        for sub in range(1, N_SUB + 1):
            hs = [h for h in hrus if h["sub"] == sub]
            a = sum(h["area"] for h in hs)
            w = lambda key, comp: sum(yld(h, key, comp, y, m) * h["area"] for h in hs) / a  # noqa: E731
            row = [sub, f"{sub:08d}", mon, a, 250.0, 0.5, w("n", "orgn"), w("p", "orgp"),
                   w("n", "nsurq"), w("p", "solp"), w("p", "sedp"), w("n", "nlatq") + w("n", "tno3"),
                   w("n", "no3gw")]
            lines.append("BIGSUB" + "".join(f"{x:>12}" if isinstance(x, (str, int)) else f"{fmt(x):>12}" for x in row))
    (OUT / "output.sub").write_text("\n".join(lines) + "\n")

    # output.rch: reach N_SUB is the outlet and receives everything upstream.
    cols = ["RCH", "GIS", "MON", "AREAkm2", "FLOW_OUTcms", "SED_OUTtons", "ORGN_OUTkg", "ORGP_OUTkg",
            "NO3_OUTkg", "NH4_OUTkg", "NO2_OUTkg", "MINP_OUTkg"]
    lines = BANNER + ["      " + "".join(f"{c:>12}" for c in cols)]
    for mon, y, m in periods():
        for rch in range(1, N_SUB + 1):
            hs = hrus if rch == N_SUB else [h for h in hrus if h["sub"] == rch]
            dr_n, dr_p = (0.6, 0.5) if rch == N_SUB else (0.9, 0.9)
            tn = sum(sum(yld(h, "n", k, y, m) for k in N_KEYS) * h["area"] * 100 for h in hs) * dr_n
            tp = sum(sum(yld(h, "p", k, y, m) for k in P_KEYS) * h["area"] * 100 for h in hs) * dr_p
            area = sum(h["area"] for h in hs)
            row = [rch, f"{rch:08d}", mon, area, area * 0.01, tp * 50, tn * 0.25, tp * 0.6,
                   tn * 0.70, tn * 0.03, tn * 0.02, tp * 0.4]
            lines.append("REACH " + "".join(f"{x:>12}" if isinstance(x, (str, int)) else f"{fmt(x):>12}" for x in row))
    (OUT / "output.rch").write_text("\n".join(lines) + "\n")

    # subbasin -> county area fractions
    with open(OUT / "subbasin_county.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["sub", "county_fips", "county_name", "state", "area_fraction"])
        for sub in range(1, N_SUB + 1):
            c1 = COUNTIES[(sub - 1) // 2]
            if sub % 3 == 0:
                c2 = COUNTIES[((sub - 1) // 2 + 1) % len(COUNTIES)]
                wr.writerow([sub, *c1, 0.6])
                wr.writerow([sub, *c2, 0.4])
            else:
                wr.writerow([sub, *c1, 1.0])

    (OUT / "dataset.json").write_text(json.dumps({
        "name": "sample",
        "description": "Synthetic 12-subbasin SWAT2012 run for development. Not real model output.",
        "swat_version": "2012",
        "outlet_reach": N_SUB,
        "synthetic": True,
    }, indent=2) + "\n")
    print(f"wrote sample dataset to {OUT}")


if __name__ == "__main__":
    main()
