"""Flood impact card: pick a Walloon municipality and a flood scenario, see what is exposed.

Reads only the precomputed files in app_data/ (built by pipeline/build_wallonia.py).
Run from the project folder:  python -m streamlit run app/app.py
"""
import io, os, json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import folium
import streamlit as st
from dotenv import load_dotenv
from shapely.geometry import box
from streamlit_folium import st_folium

BASE = Path(__file__).resolve().parents[1]
load_dotenv(BASE / ".env")                         # secrets (e.g. CARTO_API_KEY) stay out of the code
DATA = BASE / "app_data"
SCENARIOS = {"Frequent flood (RP10)": "rp10", "Rare flood (RP100)": "rp100",
             "Extreme flood (RP500)": "rp500", "Observed July 2021": "observed_2021"}
DEPTH_BINS = [0, 0.5, 1.5, 3, np.inf]              # same classes as the pipeline
DEPTH_LABELS = {1: "≤ 0.5 m", 2: "0.5–1.5 m", 3: "1.5–3 m", 4: "> 3 m"}
DEPTH_COLORS = {1: "#9ecae1", 2: "#4292c6", 3: "#2171b5", 4: "#08306b"}
OBSERVED_COLOR = "#e6550d"
CELL_M = 250                                       # optional layer: buildings aggregated per 250 m cell
MAX_POINTS = 5000                                  # building dots on the map (a random sample above this)
ACCESS_COLORS = {"≤ 30 min walk": "#1a9850", "> 30 min walk": "#fdae61", "No dry route": "#d73027"}
USE_COLORS = {"Residential": "#e41a1c", "Non-residential": "#377eb8", "Outside built-up area": "#999999"}
SUSPECT_DEPTH_M = 10                               # deeper cells are likely river channel or artefacts (step 7)
HEIGHT_FLOOR_M = 2.5                               # OBAT minimum height: not a measured value
RESIDENT_URL = os.getenv("RESIDENT_URL", "http://localhost:8000").rstrip("/")   # Vercel URL once deployed
CARTO_KEY = os.getenv("CARTO_API_KEY", "")         # CARTO basemaps need ?key= (otherwise "API key required" tiles)
CARTO_ATTR = "© OpenStreetMap contributors © CARTO"
BASEMAPS = {                                       # name: (tile URL, attribution); first one is shown by default
    "Light (CARTO)": (f"https://basemaps.cartocdn.com/rastertiles/light_all/{{z}}/{{x}}/{{y}}.png?key={CARTO_KEY}", CARTO_ATTR),
    "Streets (CARTO)": (f"https://basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png?key={CARTO_KEY}", CARTO_ATTR),
    "Streets (OpenStreetMap)": ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", "© OpenStreetMap contributors"),
    "Satellite (Esri)": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                         "Tiles © Esri, Maxar, Earthstar Geographics"),
}
if not CARTO_KEY:                                  # keyless fallback: satellite only
    BASEMAPS = {k: v for k, v in BASEMAPS.items() if "CARTO" not in k}
USE_LABELS = {0: "Outside built-up area", 1: "Residential", 2: "Non-residential"}          # OBAT documentation
EPOCH_LABELS = {0: "Outside built-up area", 1: "Before 1980", 2: "1980–1990", 3: "1990–2000", 4: "2000–2010",
                5: "2010–2020"}
SHELTER_COLORS = {"Dry: usable": "#1a9850", "Wet: upper floors usable": "#fdae61", "Wet: not usable": "#d73027",
                  "Wet: height uncertain": "#969696", "Dry in 2021": "#1a9850", "Flooded in 2021": "#d73027"}
TRANSPORT_STYLE = {"Road": {"color": "#7b3294", "weight": 4}, "Railway": {"color": "#000000", "weight": 4,
                                                                         "dashArray": "8 4"}}
