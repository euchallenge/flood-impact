"""Step 9 of the impact-card pipeline: dry access to shelter candidates over the OpenStreetMap walking network.

Needs app_data/ from steps 1-8 and the Geofabrik Belgium extract (external, ODbL) at
data/external/osm/geofabrik/belgium-latest.osm.pbf (https://download.geofabrik.de/europe/belgium-latest.osm.pbf).
  - network: walkable OSM ways around the analysis areas, split into segments (cached after the first read)
  - a segment is flooded in a scenario when its midpoint lies in an EFAS cell with depth > 0, or inside the observed
    2021 extent; bridges in flooded cells count as flooded too (cautious: many were blocked by debris in 2021)
  - for each 250 m cell with residential buildings: the nearest usable shelter with capacity, reachable on dry
    segments only (walking), and the same for persons with reduced mobility (no steps, no upper-floor-only shelters)
  - shelter load: people living in flood cells assigned to each shelter, to compare with its rough capacity
"""
import os, time
from pathlib import Path
from common import save_parquet
import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio, rasterio, shapely
from rasterio.features import rasterize
from rasterio.windows import from_bounds
from pyproj import Transformer
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

os.environ["GS_NO_SIGN_REQUEST"] = "YES"
G, ROOT = "/vsigs/", "datasets_challenge/working_data"
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "app_data"
PBF = BASE / "data/external/osm/geofabrik/belgium-latest.osm.pbf"
NETWORK_FILE = BASE / "data/external/osm/walk_segments.parquet"   # cache: reading the 700 MB extract takes minutes
EQUAL_AREA = 3035
RPS = [10, 100, 500]
SCENARIOS = ["observed_2021"] + [f"rp{rp}" for rp in RPS]
CELL_M = 250
BUFFER_DEG = 0.03                                  # network margin around the analysis areas (~3 km)
NOT_WALKABLE = {"motorway", "motorway_link", "trunk", "trunk_link", "construction", "proposed", "abandoned",
                "raceway", "bus_guideway", "platform", "elevator", "corridor"}
MAX_SNAP_M = 300                                   # origin / shelter to the nearest dry network node
MAX_ROUTE_M = 15_000                               # beyond this a shelter counts as unreachable on foot
WALK_M_PER_MIN, PRM_M_PER_MIN = 75, 50             # 4.5 km/h walking, 3 km/h reduced mobility (assumptions)
USABLE = {"Dry: usable", "Wet: upper floors usable", "Dry in 2021"}

t0 = time.time()
log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)
to_m = Transformer.from_crs(4326, EQUAL_AREA, always_xy=True)

munis = gpd.read_file(OUT / "municipalities.gpkg")
fac = gpd.read_file(OUT / "facilities.gpkg")
b = gpd.read_parquet(OUT / "buildings.parquet")
w, s, e, n = munis.total_bounds
bounds = (w - BUFFER_DEG, s - BUFFER_DEG, e + BUFFER_DEG, n + BUFFER_DEG)


# ---------------- network segments (cached) ----------------
def tag(other, key):
    # value of key in GDAL's OSM 'other_tags' hstore text, e.g. "bridge"=>"yes"
    return other.str.extract(rf'"{key}"=>"([^"]*)"', expand=False)


if NETWORK_FILE.exists():
    seg = pd.read_parquet(NETWORK_FILE)
else:
    lines = pyogrio.read_dataframe(PBF, layer="lines", bbox=bounds, where="highway IS NOT NULL",
                                   columns=["osm_id", "highway", "other_tags"])
    log(f"OSM: {len(lines):,} ways with a highway tag")
    other = lines["other_tags"].fillna("")
    foot, access = tag(other, "foot"), tag(other, "access")
    walk = ~lines["highway"].isin(NOT_WALKABLE) & (foot != "no") & \
           ~(access.isin(["no", "private"]) & ~foot.isin(["yes", "designated", "permissive"]))
    lines = lines[walk].reset_index(drop=True)
    coords, idx = shapely.get_coordinates(lines.geometry.values, return_index=True)
    same = idx[1:] == idx[:-1]                     # consecutive vertices of the same way form one segment
    a, c, way = coords[:-1][same], coords[1:][same], idx[:-1][same]
    ax, ay = to_m.transform(a[:, 0], a[:, 1])
    cx, cy = to_m.transform(c[:, 0], c[:, 1])
    seg = pd.DataFrame({"ax": a[:, 0], "ay": a[:, 1], "cx": c[:, 0], "cy": c[:, 1],
                        "length_m": np.hypot(cx - ax, cy - ay).astype("float32"),
                        "highway": lines["highway"].to_numpy()[way],
                        "bridge": tag(other[walk].reset_index(drop=True), "bridge").notna().to_numpy()[way]})
    NETWORK_FILE.parent.mkdir(parents=True, exist_ok=True)
    seg.to_parquet(NETWORK_FILE)
