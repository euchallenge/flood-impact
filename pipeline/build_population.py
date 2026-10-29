"""Step 6 of the impact-card pipeline: inhabitants and age, total and exposed per scenario.

Needs the outputs of build_wallonia.py (and build_facilities.py, which rewrites buildings.parquet) in app_data/.
Sources:
  - Eurostat Census 2021 1 km grid (external): population and age groups <15, 15-64, 65+ per cell
  - GHS-POP 2020 (challenge data): population per ~1 km cell, used as a second estimate
  - Statbel 2021 (external): population by single year of age per municipality, for the 80+ share
Each cell's population is split over the analysis areas by area, then over the residential OBAT buildings inside by
volume (footprint area x height). Exposed population = population of exposed buildings. The two population sources
give a low-high range.
"""
import os, time, warnings
from pathlib import Path
from common import save_parquet
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.windows import from_bounds
from shapely.geometry import box

os.environ["GS_NO_SIGN_REQUEST"] = "YES"
G, ROOT = "/vsigs/", "datasets_challenge/working_data"
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "app_data"
EXT = BASE / "data/external/demographics"
CENSUS = EXT / "eurostat_census_grid_2021_v3/ESTAT_Census_2021_V3_BE.csv"
STATBEL = EXT / "statbel_pop_struct_2021/TF_SOC_POP_STRUCT_2021.txt"
GHS_POP = G + f"{ROOT}/ghs_pop/GHS_POP_E2020_GLOBE_R2023A_4326_30ss_V1_0/GHS_POP_E2020_GLOBE_R2023A_4326_30ss_V1_0.tif"
EQUAL_AREA = 3035
AGE_COLS = {"Y_LT15": "pop_lt15", "Y_1564": "pop_15_64", "Y_GE65": "pop_65plus"}
SCENARIOS = ["rp10", "rp100", "rp500", "observed_2021"]

t0 = time.time()
log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

munis = gpd.read_file(OUT / "municipalities.gpkg")
b = gpd.read_parquet(OUT / "buildings.parquet")
areas = munis[["LAU_ID", "geometry"]].to_crs(EQUAL_AREA)


def allocate(cells, value_cols, tag):
    """Split cell values over analysis areas (by area) and then over residential buildings (by volume)."""
    cells = cells.to_crs(EQUAL_AREA)
    cells["cell_m2"] = cells.area
    pieces = gpd.overlay(cells, areas, how="intersection", keep_geom_type=True)
    frac = pieces.area / pieces["cell_m2"]
    for c in value_cols:
        pieces[c] = pieces[c] * frac
    pieces["piece"] = np.arange(len(pieces))
    # building -> piece (its cell within its municipality)
    pts = b[["LAU_ID", "use", "area", "height", "geometry"]].to_crs(EQUAL_AREA)
    j = gpd.sjoin(pts, pieces[["piece", "LAU_ID", "geometry"]], predicate="within")
    j = j[j["LAU_ID_left"] == j["LAU_ID_right"]]
    j = j[~j.index.duplicated()]
    j["w"] = j["area"] * j["height"].fillna(j["height"].median())
    has_res = j.groupby("piece")["use"].transform(lambda u: (u == 1).any())
    j.loc[has_res & (j["use"] != 1), "w"] = 0     # people live in residential buildings; others only if a piece has none
    share = j["w"] / j.groupby("piece")["w"].transform("sum")
    vals = pieces.set_index("piece").loc[j["piece"], value_cols].to_numpy() * share.to_numpy()[:, None]
    out = pd.DataFrame(vals, index=j.index, columns=[f"{c}_{tag}" for c in value_cols])
    area_totals = pieces.groupby("LAU_ID")[value_cols].sum().add_suffix(f"_{tag}_area")
    log(f"{tag}: {pieces[value_cols[0]].sum():,.0f} people in analysis areas, "
        f"{out.iloc[:, 0].sum():,.0f} allocated to buildings")
    return out, area_totals


