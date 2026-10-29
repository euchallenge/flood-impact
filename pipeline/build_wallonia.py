    """Steps 1-3 of the impact-card pipeline: Walloon municipalities covered by EMSR518.

Reads only the needed windows from the bucket and writes everything the app needs to app_data/,
so the app itself never touches the bucket.
  1. analysis areas  = Walloon LAU municipalities clipped to the EMS areas of interest
  2. flood extents   = observed 2021 (EMS) + modelled EFAS RP10/RP100/RP500, per municipality
  3. buildings       = OBAT points with municipality, EFAS depth per return period and 2021 flooded flag
"""
import os, json, time, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import geopandas as gpd
import gcsfs, rasterio
from rasterio.features import shapes
from rasterio.windows import from_bounds
from shapely.geometry import shape

os.environ.update(GS_NO_SIGN_REQUEST="YES", VSI_CACHE="TRUE", CPL_VSIL_CURL_CHUNK_SIZE="4194304")
G, ROOT = "/vsigs/", "datasets_challenge/working_data"
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "app_data"
OUT.mkdir(exist_ok=True)
LAU_FILE = BASE / "data/external/lau/LAU_RG_01M_2021_4326.parquet"
EQUAL_AREA = 3035                                  # LAEA Europe, for areas in km2
RPS = [10, 100, 500]
DEPTH_BINS = [0, 0.5, 1.5, 3, np.inf]              # map classes in metres (EFAS unit to confirm in Annex 2)
WALLOON_NIS = ("25", "5", "6", "8", "9")           # NIS prefixes: Brabant wallon, Hainaut, Liège, Luxembourg, Namur
FR_NAMES = {"Luik": "Liège", "Wezet": "Visé", "Bitsingen": "Bassenge",   # GISCO uses Dutch names for these
            "Limburg": "Limbourg", "Saint-Nicolas (Luik)": "Saint-Nicolas"}

fs = gcsfs.GCSFileSystem(token="anon")
t0 = time.time()
log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)


def ems_layer(layer):
    # MONIT01 products are cumulative: they contain the PRODUCT polygons plus the 17/07 acquisitions
    paths = sorted(p for p in fs.find(f"{ROOT}/ems_be") if "_MONIT01_" in p and p.endswith(f"_{layer}_r1_v1.shp"))
    parts = [gpd.read_file(G + p).assign(aoi="AOI" + p.split("_AOI")[1][:2]) for p in paths]
    gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs).to_crs(4326)
    gdf["geometry"] = gdf.make_valid()
    return gdf


def km2(gdf):
    return gdf.to_crs(EQUAL_AREA).area / 1e6


def per_municipality(extent, munis):
    # clip an extent layer to the analysis areas and dissolve it to one (multi)polygon per municipality
    parts = gpd.overlay(extent, munis[["LAU_ID", "geometry"]], how="intersection", keep_geom_type=True)
    return parts.dissolve(by=[c for c in parts.columns if c in ("LAU_ID", "depth_class")]).reset_index()


# ---------------- 1. analysis areas ----------------
aoi = ems_layer("areaOfInterestA")
aoi_union = aoi.union_all()
lau = gpd.read_parquet(LAU_FILE).rename_geometry("geometry").set_crs(4326, allow_override=True)
lau = lau[(lau["CNTR_CODE"] == "BE") & lau["LAU_ID"].str.startswith(WALLOON_NIS) & lau.intersects(aoi_union)].copy()
lau["name"] = lau["LAU_NAME"].replace(FR_NAMES)
lau["full_km2"] = km2(lau)
lau["geometry"] = lau.intersection(aoi_union)      # analysis area = part of the municipality that EMS mapped
lau["mapped_km2"] = km2(lau)
lau["coverage"] = lau["mapped_km2"] / lau["full_km2"]
munis = lau[lau["coverage"] >= 0.01][["LAU_ID", "name", "POP_2021", "full_km2", "mapped_km2", "coverage", "geometry"]]
munis = munis.sort_values("name").reset_index(drop=True)
log(f"step 1: {len(munis)} Walloon municipalities intersect the EMS areas")

# ---------------- 2. flood extents ----------------
observed = per_municipality(ems_layer("observedEventA")[["geometry"]], munis)
observed.to_file(OUT / "flood_extents.gpkg", layer="observed_2021", driver="GPKG")
log(f"step 2: observed 2021 extent clipped ({len(observed)} municipalities flooded)")

bounds = munis.total_bounds
efas_paths = {rp: next(p for p in fs.find(f"{ROOT}/cems-efas") if p.endswith(f"_RP{rp}_filled_depth.tif")) for rp in RPS}
depth = {}
with rasterio.open(G + efas_paths[RPS[0]]) as r:
    window = from_bounds(*bounds, transform=r.transform).round_offsets().round_lengths()
    transform = r.window_transform(window)