log(f"network: {len(seg):,} walkable segments, {seg['length_m'].sum() / 1000:,.0f} km")

# nodes = shared vertices (rounded to ~0.1 m), so ways connect where they share a node
keys = np.round(np.concatenate([seg[["ax", "ay"]].to_numpy(), seg[["cx", "cy"]].to_numpy()]) * 1e6).astype(np.int64)
uniq, first, inv = np.unique(keys[:, 0] * 100_000_000 + keys[:, 1], return_index=True, return_inverse=True)
node_xy = np.concatenate([seg[["ax", "ay"]].to_numpy(), seg[["cx", "cy"]].to_numpy()])[first]
u, v = inv[:len(seg)], inv[len(seg):]
keep = u != v
seg, u, v = seg[keep].reset_index(drop=True), u[keep], v[keep]
nx_, ny_ = to_m.transform(node_xy[:, 0], node_xy[:, 1])
node_m = np.column_stack([nx_, ny_])
n_nodes = len(node_xy)
log(f"graph: {n_nodes:,} nodes")

# ---------------- flooded segments per scenario (on the EFAS grid) ----------------
mid_lon, mid_lat = (seg["ax"] + seg["cx"]).to_numpy() / 2, (seg["ay"] + seg["cy"]).to_numpy() / 2
wet = {}
with rasterio.open(G + f"{ROOT}/cems-efas/Europe_RP10_filled_depth.tif") as r:
    window = from_bounds(*bounds, transform=r.transform).round_offsets().round_lengths()
    transform = r.window_transform(window)
rows, cols = rasterio.transform.rowcol(transform, mid_lon, mid_lat)
rows, cols = np.asarray(rows), np.asarray(cols)
inside = (rows >= 0) & (rows < window.height) & (cols >= 0) & (cols < window.width)
rr, cc = rows.clip(0, window.height - 1), cols.clip(0, window.width - 1)
for rp in RPS:
    with rasterio.open(G + f"{ROOT}/cems-efas/Europe_RP{rp}_filled_depth.tif") as r:
        d = r.read(1, window=window, masked=True).filled(0)
    wet[f"rp{rp}"] = inside & (d[rr, cc] > 0)
obs = gpd.read_file(OUT / "flood_extents.gpkg", layer="observed_2021")
obs_grid = rasterize(((g, 1) for g in obs.geometry), out_shape=(window.height, window.width), transform=transform,
                     all_touched=True, dtype="uint8")
wet["observed_2021"] = inside & (obs_grid[rr, cc] > 0)
log("flooded segments: " + ", ".join(f"{k} {m.sum():,}" for k, m in wet.items()))

