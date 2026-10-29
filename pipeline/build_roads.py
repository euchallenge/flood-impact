"""Step 5 of the impact-card pipeline: roads and railways flooded per scenario.

Needs the outputs of build_wallonia.py in app_data/.
  - roads: Copernicus EMS transportation lines (highways, primary and secondary roads; no local streets)
  - railways: Infrabel main tracks (external, CC0, one track per line), because EMS maps railways only in AOI02
Usage: python build_roads.py [infrabel|osm|ems]   (railway source; default infrabel)
Writes app_data/roads.gpkg (network + flooded parts per scenario) and app_data/roads_stats.parquet (km per municipality),
kept apart from municipalities.gpkg so this step can run alongside the population step.
"""
import os, sys, time, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import geopandas as gpd
import gcsfs, shapely
from shapely.geometry import LineString
import osm

os.environ["GS_NO_SIGN_REQUEST"] = "YES"
G, ROOT = "/vsigs/", "datasets_challenge/working_data"
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "app_data"
OSM_FILE = BASE / "data/external/osm/railways_overpass.json"
EQUAL_AREA = 3035
SCENARIOS = ["observed_2021", "rp10", "rp100", "rp500"]
ROAD_CLASSES = {"2111": "Highway", "21120": "Primary road", "21121": "Secondary road"}   # EMS info codes
RAIL_SOURCE = sys.argv[1] if len(sys.argv) > 1 else "infrabel"   # infrabel | osm | ems (EMS: AOI02 only)
INFRABEL_FILE = BASE / "data/external/infrabel/geosporen.geojson"  # main tracks, CC0, opendata.infrabel.be
EMS_RAIL_CLASSES = {"2121": "Railway", "21220": "Tram / light rail"}
RAIL_TAGS = {"rail": "Railway", "light_rail": "Tram / light rail", "tram": "Tram / light rail",
             "narrow_gauge": "Railway"}

t0 = time.time()
log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

munis = gpd.read_file(OUT / "municipalities.gpkg")
extents = {k: gpd.read_file(OUT / "flood_extents.gpkg", layer=k) for k in SCENARIOS}


def cut(lines, polys, poly_cols):
    """Line parts inside polygons, carrying the line and polygon attributes."""
    li, pi = polys.sindex.query(lines.geometry, predicate="intersects")
    parts = gpd.GeoDataFrame(
        {**{c: lines[c].to_numpy()[li] for c in lines.columns if c != "geometry"},
         **{c: polys[c].to_numpy()[pi] for c in poly_cols}},
        geometry=shapely.intersection(lines.geometry.to_numpy()[li], polys.geometry.to_numpy()[pi]), crs=lines.crs)
    parts = parts.explode(index_parts=False)
    return parts[parts.geom_type == "LineString"].reset_index(drop=True)


# ---------------- roads (EMS) ----------------
fs = gcsfs.GCSFileSystem(token="anon")
paths = sorted(p for p in fs.find(f"{ROOT}/ems_be") if "_MONIT01_" in p and p.endswith("_transportationL_r1_v1.shp"))
ems = pd.concat([gpd.read_file(G + p) for p in paths], ignore_index=True).to_crs(4326)
roads = ems[ems["obj_type"].str.startswith("211")].copy()
roads["mode"] = "Road"
roads["class"] = roads["info"].str.split("-").str[0].map(ROAD_CLASSES).fillna("Other road")
roads["name"] = roads["name"].replace("Unknown", "")
log(f"EMS: {len(roads):,} road lines")

# ---------------- railways (Infrabel by default; OSM or EMS as alternatives) ----------------
if RAIL_SOURCE == "infrabel":
    tracks = gpd.read_file(INFRABEL_FILE)
    tracks = tracks[(tracks["exploitation"] == "In operation") & tracks.geom_type.str.contains("LineString")]
    # one track per line (track A where the line has one) so parallel tracks don't double the km
    first = tracks.groupby("linecnum")["trackname"].transform("min")
    tracks = tracks[tracks["trackname"] == first]
    rails = gpd.GeoDataFrame({"mode": "Railway", "class": "Railway", "name": "Line " + tracks["linecalfa"].astype(str)},
                             geometry=tracks.geometry.values, crs=tracks.crs).to_crs(4326)
elif RAIL_SOURCE == "osm":
    data = osm.fetch([("railway", v) for v in RAIL_TAGS], munis.total_bounds, OSM_FILE, log)
    rows = [{"mode": "Railway", "class": RAIL_TAGS[el["tags"]["railway"]], "name": el["tags"].get("name", ""),
             "geometry": LineString([(p["lon"], p["lat"]) for p in el["geometry"]])}
            for el in data["elements"]
            if el["type"] == "way" and len(el.get("geometry", [])) > 1 and "service" not in el.get("tags", {})]
    rails = gpd.GeoDataFrame(rows, crs=4326)                # sidings and yards (tagged "service") excluded above
else:
    rails = ems[ems["obj_type"].str.startswith("212")].copy()
    rails["mode"] = "Railway"
    rails["class"] = rails["info"].str.split("-").str[0].map(EMS_RAIL_CLASSES).fillna("Railway")
    rails["name"] = rails["name"].replace("Unknown", "")
    rails = rails[["mode", "class", "name", "geometry"]]
log(f"{RAIL_SOURCE.upper()}: {len(rails):,} railway lines")
(OUT / "roads.gpkg").unlink(missing_ok=True)

# ---------------- network per municipality ----------------
network = cut(pd.concat([roads[["mode", "class", "name", "geometry"]], rails], ignore_index=True), munis, ["LAU_ID"])
network["length_km"] = network.to_crs(EQUAL_AREA).length / 1000
network.to_file(OUT / "roads.gpkg", layer="network", driver="GPKG")
stats = network.groupby(["LAU_ID", "mode", "class"])["length_km"].sum().rename("network_km").to_frame()

# ---------------- flooded parts per scenario ----------------
for key in SCENARIOS:
    ext = extents[key]
    cols = ["LAU_ID"] + (["depth_class"] if "depth_class" in ext.columns else [])
    wet = cut(network.drop(columns=["LAU_ID", "length_km"]), ext, cols)
    wet["length_km"] = wet.to_crs(EQUAL_AREA).length / 1000
    wet.to_file(OUT / "roads.gpkg", layer=f"flooded_{key}", driver="GPKG")
    stats[f"flooded_km_{key}"] = wet.groupby(["LAU_ID", "mode", "class"])["length_km"].sum()
    log(f"{key}: {wet['length_km'].sum():.1f} km flooded "
        f"({wet.groupby('mode')['length_km'].sum().round(1).to_dict()})")
stats = stats.fillna(0).reset_index()
stats.to_parquet(OUT / "roads_stats.parquet")

pd.set_option("display.width", 250)
summary = stats.merge(munis[["LAU_ID", "name"]]).groupby(["name", "mode"])[
    ["network_km", "flooded_km_observed_2021", "flooded_km_rp100"]].sum().round(1)
print(summary.sort_values("flooded_km_rp100", ascending=False).head(15).to_string())
log("done")
os._exit(0)