CATEGORY_ICONS = {"School": "🏫", "Hospital": "🏥", "Church": "⛪", "Stadium / sports hall": "🏟️"}
EXPOSED_COL = {"rp10": "buildings_rp10", "rp100": "buildings_rp100", "rp500": "buildings_rp500",
               "observed_2021": "buildings_flooded_2021"}

st.set_page_config(page_title="Flood impact card", page_icon="🌊", layout="wide")


@st.cache_resource
def load():
    munis = gpd.read_file(DATA / "municipalities.gpkg")
    extents = {k: gpd.read_file(DATA / "flood_extents.gpkg", layer=k) for k in SCENARIOS.values()}
    # read into memory so the running app never keeps the file open (Windows would block pipeline rewrites)
    buildings = gpd.read_parquet(io.BytesIO((DATA / "buildings.parquet").read_bytes()))
    meta = json.loads((DATA / "metadata.json").read_text(encoding="utf-8"))
    facilities = gpd.read_file(DATA / "facilities.gpkg") if (DATA / "facilities.gpkg").exists() else None
    roads = None
    if (DATA / "roads_stats.parquet").exists():
        roads = {"stats": pd.read_parquet(DATA / "roads_stats.parquet"),
                 **{k: gpd.read_file(DATA / "roads.gpkg", layer=f"flooded_{k}") for k in SCENARIOS.values()}}
    access = (gpd.read_parquet(io.BytesIO((DATA / "access.parquet").read_bytes()))
              if (DATA / "access.parquet").exists() else None)
    return munis, extents, buildings, meta, facilities, roads, access