# ---------------- origins: 250 m cells with residential buildings ----------------
res = b[b["use"] == 1]
px, py = to_m.transform(res.geometry.x.to_numpy(), res.geometry.y.to_numpy())
cells = pd.DataFrame({"LAU_ID": res["LAU_ID"].to_numpy(), "x": px, "y": py,
                      "cell": (px // CELL_M).astype(np.int64) * 100_000 + (py // CELL_M).astype(np.int64),
                      "pop": res["pop_census"].to_numpy()})
for k in SCENARIOS:                                # people living in flood cells, per scenario
    flooded = res["flooded_2021"] if k == "observed_2021" else res[f"depth_{k}"] > 0
    cells[f"pop_exposed_{k}"] = np.where(flooded.to_numpy(), cells["pop"], 0)
cells = cells.groupby(["cell", "LAU_ID"]).agg(
    x=("x", "mean"), y=("y", "mean"), buildings=("pop", "size"), pop=("pop", "sum"),
    **{f"pop_exposed_{k}": (f"pop_exposed_{k}", "sum") for k in SCENARIOS}).reset_index()
log(f"origins: {len(cells):,} residential cells of {CELL_M} m")

fac_m = np.column_stack(to_m.transform(fac.geometry.representative_point().x.to_numpy(),
                                       fac.geometry.representative_point().y.to_numpy()))


def nearest_shelter(edge_ok, shelters):
    """Walking distance from every cell to the nearest shelter in `shelters` over edges with edge_ok."""
    graph = csr_matrix((seg["length_m"].to_numpy()[edge_ok], (u[edge_ok], v[edge_ok])), shape=(n_nodes, n_nodes))
    on_net = np.zeros(n_nodes, bool)
    on_net[u[edge_ok]] = on_net[v[edge_ok]] = True
    ids = np.flatnonzero(on_net)
    tree = cKDTree(node_m[ids])
    s_d, s_i = tree.query(fac_m[shelters], distance_upper_bound=MAX_SNAP_M)
    ok = np.isfinite(s_d)
    src_nodes, src_fac, src_snap = ids[s_i[ok]], shelters[ok], s_d[ok]
    out = pd.DataFrame(index=cells.index, data={"shelter": -1, "dist_m": np.inf})
    if len(src_nodes) == 0:
        return out
    dist, _, src = dijkstra(graph, directed=False, indices=src_nodes, min_only=True, limit=MAX_ROUTE_M,
                            return_predecessors=True)
    node_to_fac = dict(zip(src_nodes, zip(src_fac, src_snap)))   # one shelter per node is enough here
    o_d, o_i = tree.query(cells[["x", "y"]].to_numpy(), distance_upper_bound=MAX_SNAP_M)
    found = np.isfinite(o_d)
    o_nodes = ids[o_i[found]]
    d = dist[o_nodes]
    reach = np.isfinite(d)
    rows_ = np.flatnonzero(found)[reach]
    fac_snap = np.array([node_to_fac[x] for x in src[o_nodes[reach]]])
    out.loc[rows_, "shelter"] = fac_snap[:, 0].astype(int)
    out.loc[rows_, "dist_m"] = d[reach] + o_d[found][reach] + fac_snap[:, 1]
    return out


# ---------------- routing per scenario ----------------
steps = (seg["highway"] == "steps").to_numpy()
for k in SCENARIOS:
    usable = fac[f"shelter_{k}"].isin(USABLE) & (fac[f"capacity_{k}"] > 0)
    prm_ok = usable & ~fac[f"prm_{k}"].isin(["No (OSM)", "Upper floors only: stairs likely"])
    walk = nearest_shelter(~wet[k], np.flatnonzero(usable.to_numpy()))
    prm = nearest_shelter(~wet[k] & ~steps, np.flatnonzero(prm_ok.to_numpy()))
    cells[f"shelter_{k}"], cells[f"walk_min_{k}"] = walk["shelter"], (walk["dist_m"] / WALK_M_PER_MIN).round(1)
    cells[f"prm_shelter_{k}"], cells[f"prm_min_{k}"] = prm["shelter"], (prm["dist_m"] / PRM_M_PER_MIN).round(1)
    load = cells[cells[f"shelter_{k}"] >= 0].groupby(f"shelter_{k}")[f"pop_exposed_{k}"].sum()
    fac[f"load_{k}"] = fac.index.map(load).fillna(0).round().astype(int)
    exposed = cells[f"pop_exposed_{k}"]
    no_route = exposed[cells[f"shelter_{k}"] < 0].sum()
    log(f"{k}: {usable.sum():,} usable shelters; people in flood cells without a dry route within "
        f"{MAX_ROUTE_M / 1000:.0f} km: {no_route:,.0f} of {exposed.sum():,.0f}; "
        f"median walk {cells.loc[exposed > 0, f'walk_min_{k}'].replace(np.inf, np.nan).median():.0f} min")

cells = cells.replace(np.inf, np.nan)
lon, lat = Transformer.from_crs(EQUAL_AREA, 4326, always_xy=True).transform(cells["x"].to_numpy(), cells["y"].to_numpy())
save_parquet(gpd.GeoDataFrame(cells.drop(columns=["x", "y"]), geometry=gpd.points_from_xy(lon, lat), crs=4326),
             OUT / "access.parquet")
fac.to_file(OUT / "facilities.gpkg", driver="GPKG")
log("done")
os._exit(0)
