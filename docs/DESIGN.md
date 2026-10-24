# BASIN prototype design

## Goals for the prototype

1. Ingest SWAT outputs as the single source of truth for baseline loads.
2. Let a user describe a practice scenario (what, how much, where) and see the
   effect at field (HRU), subbasin, county, and basin scale.
3. Translate basin-outlet changes into a first-order Gulf hypoxia signal.
4. Stay small enough to change direction cheaply.

## Stack

Python 3.11+, FastAPI, pandas, pydantic. Data held in memory per dataset, loaded
at startup. No database yet: a UMRB SWAT run at HRU scale is a few hundred
thousand rows of average-annual data, which fits comfortably in memory. Move to
DuckDB/Parquet (or PostGIS once geometry is needed) when datasets or concurrency
grow.

## Data model

A **dataset** is one SWAT run directory:

| File | Content |
|---|---|
| `dataset.json` | name, description, `outlet_reach`, `swat_version`, `synthetic` |
| `output.hru` | SWAT2012 HRU yields (kg/ha) by period |
| `output.sub` | SWAT2012 subbasin output (optional, for checks) |
| `output.rch` | SWAT2012 reach loads; outlet reach gives delivered load and May flux |
| `subbasin_county.csv` | `sub, county_fips, county_name, state, area_fraction` from a GIS overlay |
| `delivery_ratio.csv` | optional `sub, dr_n, dr_p`, edge-of-field to outlet |

Parsing labels each row as month, year, or average. SWAT2012 puts the year count
in MON on the trailing average rows, so rows after the last annual row are
treated as averages rather than as months.

TN yield = ORGN + NSURQ + NLATQ + NO3GW + TNO3 (tile). TP = ORGP + SEDP + SOLP.

## Scenario engine

1. Split each HRU across counties by the subbasin-county area fractions, giving
   hru x county units, so county targeting stays inside the county.
2. For each practice application (`practice`, `adoption` 0-1, optional
   `where` by county, subbasin, land use), multiply eligible units' load by
   `1 - adoption * efficiency`. Practices stack multiplicatively.
3. Aggregate units to HRU, subbasin, county, basin.
4. Delivered reduction at the outlet = edge-of-field reduction x delivery
   ratio. Without `delivery_ratio.csv`, one basin-wide ratio is derived as
   outlet load / summed HRU load.
5. May NO3+NO2 at the outlet changes by the same fraction as delivered TN.

## Hypoxia

Relative model: UMRB May flux change x UMRB share of MARB May flux x elasticity,
applied to a reference hypoxic area. Reports scenario area, risk class against
the 5,000 km2 goal, and progress toward the 45% load reduction goal. All
parameters are request-overridable placeholders.

## Known simplifications (refine next)

- Practice effects are lookup efficiencies, not SWAT-simulated practice runs.
  The natural next step is to ingest SWAT runs per practice and use their HRU
  deltas as efficiencies (the API shape stays the same).
- Uniform delivery ratio unless a per-subbasin table is supplied; a proper
  version routes reductions through the reach network with in-stream retention.
- May flux scales with annual delivered TN.
- HRUs are non-spatial in SWAT2012; true field scale needs HRU or field
  geometry (e.g. DAWN fields) and a field-level crosswalk.
- SWAT+ outputs (`hru_ls_*`, `channel_sd_*`) need their own parser; the
  dataset layer is the only place that changes.
- Practice efficiencies and costs are rounded Iowa NRS figures, to be reviewed.
- Whitespace parsing assumes SWAT column headers are separated; a fixed-width
  reader is the fallback if real files run columns together.
