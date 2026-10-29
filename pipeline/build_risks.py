"""Step 10 of the impact-card pipeline: priority issues per municipality and scenario (admin view).

Run after build_access.py (and build_dams.py if available). Each issue gets a level from screening thresholds:
1 = red (most important), 2 = orange, 3 = yellow (present, least important). The thresholds below are assumptions
for screening, not official standards; the admin view shows them. Writes app_data/risks.parquet.
"""
import os, time
from pathlib import Path
from common import save_parquet
import numpy as np
import pandas as pd
import geopandas as gpd

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "app_data"
SCENARIOS = ["rp10", "rp100", "rp500", "observed_2021"]
USABLE = {"Dry: usable", "Wet: upper floors usable", "Dry in 2021"}
LONG_WALK_MIN = 30
SUSPECT_DEPTH_M = 10
DAM_NEAR_DEG = 0.02                                # ~2 km around the mapped part of the municipality
# thresholds: (red, orange); anything above 0 but below orange is yellow
T_NO_ROUTE = (1000, 200)                           # people; or share of people in flood cells (below)
T_NO_ROUTE_SHARE = (0.30, 0.10)
T_SHARE_MIN = (200, 50)                            # people needed before a share alone makes it red / orange
T_ELDERLY = (1000, 300)
T_PRM = (500, 100)
T_LONG_WALK = (500, 100)
T_NO_DRY_FLOOR = (500, 100)
T_GAP = (1.0, 0.5, 0.25)                           # people in flood cells / usable capacity: red, orange, yellow
T_OVERLOAD = (1000, 200)                           # people above capacity; or share of people in flood cells
T_OVERLOAD_SHARE = (0.50, 0.20)
T_ROADS_SHARE = 0.20

t0 = time.time()
log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

munis = gpd.read_file(OUT / "municipalities.gpkg")
cells = pd.read_parquet(OUT / "access.parquet").drop(columns="geometry")
fac = gpd.read_file(OUT / "facilities.gpkg")
roads = pd.read_parquet(OUT / "roads_stats.parquet")
b = pd.read_parquet(OUT / "buildings.parquet", columns=["LAU_ID", "use", "height", "pop_census", "depth_rp10",
                                                          "depth_rp100", "depth_rp500"])
dams = gpd.read_file(OUT / "dams.gpkg") if (OUT / "dams.gpkg").exists() else None


def level(x, red, orange):
    return None if x <= 0 else 1 if x >= red else 2 if x >= orange else 3


