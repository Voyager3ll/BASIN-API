"""Conservation practice catalog.

Efficiencies are fractional reductions in edge-of-field TN and TP load on the
area where the practice is adopted. Starting values are rounded from the Iowa
Nutrient Reduction Strategy science assessment and are placeholders until the
team replaces them with SWAT-simulated practice runs or a reviewed table.
Costs are rough per-hectare annualized figures for ranking, not budgeting.
"""

from __future__ import annotations

from pydantic import BaseModel

ROW_CROPS = ["CORN", "SOYB", "CSIL", "AGRR", "AGRC", "WWHT"]


class Practice(BaseModel):
    id: str
    name: str
    tn_eff: float
    tp_eff: float
    eligible_lulc: list[str]
    cost_usd_ha: float
    source: str = "Iowa NRS science assessment (rounded, placeholder)"


CATALOG: dict[str, Practice] = {
    p.id: p
    for p in [
        Practice(id="n_rate_mrtn", name="N rate at MRTN", tn_eff=0.10, tp_eff=0.0,
                 eligible_lulc=["CORN", "CSIL"], cost_usd_ha=-15.0),
        Practice(id="spring_n", name="Spring instead of fall N", tn_eff=0.06, tp_eff=0.0,
                 eligible_lulc=["CORN", "CSIL"], cost_usd_ha=10.0),
        Practice(id="cover_crop", name="Cereal rye cover crop", tn_eff=0.31, tp_eff=0.29,
                 eligible_lulc=ROW_CROPS, cost_usd_ha=72.0),
        Practice(id="cons_tillage", name="Conservation tillage", tn_eff=0.0, tp_eff=0.33,
                 eligible_lulc=ROW_CROPS, cost_usd_ha=0.0),
        Practice(id="bioreactor", name="Denitrifying bioreactor (tiled land)", tn_eff=0.43, tp_eff=0.0,
                 eligible_lulc=ROW_CROPS, cost_usd_ha=20.0),
        Practice(id="saturated_buffer", name="Saturated buffer (tiled land)", tn_eff=0.50, tp_eff=0.0,
                 eligible_lulc=ROW_CROPS, cost_usd_ha=6.0),
        Practice(id="wetland", name="Targeted N-removal wetland", tn_eff=0.52, tp_eff=0.0,
                 eligible_lulc=ROW_CROPS, cost_usd_ha=25.0),
        Practice(id="riparian_buffer", name="Riparian buffer", tn_eff=0.91, tp_eff=0.58,
                 eligible_lulc=ROW_CROPS + ["PAST", "HAY"], cost_usd_ha=12.0),
        Practice(id="perennial", name="Perennial cover / land retirement", tn_eff=0.85, tp_eff=0.75,
                 eligible_lulc=ROW_CROPS, cost_usd_ha=500.0),
    ]
}
