# Plan and status

Scope now: Walloon municipalities covered by EMS EMSR518 (66 municipalities, AOI01 Liège/Vesdre, AOI02 Rochefort area).
Scale to Germany / Netherlands only after the Walloon version is complete.

## Pipeline

| # | Step | Status | Output |
|---|------|--------|--------|
| 1 | Analysis areas: LAU 2021 municipalities clipped to the EMS areas of interest, with coverage share | ✅ done | `municipalities.gpkg` |
| 2 | Flood extents: observed 2021 (EMS MONIT01) and EFAS RP10/100/500 in depth classes, permanent water removed | ✅ done | `flood_extents.gpkg` |
| 3 | Buildings: OBAT points with EFAS depth per scenario and flooded-in-2021 flag | ✅ done | `buildings.parquet` |
| 4 | Shelter candidates (schools, hospitals, churches, stadiums/sports halls from OSM): height, depth, flooded or not, shelter status per scenario; EMS building category for every building | 🔄 running (OSM download) | `facilities.gpkg`, `buildings.parquet` |
| 5 | Roads: km flooded per scenario and road class (EMS `transportationL`) | ⏳ to do | |
| 6 | Population: inhabitants and age (<15, 15–64, 65+, 80+ estimate), total and exposed, range from two sources | 🟡 script written, to run after step 4 | `buildings.parquet`, `municipalities.gpkg` |
| 7 | Vulnerability: residential buildings with no dry floor (height ≤ depth + 1 m); shelter rule already in step 4 | ⏳ to do | |
| 8 | Evacuation priority: 250 m cells scored by depth × people × vulnerable share, extra weight for schools/hospitals/80+ | ⏳ to do | |
| 9 | Comparison with 2021: hit / missed / over-predicted buildings per scenario | ✅ in the app | |

## App
- ✅ Scenario and municipality pickers (list sorted by exposure, selection kept across scenarios)
- ✅ Tiles, map (CARTO / OSM / satellite basemaps), Compare with 2021, Buildings, Data & limits tabs
- 🟡 Shelters and Population tabs (waiting for steps 4 and 6 data)
- ⏳ Roads layer, vulnerable buildings, evacuation priority list with CSV download
- Optional: plain-language summary per municipality written by Claude from aggregated numbers only

## Rules and assumptions
- Exposed building = OBAT centroid inside the extent (2021) or in an EFAS cell with depth > 0.
- Storey height 3 m. Shelter: dry = footprint outside the extent; upper floors usable = height − depth ≥ 3 m.
- Population allocated to residential buildings by volume (footprint × height) within each 1 km cell.
- EFAS depth unit assumed metres (confirm in Annex 2).

## Open questions for the team
- Named public actor for the brief (e.g. Liège province crisis cell, Walloon regional crisis centre).
- Is there an official Walloon 2021 flood extent to replace or complement EMS in the Vesdre valley?
- Disability: no open municipal data; ask AVIQ / IWEPS, or keep 65+/80+ as the proxy and say so.
