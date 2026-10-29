"""Step 7 of the impact-card pipeline: data-quality flags (from the review in docs/IMPROVEMENTS.md).

Run after build_wallonia.py, build_facilities.py and build_population.py. Adds flags, never drops data:
  - buildings: depth > 10 m (likely river channel or model artefact), height at the OBAT 2.5 m floor,
    depth decreasing with return period
  - municipalities: whether EFAS models any river in the mapped part; counts of flagged buildings
  - metadata.json: sources and assumptions shown in the app's "Data & limits" tab
"""
import os, json, time
from pathlib import Path
from common import save_parquet
import pandas as pd
import geopandas as gpd

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "app_data"
SUSPECT_DEPTH_M = 10                               # deeper than this in a ~90 m cell: river channel or artefact
HEIGHT_FLOOR_M = 2.5                               # OBAT lower clamp, not a measured height
DEPTHS = ["depth_rp10", "depth_rp100", "depth_rp500"]

t0 = time.time()
log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

# ---------------- buildings ----------------
b = gpd.read_parquet(OUT / "buildings.parquet")
b["depth_suspect"] = (b[DEPTHS] > SUSPECT_DEPTH_M).any(axis=1)
b["height_at_floor"] = b["height"] <= HEIGHT_FLOOR_M
b["depth_inversion"] = (b["depth_rp100"] < b["depth_rp10"]) | (b["depth_rp500"] < b["depth_rp100"])
save_parquet(b, OUT / "buildings.parquet")
log(f"buildings: {b['depth_suspect'].sum():,} depth > {SUSPECT_DEPTH_M} m, {b['height_at_floor'].mean():.1%} at the "
    f"{HEIGHT_FLOOR_M} m height floor, {b['depth_inversion'].sum():,} depth inversions")

# ---------------- municipalities ----------------
m = gpd.read_file(OUT / "municipalities.gpkg")
m["efas_modelled"] = m["rp500_km2"] > 0             # no EFAS flood cell at all: "not modelled", not "no risk"
g = b.groupby("LAU_ID")
m["buildings_depth_suspect"] = m["LAU_ID"].map(g["depth_suspect"].sum()).fillna(0).astype(int)
m["height_floor_share"] = m["LAU_ID"].map(g["height_at_floor"].mean()).fillna(0)
m.to_file(OUT / "municipalities.gpkg", driver="GPKG")
log(f"municipalities: {(~m['efas_modelled']).sum()} of {len(m)} have no EFAS-modelled river in the mapped part "
    f"({', '.join(sorted(m.loc[~m['efas_modelled'], 'name']))})")

# ---------------- metadata ----------------
meta_file = OUT / "metadata.json"
meta = json.loads(meta_file.read_text(encoding="utf-8"))
meta["efas_depth_unit"] = "metres (JRC EFAS flood hazard README v3.1.1, field D10)"
meta["assumptions"] = [
    "A building is 'in a modelled flood cell' when its OBAT centroid lies in an EFAS cell (~90 m) with depth > 0, "
    "or inside the EMS observed extent for 2021. Depths are cell values, not depths at the building.",
    "EFAS models larger rivers only: small streams and surface runoff are not covered. Where EFAS has no flood cell "
    "in a municipality, 0 means 'not modelled', not 'no risk'.",
    "EFAS maps are treated as undefended hazard: the README does not mention flood defences, and the literature "
    "(Dottori et al. 2022, ESSD) describes local defences as not represented.",
    f"Depths above {SUSPECT_DEPTH_M} m are flagged as likely river-channel cells or artefacts and left out of the "
    "deep-water counts.",
    f"OBAT heights are 100 m cell averages with a {HEIGHT_FLOOR_M} m minimum; buildings at that minimum have an "
    "uncertain height.",
    "Permanent water (EMS hydrography: rivers, lakes, reservoirs) is removed from all flood extents.",
    "The EMS 2021 extent is satellite-detected only (radar on 15 and 17 July 2021) and is a lower bound; it captured "
    "almost none of the Vesdre valley flooding.",
]
meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
log("metadata updated")
os._exit(0)
