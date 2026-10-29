# Plan and status

## Goal
A flood-shelter app with two views, built on the same precomputed data (`app_data/`):

1. **Resident view (mobile first, also desktop).** Pick your municipality, or let the browser locate you, and a
   flood severity. See the nearest candidate shelters that are **outside the modelled flood extent**, reachable by
   a **road that is not flooded**, and marked for **access for persons with reduced mobility (PRM)** where known.
   If no route stays dry, show "go to an upper floor" guidance.
   Location stays in the browser: nothing is entered, sent or stored.
2. **Administration view (desktop).** For mayors, emergency planning officers and governors:
   - flood risk per shelter, per municipality and scenario (depth, access, height, PRM),
   - the "shelter gap": exposed residents vs dry, reachable shelter capacity,
   - vulnerable groups (children, 65+, 80+, care homes, PRM proxy),
   - critical networks (roads, railways, power, gas, telecom) under water,
   - a multi-municipality triage table with CSV export.

Scope: Walloon municipalities covered by EMS EMSR518 (66). Germany and the Netherlands are a "next step" line only.

**Framing rules** (see `docs/IMPROVEMENTS.md` §5–6):
- **Candidate shelters are not official.** Official reception centres sit in municipal emergency plans (PGUI), which are
  usually confidential. The app shows *candidate* public buildings, and the administration view lets a municipality
  mark which ones are official.
- **Never write "safe".** Write "outside the modelled flood extent".
- **Permanent banner:** "Not official evacuation guidance. In an emergency call 112 and follow BE-Alert and your municipality."
- **EFAS is undefended hazard** (it ignores dykes and walls), and the EMS 2021 extent is a lower bound.
- **No building-level flood flags for private homes.** Show residents shelters and areas, never their own house.

## Data sources
| Need | Source | Type | Status |
|---|---|---|---|
| Flood extent and depth (RP10/100/500) | EFAS | challenge | ✅ |
| Observed 2021 | Copernicus EMS EMSR518 | challenge | ✅ |
| Buildings, height, use, age | GHS-OBAT | challenge | ✅ |
| Population | GHS-POP 2020 + Eurostat Census 2021 grid (age) + Statbel 2021 (80+) | challenge + external | ✅ |
| Main roads | EMS `transportationL` | challenge | ✅ |
| Railway lines | Infrabel main tracks (CC0) | external | ✅ |
| Shelter candidates | OSM + EMS (schools, hospitals, churches, sports halls) | external + challenge | ✅ |
| Full road network for routing | OSM (Geofabrik Belgium extract, avoids the overloaded Overpass servers) | external | ⏳ |
| PRM access | OSM `wheelchair` tag on shelters (already in the cached download) | external | ⏳ |
| Care homes, schools as vulnerable sites | OSM `amenity=nursing_home`, `social_facility` | external | ⏳ |
| Power, gas, telecom | OSM `power=*`, `man_made=pipeline`, `telecom=*`, masts; Elia / Fluxys open data (to verify) | external | ⏳ |
| Disability | none open at municipal level; 65+/80+ as proxy | – | ❌ (ask AVIQ / IWEPS) |

