"""Export the data of the resident web app (static site in resident/, deployed on Vercel).

Run after build_access.py. Writes compact JSON to resident/data/:
  - index.json: municipalities (id, name, bounds) and the code lists used below
  - m/<LAU_ID>.json: flood extents per scenario (simplified), candidate shelters (status, capacity, PRM per scenario)
    and the 250 m residential cells with their nearest dry shelter (walking and PRM minutes)
No population numbers per cell and no individual buildings: residents see areas and shelters only.
"""
import os, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "app_data"
OUT = BASE / "resident" / "data"
SCENARIOS = ["rp10", "rp100", "rp500", "observed_2021"]
STATUS = ["Dry: usable", "Wet: upper floors usable", "Wet: height uncertain", "Wet: not usable",
          "Dry in 2021", "Flooded in 2021"]
PRM = ["Yes (OSM)", "Limited (OSM)", "No (OSM)", "Unknown", "Upper floors only: stairs likely", "Not usable"]
CATEGORIES = ["School", "Hospital", "Church", "Stadium / sports hall"]
SIMPLIFY_DEG = 0.0001                              # ~10 m: enough for a phone map, keeps files small
PRECISION = 1e-5                                   # ~1 m coordinate rounding

t0 = time.time()
log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

munis = gpd.read_file(DATA / "municipalities.gpkg")
fac = gpd.read_file(DATA / "facilities.gpkg")
cells = gpd.read_parquet(DATA / "access.parquet")
extents = {k: gpd.read_file(DATA / "flood_extents.gpkg", layer=k) for k in SCENARIOS}
pt = fac.geometry.representative_point()
fac["lat"], fac["lon"] = pt.y.round(5), pt.x.round(5)


def geojson(gdf, props):
    feats = []
    for row in gdf.itertuples():
        g = shapely.set_precision(row.geometry.simplify(SIMPLIFY_DEG, preserve_topology=True), PRECISION)
        if not g.is_empty:
            feats.append({"type": "Feature", "properties": {p: int(getattr(row, p)) for p in props},
                          "geometry": shapely.geometry.mapping(g)})
    return {"type": "FeatureCollection", "features": feats}


def code(series, values):
    return series.map({v: i for i, v in enumerate(values)}).fillna(-1).astype(int)


for k in SCENARIOS:
    fac[f"s_{k}"], fac[f"p_{k}"] = code(fac[f"shelter_{k}"], STATUS), code(fac[f"prm_{k}"], PRM)

(OUT / "m").mkdir(parents=True, exist_ok=True)
sizes = {}
for mu in munis.itertuples():
    c = cells[cells["LAU_ID"] == mu.LAU_ID]
    used = set(c[[f"{p}shelter_{k}" for k in SCENARIOS for p in ("", "prm_")]].to_numpy().ravel()) - {-1}
    f = fac[(fac["LAU_ID"] == mu.LAU_ID) | fac.index.isin(used)]   # incl. shelters just across the border
    data = {
        "id": mu.LAU_ID, "name": mu.name, "coverage": round(mu.coverage, 2), "efas_modelled": bool(mu.rp500_km2 > 0),
        "bounds": [round(x, 5) for x in mu.geometry.bounds],
        "extents": {k: geojson(extents[k][extents[k]["LAU_ID"] == mu.LAU_ID],
                               ["depth_class"] if k != "observed_2021" else []) for k in SCENARIOS},
        # shelter: [id, name, category, lat, lon, in this municipality, {scenario: [status, capacity, prm]}]
        "shelters": [[int(i), r.name or "", CATEGORIES.index(r.category), r.lat, r.lon, r.LAU_ID == mu.LAU_ID,
                      {k: [int(getattr(r, f"s_{k}")), int(getattr(r, f"capacity_{k}")), int(getattr(r, f"p_{k}"))]
                       for k in SCENARIOS}] for i, r in zip(f.index, f.itertuples())],
        # cell: [lat, lon, {scenario: [in a flood cell, shelter id, walk min, PRM shelter id, PRM min]}]
        "cells": [[round(r.geometry.y, 5), round(r.geometry.x, 5),
                   {k: [int(getattr(r, f"pop_exposed_{k}") > 0), int(getattr(r, f"shelter_{k}")),
                        None if pd.isna(getattr(r, f"walk_min_{k}")) else round(getattr(r, f"walk_min_{k}")),
                        int(getattr(r, f"prm_shelter_{k}")),
                        None if pd.isna(getattr(r, f"prm_min_{k}")) else round(getattr(r, f"prm_min_{k}"))]
                    for k in SCENARIOS}] for r in c.itertuples()],
    }
    path = OUT / "m" / f"{mu.LAU_ID}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    sizes[mu.name] = path.stat().st_size / 1e6

index = {"municipalities": sorted([{"id": r.LAU_ID, "name": r.name, "bounds": [round(x, 4) for x in r.geometry.bounds]}
                                   for r in munis.itertuples()], key=lambda d: d["name"]),
         "status": STATUS, "prm": PRM, "categories": CATEGORIES, "scenarios": SCENARIOS,
         "sources": "Copernicus EMS, JRC EFAS, GHS-OBAT, GHS-POP (challenge data); OpenStreetMap contributors (ODbL), "
                    "Eurostat GISCO, Eurostat Census 2021, Statbel, Infrabel (external)"}
(OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
largest = sorted(sizes.items(), key=lambda x: -x[1])[:3]
log(f"wrote {len(sizes)} municipality files, {sum(sizes.values()):.1f} MB in total; largest: "
    + ", ".join(f"{n} {s:.2f} MB" for n, s in largest))
os._exit(0)