def issues(m, k):
    rows = []
    add = lambda lvl, issue, value, text, action: lvl and rows.append(
        {"LAU_ID": m.LAU_ID, "scenario": k, "level": lvl, "issue": issue, "value": float(value), "text": text,
         "action": action})
    c = cells[cells["LAU_ID"] == m.LAU_ID]
    f = fac[fac["LAU_ID"] == m.LAU_ID]
    exposed = c[f"pop_exposed_{k}"].sum()
    ex = c[c[f"pop_exposed_{k}"] > 0]
    usable = f[f[f"shelter_{k}"].isin(USABLE) & (f[f"capacity_{k}"] > 0)]

    if exposed > 0:
        no_route = ex.loc[ex[f"shelter_{k}"] < 0, f"pop_exposed_{k}"].sum()
        share = no_route / exposed                 # a share only counts above a minimum number of people
        lvl = (None if no_route <= 0 else
               1 if no_route >= T_NO_ROUTE[0] or (share >= T_NO_ROUTE_SHARE[0] and no_route >= T_SHARE_MIN[0]) else
               2 if no_route >= T_NO_ROUTE[1] or (share >= T_NO_ROUTE_SHARE[1] and no_route >= T_SHARE_MIN[1]) else 3)
        add(lvl, "No dry route to a shelter", no_route,
            f"{no_route:,.0f} people in flood cells ({share:.0%}) have no dry walking route to a candidate shelter",
            "Plan vertical evacuation (upper floors), boat or helicopter rescue, and early warning for these areas")
        if usable.empty:
            add(1, "No usable shelter", exposed, f"No usable candidate shelter with indoor space in the municipality "
                f"while {exposed:,.0f} people live in flood cells", "Agree reception capacity with neighbouring "
                "municipalities and the province before the event")
        else:
            gap = exposed / usable[f"capacity_{k}"].sum()
            add(1 if gap > T_GAP[0] else 2 if gap > T_GAP[1] else 3 if gap > T_GAP[2] else None, "Shelter capacity gap",
                gap, f"People in flood cells = {gap:.0%} of the rough capacity of usable shelters "
                f"({usable[f'capacity_{k}'].sum():,} places)", "Check real capacities and add reception sites outside "
                "the flood extent")
        excess_by_site = (f[f"load_{k}"] - f[f"capacity_{k}"]).clip(lower=0)
        excess, sites = excess_by_site.sum(), (excess_by_site > 0).sum()
        ex_share = excess / exposed
        lvl = (None if excess <= 0 else 1 if excess >= T_OVERLOAD[0] or ex_share >= T_OVERLOAD_SHARE[0] else
               2 if excess >= T_OVERLOAD[1] or ex_share >= T_OVERLOAD_SHARE[1] else 3)
        add(lvl, "Overloaded shelters", excess, f"{sites} nearest shelter(s) would receive {excess:,.0f} more people "
            f"than their rough capacity ({ex_share:.0%} of people in flood cells)",
            "Spread arrivals across sites; pre-assign neighbourhoods to shelters")
        elderly = getattr(m, f"exp_{k}_pop_65plus_census")
        add(level(elderly, *T_ELDERLY), "Elderly residents in flood cells", elderly,
            f"{elderly:,.0f} people aged 65+ live in flood cells (about {elderly / max(exposed, 1):.0%} of them; "
            f"~{getattr(m, f'exp_{k}_pop_census') * m.share_80plus:,.0f} aged 80+, estimate)",
            "Door-to-door warning lists with CPAS and care services; prioritise assisted evacuation")
        prm = ex.loc[ex[f"prm_shelter_{k}"] < 0, f"pop_exposed_{k}"].sum()
        add(level(prm, *T_PRM), "No step-free route (PRM)", prm, f"{prm:,.0f} people in flood cells have no dry "
            "step-free route to a shelter accessible without stairs", "Register residents with reduced mobility; "
            "plan vehicles and staff for assisted evacuation")
        long_walk = ex.loc[ex[f"walk_min_{k}"] > LONG_WALK_MIN, f"pop_exposed_{k}"].sum()
        add(level(long_walk, *T_LONG_WALK), "Long distance to a dry shelter", long_walk,
            f"{long_walk:,.0f} people in flood cells walk more than {LONG_WALK_MIN} min to the nearest dry shelter",
            "Add closer reception sites or transport (buses) from collection points")

    if k != "observed_2021":
        r = b[(b["LAU_ID"] == m.LAU_ID) & (b["use"] == 1)]
        d = r[f"depth_{k}"]
        no_floor = r[(d > 0) & (d <= SUSPECT_DEPTH_M) & (r["height"] <= d + 1)]
        add(level(len(no_floor), *T_NO_DRY_FLOOR), "Homes with no dry floor", len(no_floor),
            f"{len(no_floor):,} homes in flood cells are not tall enough to keep a dry floor "
            f"(~{no_floor['pop_census'].sum():,.0f} residents; OBAT heights, cell depths)",
            "These residents cannot shelter upstairs: evacuate them first")

    hosp = f[f["category"] == "Hospital"]
    wet = ~hosp[f"shelter_{k}"].isin({"Dry: usable", "Dry in 2021"})
    if wet.any():
        upper_only = hosp[wet][f"shelter_{k}"].eq("Wet: upper floors usable").all()
        add(2 if upper_only else 1, "Hospital in the flood extent", wet.sum(),
            f"{wet.sum()} hospital or clinic site(s) in the flood extent: " + ", ".join(hosp[wet]["name"].replace("", "unnamed")[:3]),
            "Check the hospital emergency plan (evacuation of patients, power backup, access)")
    sch = f[f["category"] == "School"]
    s_bad = sch[f"shelter_{k}"].isin({"Wet: not usable", "Wet: height uncertain", "Flooded in 2021"}).sum()
    s_up = sch[f"shelter_{k}"].eq("Wet: upper floors usable").sum()
    add(2 if s_bad else 3 if s_up else None, "Schools in the flood extent", s_bad + s_up,
        f"{s_bad + s_up} school site(s) in the flood extent ({s_bad} not usable, {s_up} upper floors only)",
        "Include schools in the warning chain; plan pupil evacuation during school hours")

    rs = roads[roads["LAU_ID"] == m.LAU_ID].groupby("mode")[["network_km", f"flooded_km_{k}"]].sum()
    for mode, label in [("Road", "Main roads flooded"), ("Railway", "Railway lines flooded")]:
        if mode in rs.index and rs.loc[mode, f"flooded_km_{k}"] > 0:
            km, share = rs.loc[mode, f"flooded_km_{k}"], rs.loc[mode, f"flooded_km_{k}"] / rs.loc[mode, "network_km"]
            add(2 if share >= T_ROADS_SHARE else 3, label, km, f"{km:.1f} km ({share:.0%} of the mapped network) "
                "under water", "Plan detours for rescue services; keep evacuation routes clear")

    if dams is not None:
        w, s, e, n = m.geometry.bounds
        near = dams.cx[w - DAM_NEAR_DEG:e + DAM_NEAR_DEG, s - DAM_NEAR_DEG:n + DAM_NEAR_DEG]
        big = near[near["kind"] == "Dam"]
        if not near.empty:
            add(3, "Dams or weirs nearby", len(near), f"{len(big)} dam(s) and {len(near) - len(big)} weir(s) within "
                "~2 km" + (": " + ", ".join(sorted(set(big["name"]) - {""})[:3]) if (big["name"] != "").any() else ""),
                "Check dam release procedures and warning with the operator (SPW)")
    if k != "observed_2021" and not m.efas_modelled:
        add(3, "Data gap: no modelled river", 0, "EFAS models no river here: small streams and runoff are not "
            "covered, so 0 does not mean no risk", "Use the Walloon flood hazard map and local knowledge")
    if m.coverage < 0.5:
        add(3, "Data gap: partly mapped", m.coverage, f"Copernicus EMS mapped only {m.coverage:.0%} of the "
            "municipality; all figures cover that part only", "Complete with municipal data before decisions")
    return rows


rows = [r for m in munis.itertuples() for k in SCENARIOS for r in issues(m, k)]
risks = pd.DataFrame(rows).sort_values(["LAU_ID", "scenario", "level", "value"], ascending=[True, True, True, False])
save_parquet(risks, OUT / "risks.parquet")
summary = risks[risks["scenario"] == "rp100"].groupby("level").size().to_dict()
log(f"{len(risks):,} issues for {risks['LAU_ID'].nunique()} municipalities; RP100 by level {summary}")
top = risks[(risks["scenario"] == "rp100") & (risks["level"] == 1)].merge(munis[["LAU_ID", "name"]])
log("RP100 red issues: " + "; ".join(f"{n}: {', '.join(g['issue'])}" for n, g in top.groupby("name"))[:900])
os._exit(0)