# ---------------- Census 2021 grid ----------------
c = pd.read_csv(CENSUS)
c = c[c["GRD_ID"].str.startswith("CRS3035")]      # drops "BE_unallocated" (people without a grid location)
nE = c["GRD_ID"].str.extract(r"N(\d+)E(\d+)").astype(int)
c["geometry"] = [box(e, n, e + 1000, n + 1000) for n, e in zip(nE[0], nE[1])]
census = gpd.GeoDataFrame(c, crs=EQUAL_AREA)
census = census[census.intersects(areas.union_all())]
census[list(AGE_COLS)] = census[list(AGE_COLS)].clip(lower=0)       # -8888/-9999 = confidential / not available
census = census.rename(columns={"T": "pop", **AGE_COLS})
census_b, census_area = allocate(census[["pop", *AGE_COLS.values(), "geometry"]], ["pop", *AGE_COLS.values()], "census")

# ---------------- GHS-POP 2020 ----------------
with rasterio.open(GHS_POP) as r:
    win = from_bounds(*munis.total_bounds, transform=r.transform).round_offsets().round_lengths()
    arr = r.read(1, window=win)
    tr = r.window_transform(win)
rows, cols = np.nonzero(arr > 0)
xs, ys = rasterio.transform.xy(tr, rows, cols, offset="ul")
dx, dy = tr.a, -tr.e
ghs = gpd.GeoDataFrame({"pop": arr[rows, cols]},
                       geometry=[box(x, y - dy, x + dx, y) for x, y in zip(xs, ys)], crs=4326)
ghs_b, ghs_area = allocate(ghs, ["pop"], "ghs")

# ---------------- buildings and municipalities ----------------
b = b.drop(columns=[c for c in b.columns if c.startswith("pop_")], errors="ignore")
b = b.join(census_b).join(ghs_b)
b[list(census_b.columns) + list(ghs_b.columns)] = b[list(census_b.columns) + list(ghs_b.columns)].fillna(0).astype("float32")
save_parquet(b, OUT / "buildings.parquet")

exposed = {"observed_2021": b["flooded_2021"], **{s: b[f"depth_{s}"] > 0 for s in SCENARIOS[:3]}}
stats = pd.concat([census_area, ghs_area], axis=1)
for s, mask in exposed.items():
    g = b[mask].groupby("LAU_ID")
    for col in ["pop_census", "pop_ghs", "pop_lt15_census", "pop_15_64_census", "pop_65plus_census"]:
        stats[f"exp_{s}_{col}"] = g[col].sum()

# Statbel: whole-municipality age structure, for context and the 80+ share
s = pd.read_csv(STATBEL, sep="|", encoding="utf-8-sig", usecols=["CD_REFNIS", "CD_AGE", "MS_POPULATION"],
                dtype={"CD_REFNIS": str})
s = s[s["CD_REFNIS"].isin(munis["LAU_ID"])]
bands = pd.cut(s["CD_AGE"], [-1, 14, 64, 79, 200], labels=["0_14", "15_64", "65_79", "80plus"])
age = s.groupby(["CD_REFNIS", bands])["MS_POPULATION"].sum().unstack().add_prefix("statbel_")
age["statbel_total"] = age.sum(axis=1)
age["share_80plus"] = age["statbel_80plus"] / age["statbel_total"]
stats = stats.join(age, how="outer")

munis = munis.drop(columns=[c for c in munis.columns if c in stats.columns])
munis = munis.merge(stats, left_on="LAU_ID", right_index=True, how="left")
num = munis.select_dtypes("number").columns
munis[num] = munis[num].fillna(0)
munis.to_file(OUT / "municipalities.gpkg", driver="GPKG")

cols = ["name", "statbel_total", "pop_census_area", "pop_ghs_area", "exp_rp100_pop_census", "exp_rp100_pop_ghs",
        "exp_rp100_pop_65plus_census", "exp_observed_2021_pop_census", "share_80plus"]
pd.set_option("display.width", 250)
print(munis[cols].round(2).sort_values("exp_rp100_pop_census", ascending=False).head(15).to_string(index=False))
print("TOTAL", munis[cols[1:-1]].sum().round(0).to_dict())
log("done")
os._exit(0)