for rp in RPS:
    with rasterio.open(G + efas_paths[rp]) as r:
        d = r.read(1, window=window, masked=True).filled(0).astype("float32")
    depth[rp] = np.where(d > 0, d, 0)
    classes = np.digitize(depth[rp], DEPTH_BINS[1:-1], right=True).astype("uint8") + 1   # 1..4
    classes[depth[rp] == 0] = 0
    polys = [{"depth_class": int(v), "geometry": shape(g)}
             for g, v in shapes(classes, mask=classes > 0, transform=transform)]
    ext = per_municipality(gpd.GeoDataFrame(polys, crs=4326), munis)
    ext.to_file(OUT / "flood_extents.gpkg", layer=f"rp{rp}", driver="GPKG")
    log(f"step 2: EFAS RP{rp} polygonised ({(depth[rp] > 0).mean():.1%} of window cells wet)")

# ---------------- 3. buildings ----------------
obat_path = G + next(p for p in fs.find(f"{ROOT}/obat_be") if p.endswith(".gpkg"))
b = gpd.read_file(obat_path, bbox=tuple(bounds), engine="pyogrio", use_arrow=True)
log(f"step 3: {len(b):,} OBAT points read in bbox")
b = gpd.sjoin(b, munis[["LAU_ID", "geometry"]], predicate="within", how="inner").drop(columns="index_right")
rows, cols = rasterio.transform.rowcol(transform, b.geometry.x.values, b.geometry.y.values)
rows, cols = np.asarray(rows), np.asarray(cols)
inside = (rows >= 0) & (rows < window.height) & (cols >= 0) & (cols < window.width)
for rp in RPS:
    b[f"depth_rp{rp}"] = np.where(inside, depth[rp][rows.clip(0, window.height - 1), cols.clip(0, window.width - 1)], 0)
hit = gpd.sjoin(b[["geometry"]], observed[["geometry"]], predicate="within", how="inner").index
b["flooded_2021"] = b.index.isin(hit)              # building centroid inside the observed extent
b = b[["id", "LAU_ID", "use", "epoch", "height", "area", "shapefactor"] + [f"depth_rp{rp}" for rp in RPS]
      + ["flooded_2021", "geometry"]].reset_index(drop=True)
b.to_parquet(OUT / "buildings.parquet")
log(f"step 3: {len(b):,} buildings in analysis areas saved")

# ---------------- summary per municipality ----------------
g = b.groupby("LAU_ID")
stats = pd.DataFrame({"buildings": g.size(), "buildings_flooded_2021": g["flooded_2021"].sum(),
                      "height_missing_share": g["height"].apply(lambda h: h.isna().mean())})
for rp in RPS:
    stats[f"buildings_rp{rp}"] = g[f"depth_rp{rp}"].apply(lambda d: (d > 0).sum())
munis["observed_2021_km2"] = munis["LAU_ID"].map(observed.set_index("LAU_ID").pipe(km2))
for rp in RPS:
    ext = gpd.read_file(OUT / "flood_extents.gpkg", layer=f"rp{rp}")
    munis[f"rp{rp}_km2"] = munis["LAU_ID"].map(ext.assign(a=km2(ext)).groupby("LAU_ID")["a"].sum())
munis = munis.merge(stats, left_on="LAU_ID", right_index=True, how="left").fillna(0)
munis.to_file(OUT / "municipalities.gpkg", driver="GPKG")

(OUT / "metadata.json").write_text(json.dumps({
    "region": "Wallonia, municipalities intersecting EMSR518 AOI01/AOI02 (MONIT01 products)",
    "observed_2021_sources": "Sentinel-1 15/07/2021 and 17/07/2021, COSMO-SkyMed 17/07/2021 (AOI01)",
    "municipality_boundaries": "Eurostat GISCO LAU 2021 (external), clipped to EMS areas of interest",
    "efas": {f"rp{rp}": efas_paths[rp] for rp in RPS},
    "depth_classes_m": ["0-0.5", "0.5-1.5", "1.5-3", ">3"],
    "assumptions": ["building flooded/exposed = OBAT centroid inside extent / EFAS cell with depth > 0",
                    "EFAS depth unit assumed metres (check Annex 2)",
                    "permanent water bodies not yet removed from EFAS extents"],
}, indent=2, ensure_ascii=False), encoding="utf-8")

cols = ["name", "coverage", "observed_2021_km2", "rp100_km2", "buildings", "buildings_flooded_2021",
        "buildings_rp10", "buildings_rp100", "buildings_rp500", "height_missing_share"]
pd.set_option("display.width", 250)
print(munis[cols].round(2).sort_values("buildings_flooded_2021", ascending=False).to_string(index=False))
log("done")
os._exit(0)                                        # gcsfs can hang on interpreter exit on Windows