@st.cache_data
def building_cells(lau_id, key):
    """Buildings in a flood cell aggregated to CELL_M squares: count and most common depth class."""
    b = buildings[buildings["LAU_ID"] == lau_id]
    b = b[b["flooded_2021"]] if key == "observed_2021" else b[b[f"depth_{key}"] > 0]
    if b.empty:
        return gpd.GeoDataFrame(columns=["depth_class", "tooltip", "geometry"], geometry="geometry", crs=4326)
    p = b.geometry.to_crs(3035)
    df = pd.DataFrame({"cx": (p.x // CELL_M).astype(int), "cy": (p.y // CELL_M).astype(int)})
    df["depth_class"] = 0 if key == "observed_2021" else pd.cut(
        b[f"depth_{key}"].clip(upper=SUSPECT_DEPTH_M), DEPTH_BINS, labels=list(DEPTH_LABELS)).astype(int).values
    g = df.groupby(["cx", "cy"]).agg(n=("depth_class", "size"),
                                     depth_class=("depth_class", lambda s: s.mode().iloc[0])).reset_index()
    g["tooltip"] = g["n"].astype(str) + " buildings" + ("" if key == "observed_2021" else
                                                       " · mostly " + g["depth_class"].map(DEPTH_LABELS))
    geom = [box(x * CELL_M, y * CELL_M, (x + 1) * CELL_M, (y + 1) * CELL_M) for x, y in zip(g["cx"], g["cy"])]
    return gpd.GeoDataFrame(g[["depth_class", "tooltip"]], geometry=geom, crs=3035).to_crs(4326)


if not (DATA / "metadata.json").exists():
    st.error("No data yet: run `python pipeline/build_wallonia.py` first.")
    st.stop()
munis, extents, buildings, meta, facilities, roads, access = load()
has_pop = "pop_census" in buildings.columns

# ---------------- sidebar ----------------
st.sidebar.title("🌊 Flood impact card")
if "query_applied" not in st.session_state:        # links from the resident view: ?m=<LAU_ID>&s=<scenario>
    st.session_state["query_applied"] = True
    q = st.query_params
    by_key = {v: k for k, v in SCENARIOS.items()}
    if q.get("s") in by_key:
        st.session_state["scenario_label"] = by_key[q.get("s")]
    if q.get("m") in set(munis["LAU_ID"]):
        st.session_state["lau_id"] = q.get("m")
label = st.sidebar.radio("Flood scenario", list(SCENARIOS), key="scenario_label")
key = SCENARIOS[label]
observed = key == "observed_2021"
st.sidebar.caption("RP = return period: a flood expected on average once every N years (EFAS model). "
                   "'Observed July 2021' is the extent mapped from satellite images by Copernicus EMS.")

# most exposed municipalities first, so the list itself shows where to look
share = (munis[EXPOSED_COL[key]] / munis["buildings"].where(munis["buildings"] > 0)).fillna(0)
order = munis.assign(share=share).sort_values(["share", "name"], ascending=[False, True])
labels = {r.LAU_ID: f"{r.name} · {r.share:.1%} of buildings exposed ({int(getattr(r, EXPOSED_COL[key])):,})"
                    + (f" · ⚠ {r.coverage:.0%} mapped" if r.coverage < 0.5 else "")
          for r in order.itertuples()}
# the list re-sorts per scenario, so remember the chosen municipality ourselves and keep it selected
options = list(labels)
st.session_state.setdefault("lau_id", options[0])
lau_id = st.sidebar.selectbox("Municipality (sorted by exposure in this scenario)", options,
                              index=options.index(st.session_state["lau_id"]), format_func=labels.get)
st.session_state["lau_id"] = lau_id
st.sidebar.caption("⚠ = EMS mapped less than half of the municipality.")
st.query_params.update(m=lau_id, s=key)           # shareable URL, same parameters as the resident view
st.sidebar.link_button("👥 Switch to the resident view", f"{RESIDENT_URL}/?m={lau_id}&s={key}",
                       help="Opens what residents see for this municipality and scenario", width="stretch")

muni = munis[munis["LAU_ID"] == lau_id].iloc[0]
name = muni["name"]
b = buildings[buildings["LAU_ID"] == muni["LAU_ID"]].copy()
b["exposed"] = b["flooded_2021"] if observed else b[f"depth_{key}"] > 0
if not observed:
    b["depth_class"] = pd.cut(b[f"depth_{key}"], DEPTH_BINS, labels=list(DEPTH_LABELS), right=True)
exp = b[b["exposed"]]

# ---------------- header & tiles ----------------
st.title(f"{name} · {label}")
st.caption("⚠️ Planning support, not official evacuation guidance. In an emergency call 112 and follow BE-Alert and "
           "your municipality.")
if muni["coverage"] < 0.99:
    st.info(f"Copernicus EMS mapped {muni['coverage']:.0%} of {name}. All figures refer to that part only.")
if observed:
    st.warning("Satellite-detected flooding only (radar, 15 and 17 July 2021). This is a lower bound: most of the "
               "Vesdre valley flooding was not captured.")
elif muni["rp500_km2"] == 0:
    st.warning(f"EFAS models no river in the mapped part of {name}. 0 means 'not modelled', not 'no flood risk': "
               "small streams and surface runoff are not covered.")

flooded_km2 = muni[f"{key}_km2"]
c = st.columns(4)
c[0].metric("Flooded area", f"{flooded_km2:.2f} km²")
c[1].metric("Buildings in a modelled flood cell" if not observed else "Buildings in the observed extent",
            f"{len(exp):,}", f"{len(exp) / max(len(b), 1):.1%} of buildings", delta_color="off")
if observed:
    c[2].metric("Satellite passes", "15 & 17 July 2021")
else:
    depth = exp[f"depth_{key}"]
    deep = ((depth > 1.5) & (depth <= SUSPECT_DEPTH_M)).sum()
    c[2].metric("Modelled cell depth > 1.5 m", f"{deep:,}",
                f"{(depth > SUSPECT_DEPTH_M).sum():,} more with > {SUSPECT_DEPTH_M} m (likely artefact)", delta_color="off")
uncertain = exp["height"].isna() | (exp["height"] <= HEIGHT_FLOOR_M)
c[3].metric("Height uncertain", f"{uncertain.mean():.0%}" if len(exp) else "–",
            f"at the {HEIGHT_FLOOR_M} m model floor or missing", delta_color="off")

fac = facilities[facilities["LAU_ID"] == muni["LAU_ID"]] if facilities is not None else None
status_col = f"shelter_{key}"
c = st.columns(4)
if has_pop:
    lo, hi = sorted([exp["pop_census"].sum(), exp["pop_ghs"].sum()])
    c[0].metric("People exposed", f"{lo:,.0f} – {hi:,.0f}", "Census 2021 grid / GHS-POP", delta_color="off")
    c[1].metric("Of whom aged 65+", f"{exp['pop_65plus_census'].sum():,.0f}", "Census 2021 grid", delta_color="off")
    c[2].metric("Of whom under 15", f"{exp['pop_lt15_census'].sum():,.0f}", "Census 2021 grid", delta_color="off")
if fac is not None:
    usable = fac[status_col].isin(["Dry: usable", "Wet: upper floors usable", "Dry in 2021"]).sum()
    cap = fac[f"capacity_{key}"].sum() if f"capacity_{key}" in fac else None
    c[3].metric("Shelter candidates usable", f"{usable} of {len(fac)}",
                f"rough capacity {cap:,} people" if cap is not None else "schools, hospitals, churches, sports",
                delta_color="off")

rs = wet_lines = None
if roads is not None:
    rs = roads["stats"][roads["stats"]["LAU_ID"] == muni["LAU_ID"]]
    wet_lines = roads[key][roads[key]["LAU_ID"] == muni["LAU_ID"]]
    km = rs.groupby("mode")[f"flooded_km_{key}"].sum()
    c = st.columns(4)
    c[0].metric("Main roads flooded", f"{km.get('Road', 0):.1f} km", "highways, primary, secondary", delta_color="off")
    c[1].metric("Railway lines flooded", f"{km.get('Railway', 0):.1f} km", "Infrabel lines in service", delta_color="off")

acc = None
if access is not None:
    acc = access[(access["LAU_ID"] == muni["LAU_ID"]) & (access[f"pop_exposed_{key}"] > 0)]
    if roads is None:                              # otherwise share the roads row
        c = st.columns(4)
    no_route = acc.loc[acc[f"shelter_{key}"] < 0, f"pop_exposed_{key}"].sum()
    c[2].metric("People in flood cells with no dry route", f"{no_route:,.0f}",
                f"of {acc[f'pop_exposed_{key}'].sum():,.0f} · 'go up, not out'", delta_color="off")
    walk = acc[f"walk_min_{key}"].dropna()
    c[3].metric("Median walk to a dry shelter", f"{walk.median():.0f} min" if len(walk) else "–",
                f"PRM: {acc[f'prm_min_{key}'].dropna().median():.0f} min" if acc[f"prm_min_{key}"].notna().any()
                else "PRM: no dry route", delta_color="off")

# ---------------- tabs ----------------
tab_map, tab_shel, tab_pop, tab_road, tab_cmp, tab_bld, tab_lim = st.tabs(
    ["Map", "Shelters", "Population", "Roads & rail", "Compare with 2021", "Buildings", "Data & limits"])

with tab_map:
    bounds = muni.geometry.bounds
    m = folium.Map(tiles=None)
    for i, (base, (url, attr)) in enumerate(BASEMAPS.items()):
        folium.TileLayer(url, attr=attr, name=base, overlay=False, control=True, show=i == 0).add_to(m)
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    folium.GeoJson(muni.geometry, name="Mapped part of municipality",
                   style_function=lambda f: {"color": "#333", "weight": 2, "fillOpacity": 0}).add_to(m)

    ext = extents[key][extents[key]["LAU_ID"] == muni["LAU_ID"]]
    if not ext.empty:
        if observed:
            style = lambda f: {"color": OBSERVED_COLOR, "weight": 0, "fillColor": OBSERVED_COLOR, "fillOpacity": 0.5}
        else:
            style = lambda f: {"weight": 0, "fillColor": DEPTH_COLORS[f["properties"]["depth_class"]], "fillOpacity": 0.6}
        folium.GeoJson(ext, name=f"Flood extent – {label}", style_function=style).add_to(m)

    obs = extents["observed_2021"][extents["observed_2021"]["LAU_ID"] == muni["LAU_ID"]]
    if not observed and not obs.empty:
        folium.GeoJson(obs, name="Observed July 2021 (outline)", show=False,
                       style_function=lambda f: {"color": OBSERVED_COLOR, "weight": 1.5, "fillOpacity": 0}).add_to(m)

    if not exp.empty:                              # admin view only: the resident view never shows individual homes
        pts = exp.sample(min(len(exp), MAX_POINTS), random_state=0)
        depth_txt = "" if observed else " · modelled cell depth " + pts[f"depth_{key}"].round(1).astype(str) + " m"
        dots = gpd.GeoDataFrame({"kind": pts["use"].map(USE_LABELS),
                                 "tip": pts["use"].map(USE_LABELS) + " · height "
                                        + (pts["height"].round(1).astype(str) + " m").where(pts["height"].notna(), "unknown")
                                        + depth_txt}, geometry=pts.geometry.values, crs=pts.crs)
        folium.GeoJson(dots, name="Flooded buildings (by use)",
                       marker=folium.CircleMarker(radius=3, weight=0.5, fill=True, fill_opacity=0.9),
                       style_function=lambda f: {"color": "#333", "fillColor": USE_COLORS[f["properties"]["kind"]]},
                       tooltip=folium.GeoJsonTooltip(["tip"], labels=False)).add_to(m)
    if acc is not None and not acc.empty:
        band = np.select([acc[f"shelter_{key}"] < 0, acc[f"walk_min_{key}"] > 30], ["No dry route", "> 30 min walk"],
                         "≤ 30 min walk")
        folium.GeoJson(gpd.GeoDataFrame({"band": band, "tip": band + " · " + acc[f"pop_exposed_{key}"].round().astype(int)
                                         .astype(str) + " people in flood cells"}, geometry=acc.geometry.values, crs=4326),
                       name=f"Access to a dry shelter ({CELL_M} m areas)", show=False,
                       marker=folium.CircleMarker(radius=7, weight=1, fill=True, fill_opacity=0.8),
                       style_function=lambda f: {"color": "#333", "fillColor": ACCESS_COLORS[f["properties"]["band"]]},
                       tooltip=folium.GeoJsonTooltip(["tip"], labels=False)).add_to(m)
    cells = building_cells(muni["LAU_ID"], key)
    if not cells.empty:
        folium.GeoJson(cells, name=f"Buildings in flood cells (per {CELL_M} m)", show=False,
                       style_function=lambda f: {"weight": 0.5, "color": "#555", "fillOpacity": 0.75,
                                                 "fillColor": OBSERVED_COLOR if observed
                                                 else DEPTH_COLORS[f["properties"]["depth_class"]]},
                       tooltip=folium.GeoJsonTooltip(["tooltip"], labels=False)).add_to(m)
    if wet_lines is not None and not wet_lines.empty:
        folium.GeoJson(wet_lines[["mode", "class", "name", "length_km", "geometry"]], name="Flooded roads & railways",
                       style_function=lambda f: TRANSPORT_STYLE[f["properties"]["mode"]],
                       tooltip=folium.GeoJsonTooltip(["class", "name"], aliases=["", ""])).add_to(m)
    if fac is not None and not fac.empty:
        shel = folium.FeatureGroup(name="Shelter candidates")
        for row in fac.itertuples():
            status = getattr(row, status_col)
            folium.GeoJson(row.geometry, style_function=lambda f, c=SHELTER_COLORS[status]: {
                "color": c, "weight": 2, "fillColor": c, "fillOpacity": 0.7},
                tooltip=f"{CATEGORY_ICONS[row.category]} {row.name or row.category} · {status}").add_to(shel)
            folium.Marker([row.geometry.centroid.y, row.geometry.centroid.x], tooltip=f"{row.name or row.category} · {status}",
                          icon=folium.DivIcon(html=f"<div style='font-size:18px'>{CATEGORY_ICONS[row.category]}</div>")
                          ).add_to(shel)
        shel.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

    legend = ("🟧 observed flood extent" if observed else "Modelled cell depth: " +
              " · ".join(f"<span style='color:{DEPTH_COLORS[k]}'>■</span> {v}" for k, v in DEPTH_LABELS.items()))
    dots_legend = " · ".join(f"<span style='color:{c}'>●</span> {k}" for k, c in USE_COLORS.items())
    st.caption(legend + " (flood extent)  \nFlooded buildings: " + dots_legend +
               (f" · showing {MAX_POINTS:,} of {len(exp):,}" if len(exp) > MAX_POINTS else "") +
               f" · optional layer: {CELL_M} m squares by most common depth class", unsafe_allow_html=True)

with tab_shel:
    if fac is None or fac.empty:
        st.write("No shelter candidates (schools, hospitals, churches, stadiums / sports halls) found here in OpenStreetMap.")
    else:
        st.subheader(f"Shelter candidates in {name}: {label}")
        st.markdown(" · ".join(f"<span style='color:{c}'>■</span> {s}" for s, c in SHELTER_COLORS.items()
                               if s in set(fac[status_col])), unsafe_allow_html=True)
        st.bar_chart(pd.crosstab(fac["category"], fac[status_col]).rename(columns=lambda s: s.replace(":", " –")),  # ":" breaks Altair
                     color=[SHELTER_COLORS[s] for s in sorted(set(fac[status_col]))], horizontal=True)
        table = pd.DataFrame({
            "Facility": fac["category"].map(CATEGORY_ICONS) + " " + fac["name"].replace("", "(no name)"),
            "Type": fac["category"], "Height (m)": fac["height_m"],
            **({} if observed else {"Water depth (m)": fac[f"depth_{key}"].round(1)}),
            "Status": fac[status_col],
            **({"Rough capacity": fac[f"capacity_{key}"], "PRM access": fac[f"prm_{key}"]}
               if f"capacity_{key}" in fac else {}),
            **({"Assigned people": fac[f"load_{key}"],
                "Over capacity": np.where(fac[f"load_{key}"] > fac[f"capacity_{key}"], "⚠ yes", "")}
               if f"load_{key}" in fac else {}),
            "Flooded in 2021": fac["flooded_2021"].map({True: "yes", False: "no"}),
        }).sort_values(["Status", "Type"])
        st.dataframe(table, hide_index=True, width="stretch")
        st.download_button("Download as CSV", table.to_csv(index=False).encode("utf-8"),
                           f"shelters_{name}_{key}.csv", "text/csv")
        st.caption("Dry: the footprint is outside the flood extent. Upper floors usable: building height minus water depth "
                   "is at least one 3 m storey. Heights are OBAT estimates averaged over 100 m (minimum 2.5 m), not "
                   "surveyed values. Rough capacity = largest building's footprint × up to 2 dry storeys × 50% usable ÷ "
                   "3.5 m² per person (Sphere minimum): a theoretical maximum, not an official capacity. Hospitals get "
                   "no capacity (critical sites to protect). PRM access comes from the OpenStreetMap 'wheelchair' tag "
                   "(mapped for few buildings); upper-floor shelters likely need stairs. Assigned people = residents of "
                   "flood cells whose nearest dry shelter (walking, OpenStreetMap paths with flooded segments removed) "
                   "is this one. "
                   "Facility locations: © OpenStreetMap contributors.")

with tab_pop:
    if not has_pop:
        st.write("Population not computed yet: run `python pipeline/build_population.py`.")
    else:
        st.subheader(f"Who lives in {name}?")
        total = muni["statbel_total"]
        ages = {"0–14": muni["statbel_0_14"], "15–64": muni["statbel_15_64"], "65–79": muni["statbel_65_79"],
                "80+": muni["statbel_80plus"]}
        c = st.columns(5)
        c[0].metric("Inhabitants (whole municipality)", f"{total:,.0f}", "Statbel, 1 Jan 2021", delta_color="off")
        for i, (band, n) in enumerate(ages.items(), start=1):
            c[i].metric(f"Aged {band}", f"{n:,.0f}", f"{n / total:.1%}" if total else "", delta_color="off")
        st.caption(f"In the part mapped by EMS: {muni['pop_census_area']:,.0f} (Census 2021 grid) – "
                   f"{muni['pop_ghs_area']:,.0f} (GHS-POP 2020) inhabitants.")

        st.markdown(f"**People living in exposed buildings – {label}**")
        rows = []
        for lab, k in SCENARIOS.items():
            pre = f"exp_{k}_"
            rows.append({"Scenario": lab, "People (Census grid)": muni[pre + "pop_census"],
                         "People (GHS-POP)": muni[pre + "pop_ghs"], "Under 15": muni[pre + "pop_lt15_census"],
                         "15–64": muni[pre + "pop_15_64_census"], "65+": muni[pre + "pop_65plus_census"],
                         "80+ (estimate)": muni[pre + "pop_census"] * muni["share_80plus"]})
        st.dataframe(pd.DataFrame(rows).set_index("Scenario").round(0).astype(int), width="stretch")
        st.caption("Each 1 km cell's population is split over its residential buildings by volume (footprint × height). "
                   "Age groups come from the Eurostat Census 2021 grid. 80+ is estimated with the municipality's Statbel "
                   "80+ share, assuming older residents are spread evenly. No open disability data exists at municipal "
                   "level, so the 65+ and 80+ counts are the best available proxy for people needing assistance.")

with tab_road:
    if rs is None:
        st.write("Roads not computed yet: run `python pipeline/build_roads.py`.")
    elif rs.empty:
        st.write("No main roads or railways mapped in this municipality.")
    else:
        st.subheader(f"Roads and railways under water – {label}")
        st.markdown("<span style='color:#7b3294'>━</span> road · <span style='color:#000'>╍</span> railway (on the map)",
                    unsafe_allow_html=True)
        cols = {f"flooded_km_{k}": lab for lab, k in SCENARIOS.items()}
        t = rs.set_index(["mode", "class"])[["network_km", *cols]].rename(columns={"network_km": "Network (km)", **cols})
        st.dataframe(t.round(1), width="stretch")
        if not wet_lines.empty:
            named = (wet_lines[wet_lines["name"] != ""].groupby(["mode", "class", "name"])["length_km"].sum()
                     .sort_values(ascending=False).round(2).rename("Flooded (km)").reset_index())
            st.markdown(f"**Named roads and lines affected** ({len(named)})")
            st.dataframe(named, hide_index=True, width="stretch")
        st.caption("Roads: Copernicus EMS (highways, primary and secondary roads only, no local streets). "
                   "Railways: Infrabel main tracks (CC0), one track per line, in service only. A flooded section can cut off "
                   "access to whole neighbourhoods; network connectivity is not analysed yet.")

with tab_cmp:
    st.subheader("How well does each modelled scenario match what happened in 2021?")
    flooded = b["flooded_2021"]
    rows = []
    for lab, k in list(SCENARIOS.items())[:3]:
        wet = b[f"depth_{k}"] > 0
        rows.append({"Scenario": lab, "Flooded area (km²)": round(muni[f"{k}_km2"], 2),
                     "Buildings exposed": int(wet.sum()),
                     "Flooded in 2021 and predicted": int((wet & flooded).sum()),
                     "Flooded in 2021 but NOT predicted": int((~wet & flooded).sum()),
                     "Predicted but not flooded in 2021": int((wet & ~flooded).sum())})
    rows.append({"Scenario": "Observed July 2021", "Flooded area (km²)": round(muni["observed_2021_km2"], 2),
                 "Buildings exposed": int(flooded.sum())})
    st.dataframe(pd.DataFrame(rows).set_index("Scenario"), width="stretch")
    if flooded.sum() >= 30:                        # below that a percentage is noise
        missed = {r["Scenario"]: r["Flooded in 2021 but NOT predicted"] / flooded.sum() for r in rows[:3]}
        st.markdown("**Share of buildings flooded in 2021 outside each modelled scenario:** " +
                    " · ".join(f"{k.split('(')[1][:-1]}: {v:.0%}" for k, v in missed.items()))
    elif flooded.sum():
        st.markdown(f"Only {int(flooded.sum())} buildings lie in the 2021 observed extent here: too few for a percentage.")
    st.markdown("This is **agreement between two different products**, not a validation of the model: the observed "
                "layer is a lower bound and the modelled layers ignore flood defences.")
    st.caption("A modelled return period is not a forecast of the 2021 event: EFAS maps river floods, while 2021 also "
               "involved flash floods on small streams. EMS extents are snapshots at satellite pass time and can miss "
               "water that had already receded or was under trees and buildings.")

with tab_bld:
    if exp.empty:
        st.write("No exposed buildings in this scenario.")
    else:
        left, right = st.columns(2)
        if not observed:
            left.markdown(f"**Buildings by modelled cell depth** (incl. {(exp[f'depth_{key}'] > SUSPECT_DEPTH_M).sum():,}"
                          f" with > {SUSPECT_DEPTH_M} m, likely artefacts, in '> 3 m')")
            left.bar_chart(exp["depth_class"].map(DEPTH_LABELS).value_counts().reindex(DEPTH_LABELS.values()).fillna(0))
        right.markdown("**Exposed buildings by height** (OBAT, 100 m averages)")
        h = pd.cut(exp["height"], [0, HEIGHT_FLOOR_M, 3, 6, 9, 15, np.inf],
                   labels=[f"{HEIGHT_FLOOR_M} m (model floor)", "2.5–3 m", "3–6 m", "6–9 m", "9–15 m", "> 15 m"])
        right.bar_chart(h.value_counts().sort_index())
        left2, right2 = st.columns(2)
        left2.markdown("**Exposed buildings by use** (OBAT)")
        left2.bar_chart(exp["use"].map(USE_LABELS).value_counts(), horizontal=True)
        right2.markdown("**Exposed buildings by construction period** (OBAT)")
        right2.bar_chart(exp["epoch"].map(EPOCH_LABELS).value_counts().reindex(EPOCH_LABELS.values()).dropna())
        if "ems_category" in exp.columns:
            st.markdown("**Exposed buildings by type** (Copernicus EMS building blocks, where mapped)")
            st.bar_chart(exp["ems_category"].value_counts(), horizontal=True)

with tab_lim:
    st.markdown(f"**Region:** {meta['region']}  \n**Observed 2021:** {meta['observed_2021_sources']}  \n"
                f"**Municipality boundaries:** {meta['municipality_boundaries']}")
    st.markdown("**Assumptions**\n" + "\n".join(f"- {a}" for a in meta["assumptions"]))
    st.markdown("**External sources:** shelter candidates © OpenStreetMap contributors (ODbL); "
                "railway lines Infrabel open data (CC0); "
                "Eurostat Census 2021 1 km grid (© European Union); Statbel population by age 2021 (CC BY 4.0).")
    st.markdown("**Not yet included:** vulnerable homes and evacuation priority (next pipeline steps). "
                "No open disability data per municipality was found.")
