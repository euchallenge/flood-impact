"""Step 4 of the impact-card pipeline: shelter candidates and building categories.

Needs the outputs of build_wallonia.py in app_data/.
  - shelter candidates (schools, hospitals, churches, stadiums/sports halls) from Copernicus EMS and/or OpenStreetMap
    (external, Overpass API), with height (OBAT), EFAS depth per return period, flooded in 2021, and a shelter status
    per scenario. Usage: python build_facilities.py [ems|osm|both]   (default both; ems needs no download)
  - every OBAT building gets its EMS building category where EMS mapped one (residential, industrial, school, ...)
"""
import os, sys, json, time, warnings
from pathlib import Path
from common import save_parquet
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import geopandas as gpd
import gcsfs
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import polygonize, unary_union
import osm

os.environ["GS_NO_SIGN_REQUEST"] = "YES"
G, ROOT = "/vsigs/", "datasets_challenge/working_data"
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "app_data"
OSM_FILE = BASE / "data/external/osm/shelter_candidates_overpass.json"
EQUAL_AREA = 3035
RPS = [10, 100, 500]
FLOOR_M = 3.0                                      # assumed storey height
NODE_BUFFER_M = 15                                 # OSM points get a small footprint
NEAREST_M = 30                                     # max distance to borrow an OBAT height when none falls inside
HEIGHT_FLOOR_M = 2.5                               # OBAT clamps heights to this minimum: not a measured height
SOURCE = sys.argv[1] if len(sys.argv) > 1 else "both"   # ems | osm | both
EMS_SHELTERS = {"1263": "School", "1264": "Hospital",    # EMS info codes; sports grounds may be outdoor pitches
                "2411": "Stadium / sports hall", "2412": "Stadium / sports hall"}
CATEGORIES = {                                     # category: OSM tag values that map to it
    "School": {"amenity": ["school", "college", "university", "kindergarten"], "building": ["school"]},
    "Hospital": {"amenity": ["hospital", "clinic"], "building": ["hospital"]},
    "Church": {"amenity": ["place_of_worship"], "building": ["church", "chapel"]},
    "Stadium / sports hall": {"leisure": ["stadium", "sports_centre", "sports_hall"], "building": ["stadium", "sports_hall"]},
}

t0 = time.time()
log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

munis = gpd.read_file(OUT / "municipalities.gpkg")
buildings = gpd.read_parquet(OUT / "buildings.parquet")
extents = {k: gpd.read_file(OUT / "flood_extents.gpkg", layer=k) for k in ["observed_2021"] + [f"rp{rp}" for rp in RPS]}


# ---------------- OSM shelter candidates ----------------
def to_geometry(el):
    if el["type"] == "node":
        return Point(el["lon"], el["lat"])
    if el["type"] == "way":
        pts = [(p["lon"], p["lat"]) for p in el.get("geometry", [])]
        return Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1] else (LineString(pts) if len(pts) > 1 else None)
    lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])   # relation: rebuild outer rings
             for m in el.get("members", []) if m.get("role") == "outer" and len(m.get("geometry", [])) > 1]
    polys = list(polygonize(unary_union(lines))) if lines else []
    return unary_union(polys) if polys else None


def category(tags):
    for cat, keys in CATEGORIES.items():
        if any(tags.get(k) in vals for k, vals in keys.items()):
            return cat
    return None


def osm_candidates():
    tags = sorted({(k, v) for c in CATEGORIES.values() for k, vals in c.items() for v in vals})
    rows = []
    for el in osm.fetch(tags, munis.total_bounds, OSM_FILE, log)["elements"]:
        t = el.get("tags", {})
        cat, geom = category(t), to_geometry(el)
        if cat and geom is not None and not geom.is_empty:
            rows.append({"source_id": f"osm/{el['type']}/{el['id']}", "category": cat, "name": t.get("name", ""),
                         "religion": t.get("religion", ""), "source": "OpenStreetMap", "geometry": geom})
    gdf = gpd.GeoDataFrame(rows, crs=4326).to_crs(EQUAL_AREA)
    gdf["geometry"] = [g.buffer(NODE_BUFFER_M) if g.geom_type in ("Point", "LineString") else g.buffer(0)
                       for g in gdf.geometry]
    log(f"OSM: {len(gdf):,} candidate features")
    return gdf


def ems_candidates():
    # EMS building blocks and facility areas; no churches and no facility names in EMS
    paths = sorted(p for p in fs.find(f"{ROOT}/ems_be") if "_MONIT01_" in p
                   and p.endswith(("_builtUpA_r1_v1.shp", "_facilitiesA_r1_v1.shp")))
    ems = pd.concat([gpd.read_file(G + p) for p in paths], ignore_index=True).to_crs(4326)
    code = ems["info"].str.split("-").str[0]
    ems = ems[code.isin(EMS_SHELTERS)]
    gdf = gpd.GeoDataFrame({"source_id": "ems/" + ems.index.astype(str), "category": code[ems.index].map(EMS_SHELTERS),
                            "name": "", "religion": "", "source": "Copernicus EMS"},
                           geometry=ems.geometry.make_valid().values, crs=4326).to_crs(EQUAL_AREA)
    log(f"EMS: {len(gdf):,} candidate features")
    return gdf


fs = gcsfs.GCSFileSystem(token="anon")
fac = pd.concat([f() for src, f in [("osm", osm_candidates), ("ems", ems_candidates)] if SOURCE in (src, "both")],
                ignore_index=True)