## Pipeline
| # | Step | Status | Output |
|---|------|--------|--------|
| 1 | Analysis areas: LAU 2021 municipalities clipped to the EMS areas, with coverage share | ✅ | `municipalities.gpkg` |
| 2 | Flood extents: observed 2021 and EFAS RP10/100/500 in depth classes, permanent water removed | ✅ | `flood_extents.gpkg` |
| 3 | Buildings: OBAT points with depth per scenario and flooded-in-2021 flag | ✅ | `buildings.parquet` |
| 4 | Shelter candidates: height, depth, flooded or not, status per scenario; EMS category per building | ✅ 2,346 | `facilities.gpkg` |
| 5 | Roads (EMS) and railway lines (Infrabel): km flooded per scenario | ✅ | `roads.gpkg`, `roads_stats.parquet` |
| 6 | Population and age, total and exposed (two-source range) | ✅ | `buildings.parquet`, `municipalities.gpkg` |
| 7 | **Data-quality flags:** municipalities with no EFAS-modelled river (28 of 66; replaces the review's "east of 5.94°", which was wrong), depths > 10 m (1,200), 2.5 m height floor (22.3%), depth inversions (84), depth unit metres (JRC README) | ✅ | flags in `buildings.parquet`, `municipalities.gpkg`, `facilities.gpkg` |
| 8 | **Shelter attributes:** PRM access (OSM `wheelchair`, tagged for only 49 of 2,346; upper-floor shelters marked "stairs likely"), rough capacity per scenario (largest building × ≤ 2 dry storeys × 50% ÷ 3.5 m² Sphere minimum; hospitals 0) | ✅ | `facilities.gpkg` |
| 9 | **Dry access:** OSM walking network (Geofabrik extract, 1.5 M segments); per scenario, flooded segments and bridges removed; nearest usable shelter with capacity from each 250 m residential cell, walking and PRM (no steps); shelter load vs capacity. RP100: 56,486 of 138,281 people in flood cells have no dry route within 300 m + 15 km. 394 rural cells get no route even when dry (to investigate) | ✅ | `access.parquet`, `facilities.gpkg` |
| 10 | **Vulnerability:** vulnerable sites (care homes, schools) in the extent; homes with no dry floor per cell (height ≤ depth + 1 m, aggregated, never per house) | ⏳ P1 | `cells.parquet` |
| 11 | **Shelter gap and evacuation priority** per 250 m cell and municipality: exposed people (by age), no dry route, no dry floor | ⏳ P2 | `cells.parquet`, `municipalities.gpkg` |
| 12 | **Utilities:** electricity, drinking water and gas sites in each flood extent (see "Utilities plan" below) | ⏳ P2 | `utilities.gpkg` |
| 15 | **Priority issues per municipality and scenario** (admin view, top of the page, 🔴/🟠/🟡 from screening thresholds): no dry route, no usable shelter, capacity gap, overloaded shelters, 65+, PRM, long walks, homes with no dry floor, hospitals, schools, roads, railways, dams, data gaps; plus an "All municipalities" triage tab | ✅ | `risks.parquet` |
| 14 | **Dams and weirs** as keep-away zones for residents (EMS 2152 + OSM `waterway=dam/weir`, 300 m / 100 m) | ✅ | `dams.gpkg` |
| 13 | **KPI export:** one script writing every number used in the brief, app and slides | ⏳ P1 | `app_data/kpis.json` |

## Apps
**Administration view: Streamlit (existing `app/app.py`)**
- ✅ Scenario and municipality pickers, map, Shelters, Population, Roads & rail, Compare, Buildings, Data & limits
- ✅ P0: review wording fixes, 112/BE-Alert note, observed-2021 banner, "not modelled" banner, "% missed" gated
  at n ≥ 30, buildings shown as 250 m cells only, height floor shown separately
- ⏳ P1: shelter risk table per municipality (status, depth, access, PRM, capacity) with CSV export;
  vulnerable-groups panel; mark official reception sites (kept in the session, never uploaded)
- ⏳ P2: multi-municipality triage table by province / rescue zone; utilities layer; one-page municipal sheet

**Resident view: mobile-first static web app (new `resident/`)**
- One HTML page with Leaflet and precomputed JSON per municipality. No server and no secrets, so it can be hosted as
  static files and also works on desktop.
- Flow: municipality (or "use my location", processed only in the browser) → severity → up to 3 candidate shelters
  outside the extent with a dry route: distance, walking time, PRM flag, "not official" label.
  No dry route: "go to an upper floor, call 112".
- FR and DE first (Eupen, Kelmis, Lontzen and Raeren are German-speaking), then NL and EN.
- Basemap: keyless tiles (Esri / OSM) so the CARTO key never reaches the public page.

## Next steps (in order)
1. **P0 data-quality flags and wording** (step 7 + admin P0): about 1 h. The current numbers otherwise mislead.
2. **Shelter attributes** (step 8): PRM from the cached OSM tags, rough capacity. About 1 h.
3. **Road graph and dry access** (step 9): download the Geofabrik Belgium extract once, build the graph for the
   66 municipalities, route per scenario. About 2–3 h. This is the core of the resident view.
4. **Resident web app**: first municipality (Pepinster) end to end, then all. About 3 h.
5. **Admin shelter-risk and vulnerability panels** (steps 10–11). About 2 h.
6. **Utilities** (step 12) if time allows. OSM coverage of power and gas is partial, so label it. Keep detailed
   critical-infrastructure maps in the admin view only.
7. **KPI export, brief numbers, AI sheet log, demo script.**

## Utilities plan (electricity, drinking water, gas)
**Question for the brief:** which utility sites sit in the flood extent, and how many residents could lose power,
water or gas as a result? In 2021 outages of all three hit the Vesdre valley (to source from SPW / operator reports).

**Data**
| Network | Open source | What it gives | Status |
|---|---|---|---|
| Electricity | OSM in the Geofabrik extract (already downloaded): `power=substation`, `plant`, `transformer`, `line`, `cable` | Substations and high-voltage lines; low-voltage distribution mostly missing | available |
| Electricity | Elia open data (transmission operator) | Mostly time series; grid geometry to verify | to verify |
| Drinking water | OSM: `man_made=water_works`, `water_tower`, `reservoir_covered`, `pumping_station`, `water_well` | Treatment plants, towers, reservoirs, pumping stations | available |
| Drinking water | SPW geoportal (WalOnMap): water abstraction points, protection zones; SWDE / CILE sites | Official sites; distribution pipes are not public | to verify |
| Gas | OSM: `man_made=pipeline` + `substance=gas`, `pipeline=substation` (pressure reduction stations) | Transmission pipelines and some stations | available, partial |
| Gas | Fluxys (transmission), ORES / RESA (distribution) | Network maps, not open GIS | to verify |
| All | EMS `facilitiesL` code 221 (pipelines, communication and electricity lines) | 2 features in AOI02 only | negligible |

**Method (2–3 h, all offline from the Geofabrik extract)**
1. `pipeline/build_utilities.py`: read the OSM features above (points, lines, areas) within the analysis bbox.
2. Per scenario: site in a flood cell (EFAS depth > 0 or 2021 extent) = "at risk"; lines and pipes: km in the extent.
3. Rough service areas: Voronoi polygons around substations and water sites, clipped to municipalities, then
   residents per area from the population step. Label it a proxy: real service areas are not public.
4. Admin view: "Utilities" tab (sites at risk per scenario, km of lines and pipes, residents in affected service areas).
5. Resident view: no locations of critical infrastructure. Only an advice line where a site serving the area is
   at risk: "power, water or gas may be cut: keep drinking water, charge your phone".

**Limits:** OSM coverage of utilities is partial, especially low-voltage power and gas distribution; locations of
critical infrastructure stay in the admin view (security).

## Rules and assumptions
- Exposed = OBAT centroid inside the observed extent, or in an EFAS cell with depth > 0 (about 90 m cells).
- Storey height 3 m. Shelter dry = footprint outside the extent; upper floors usable = height − depth ≥ 3 m.
- Population split over residential buildings by volume within each 1 km cell; range from two sources.
- Capacity: largest building footprint × up to 2 dry storeys × 50% usable ÷ 3.5 m² per person (Sphere minimum).
  A theoretical maximum for comparison between municipalities, not an official capacity. Hospitals get none.
- EFAS depth in metres (JRC README v3.1.1, per the review; check).

## Open questions for the team
- Named public actor for the brief. The review suggests the Governor of the Province of Liège.
- Is there an official Walloon 2021 flood extent (SPW) to show next to EMS in the Vesdre?
- Disability data: ask AVIQ / IWEPS, or keep 65+/80+ as the proxy and say so.
- Should scenarios cover full municipalities instead of only the EMS-mapped part (21 of 66 are less than half mapped)?
  That needs a 7-minute rerun and changes all numbers.
