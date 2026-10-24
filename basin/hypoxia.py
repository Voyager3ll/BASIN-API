"""Gulf hypoxia response to UMRB load changes.

The prototype uses a relative model so it works with any SWAT run, synthetic
or real: the fractional change in UMRB May nitrate (NO3+NO2) flux at the basin
outlet is scaled by the UMRB share of the Mississippi/Atchafalaya (MARB) May
flux, then applied to a reference hypoxic area through an elasticity.

    dL_marb   = umrb_share * dL_umrb
    area      = ref_area_km2 * (1 + elasticity * dL_marb)

All parameters are placeholders to be replaced with a published load-area
regression (e.g. Turner et al. or Scavia et al.) during refinement. The
Hypoxia Task Force goal is a 5-year average area under 5,000 km2 and a 45%
cut in TN and TP load relative to the 1980-1996 average.
"""

from __future__ import annotations

from pydantic import BaseModel

HTF_AREA_GOAL_KM2 = 5000.0
HTF_LOAD_REDUCTION_GOAL = 0.45


class HypoxiaParams(BaseModel):
    ref_area_km2: float = 14000.0    # recent multi-year average, placeholder
    umrb_share: float = 0.40          # UMRB share of MARB May NO3+NO2 flux, placeholder
    elasticity: float = 1.0           # % area change per % MARB May flux change


def estimate(baseline_may_kg: float | None, scenario_may_kg: float | None,
             baseline_tn_kg: float, scenario_tn_kg: float,
             params: HypoxiaParams | None = None) -> dict:
    p = params or HypoxiaParams()
    out: dict = {"params": p.model_dump(), "goal_area_km2": HTF_AREA_GOAL_KM2}

    tn_change = scenario_tn_kg / baseline_tn_kg - 1.0 if baseline_tn_kg else 0.0
    out["umrb_tn_reduction_pct"] = round(-100 * tn_change, 2)
    out["progress_to_45pct_goal_pct"] = round(min(100.0, -100 * tn_change / HTF_LOAD_REDUCTION_GOAL), 2)

    if baseline_may_kg:
        d_umrb = scenario_may_kg / baseline_may_kg - 1.0
    else:
        # No monthly reach output: fall back to the annual TN change.
        d_umrb = tn_change
        out["note"] = "No May reach output; used annual TN change as a proxy."
    d_marb = p.umrb_share * d_umrb
    area = float(max(0.0, p.ref_area_km2 * (1.0 + p.elasticity * d_marb)))
    out.update(
        umrb_may_nox_change_pct=round(100 * d_umrb, 2),
        marb_may_nox_change_pct=round(100 * d_marb, 2),
        baseline_area_km2=p.ref_area_km2,
        scenario_area_km2=round(area, 1),
        meets_area_goal=bool(area <= HTF_AREA_GOAL_KM2),
        risk=_risk_class(area),
    )
    return out


def _risk_class(area_km2: float) -> str:
    if area_km2 <= HTF_AREA_GOAL_KM2:
        return "low"
    if area_km2 <= 10000:
        return "moderate"
    if area_km2 <= 15000:
        return "high"
    return "severe"
