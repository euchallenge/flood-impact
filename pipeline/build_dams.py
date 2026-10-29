"""Dams and weirs as keep-away zones for the resident view.

Sources: Copernicus EMS facilities with info code 2152 "Dams" (challenge data) and OpenStreetMap waterway=dam / weir
from the Geofabrik Belgium extract (external, ODbL; also used by build_access.py). EMS features within 50 m of an
OSM one are dropped (OSM has names and the dam/weir distinction).
"""
import os, time
from pathlib import Path
import pandas as pd
import geopandas as gpd
import gcsfs, pyogrio

os.environ["GS_NO_SIGN_REQUEST"] = "YES"
G, ROOT = "/vsigs/", "datasets_challenge/working_data"
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "app_data"
PBF = BASE / "data/external/osm/geofabrik/belgium-latest.osm.pbf"
EQUAL_AREA = 3035
BUFFER_DEG = 0.03                                  # same margin as the walking network
ZONE_M = {"Dam": 300, "Weir": 100}                 # assumption: keep-away radius shown to residents
DEDUP_M = 50

t0 = time.time()
log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)
munis = gpd.read_file(OUT / "municipalities.gpkg")
w, s, e, n = munis.total_bounds
bounds = (w - BUFFER_DEG, s - BUFFER_DEG, e + BUFFER_DEG, n + BUFFER_DEG)

osm = pyogrio.read_dataframe(PBF, layer="lines", bbox=bounds, where="waterway IN ('dam', 'weir')",
                             columns=["osm_id", "name", "waterway"])
areas = pyogrio.read_dataframe(PBF, layer="multipolygons", bbox=bounds,     # large dams are often mapped as areas
                               where="other_tags LIKE '%\"waterway\"=>\"dam\"%'", columns=["osm_id", "name"])
areas["waterway"] = "dam"
osm = pd.concat([osm, areas], ignore_index=True)
osm = gpd.GeoDataFrame({"kind": osm["waterway"].map({"dam": "Dam", "weir": "Weir"}), "name": osm["name"].fillna(""),
                        "source": "OpenStreetMap"}, geometry=osm.geometry.values, crs=4326)
log(f"OSM: {len(osm):,} dams and weirs ({osm['kind'].value_counts().to_dict()})")

fs = gcsfs.GCSFileSystem(token="anon")
paths = sorted(p for p in fs.find(f"{ROOT}/ems_be") if "_MONIT01_" in p
               and p.endswith(("_facilitiesL_r1_v1.shp", "_facilitiesA_r1_v1.shp")))
ems = pd.concat([gpd.read_file(G + p) for p in paths], ignore_index=True).to_crs(4326)
ems = ems[ems["info"].str.startswith("2152")]
ems = gpd.GeoDataFrame({"kind": "Dam", "name": ems["name"].replace("Unknown", ""), "source": "Copernicus EMS"},
                       geometry=ems.geometry.values, crs=4326)
near = gpd.sjoin_nearest(ems.to_crs(EQUAL_AREA), osm.to_crs(EQUAL_AREA)[["geometry"]], max_distance=DEDUP_M, how="inner")
ems = ems.drop(index=near.index.unique())
log(f"EMS: {len(ems):,} dams not already in OSM")

dams = pd.concat([osm, ems], ignore_index=True)
dams["zone_m"] = dams["kind"].map(ZONE_M)
dams = dams.reset_index(drop=True)                 # whole bbox: upstream dams (Eupen, Gileppe) lie outside the EMS areas
dams.to_file(OUT / "dams.gpkg", driver="GPKG")
log(f"saved {len(dams):,} dams and weirs; named dams: {sorted(dams.loc[(dams['kind'] == 'Dam') & (dams['name'] != ''), 'name'].unique())[:12]}")
os._exit(0)