# one feature per facility: OSM first (named), then larger before smaller; drop a feature whose centre lies inside
# an earlier one of the same category, and EMS blocks that overlap an OSM facility of the same category
fac["area_m2"] = fac.area
fac = fac.sort_values(["source", "area_m2"], ascending=[False, False]).reset_index(drop=True)   # "OpenStreetMap" first
pts = fac.set_geometry(fac.representative_point())
dup = gpd.sjoin(pts, fac[["category", "geometry"]], predicate="within")
dup = dup[(dup["category_left"] == dup["category_right"]) & (dup["index_right"] < dup.index)]
over = gpd.sjoin(fac[fac["source"] == "Copernicus EMS"], fac[fac["source"] == "OpenStreetMap"][["category", "geometry"]],
                 predicate="intersects")
over = over[over["category_left"] == over["category_right"]]
fac = fac.drop(index=dup.index.union(over.index).unique()).to_crs(4326)

# keep facilities inside the analysis areas and attach the municipality
rp_pts = fac.set_geometry(fac.representative_point())
fac = fac.join(gpd.sjoin(rp_pts, munis[["LAU_ID", "geometry"]], predicate="within")["LAU_ID"], how="inner")
fac = fac.reset_index(drop=True)
log(f"{len(fac):,} facilities after de-duplication in analysis areas "
    f"({fac.groupby(['source', 'category']).size().to_dict()})")

# ---------------- height and depth from the OBAT points ----------------
depth_cols = [f"depth_rp{rp}" for rp in RPS]
inside = gpd.sjoin(buildings[["height"] + depth_cols + ["geometry"]], fac[["geometry"]], predicate="within")
agg = inside.groupby("index_right").agg(n_obat=("height", "size"), height_m=("height", "max"),
                                         **{c: (c, "max") for c in depth_cols})
fac = fac.join(agg)
missing = fac["n_obat"].isna()                     # small OSM footprints with no OBAT centroid inside: nearest building
if missing.any():
    near = gpd.sjoin_nearest(fac[missing].to_crs(EQUAL_AREA)[["geometry"]],
                             buildings[["height"] + depth_cols + ["geometry"]].to_crs(EQUAL_AREA),
                             max_distance=NEAREST_M, how="inner")
    near = near[~near.index.duplicated()]
    fac.loc[near.index, ["height_m"] + depth_cols] = near[["height"] + depth_cols].values
    fac.loc[near.index, "n_obat"] = 0
fac["height_source"] = np.select([fac["n_obat"] > 0, fac["n_obat"] == 0], ["OBAT inside", f"nearest OBAT ≤{NEAREST_M} m"],
                                 "none")
fac["n_obat"] = fac["n_obat"].fillna(0).astype(int)
fac[depth_cols] = fac[depth_cols].fillna(0)

# ---------------- flooded or not, per scenario ----------------
for key, ext in extents.items():
    hit = gpd.sjoin(fac[["geometry"]], ext[["geometry"]], predicate="intersects").index.unique()
    col = "flooded_2021" if key == "observed_2021" else f"wet_{key}"
    fac[col] = fac.index.isin(hit)
for rp in RPS:                                     # wet = footprint touches the extent or its building has depth > 0
    fac[f"wet_rp{rp}"] |= fac[f"depth_rp{rp}"] > 0
    spare = fac["height_m"] - fac[f"depth_rp{rp}"]
    fac[f"shelter_rp{rp}"] = np.select(
        [~fac[f"wet_rp{rp}"], spare >= FLOOR_M, fac["height_m"].isna() | (fac["height_m"] <= HEIGHT_FLOOR_M)],
        ["Dry: usable", "Wet: upper floors usable", "Wet: height uncertain"], "Wet: not usable")
fac["height_at_floor"] = fac["height_m"] <= HEIGHT_FLOOR_M
fac["shelter_observed_2021"] = np.where(fac["flooded_2021"], "Flooded in 2021", "Dry in 2021")
fac["height_m"] = fac["height_m"].round(1)
fac.drop(columns="area_m2").to_file(OUT / "facilities.gpkg", driver="GPKG")
log(f"saved {len(fac):,} facilities")

# ---------------- EMS building categories for every OBAT building ----------------
paths = sorted(p for p in fs.find(f"{ROOT}/ems_be") if "_MONIT01_" in p and p.endswith("_builtUpA_r1_v1.shp"))
ems = pd.concat([gpd.read_file(G + p) for p in paths], ignore_index=True).to_crs(4326)
ems["ems_category"] = ems["obj_type"].where(ems["info"].str.startswith("997"), ems["info"]).str.split("-", n=1).str[1]
cat = gpd.sjoin(buildings[["geometry"]], ems[["ems_category", "geometry"]], predicate="within")
buildings["ems_category"] = cat[~cat.index.duplicated()]["ems_category"].reindex(buildings.index).fillna("Not mapped by EMS")
save_parquet(buildings, OUT / "buildings.parquet")
log(f"EMS categories: {buildings['ems_category'].value_counts().to_dict()}")

pd.set_option("display.width", 250)
print(pd.crosstab(fac["category"], fac["shelter_rp100"], margins=True).to_string())
print(pd.crosstab(fac["category"], fac["flooded_2021"], margins=True).to_string())
print("height source:", fac["height_source"].value_counts().to_dict())
log("done")
os._exit(0)
