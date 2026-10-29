"""Flood impact card: pick a Walloon municipality and a flood scenario, see what is exposed.

Reads only the precomputed files in app_data/ (built by pipeline/build_wallonia.py).
Run from the project folder:  python -m streamlit run app/app.py
"""
import os, json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import folium
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

BASE = Path(__file__).resolve().parents[1]
load_dotenv(BASE / ".env")                         # secrets (e.g. CARTO_API_KEY) stay out of the code
DATA = BASE / "app_data"
SCENARIOS = {"Frequent flood (RP10)": "rp10", "Rare flood (RP100)": "rp100",
             "Extreme flood (RP500)": "rp500", "Observed July 2021": "observed_2021"}
DEPTH_BINS = [0, 0.5, 1.5, 3, np.inf]              # same classes as the pipeline
DEPTH_LABELS = {1: "< 0.5 m", 2: "0.5–1.5 m", 3: "1.5–3 m", 4: "> 3 m"}
DEPTH_COLORS = {1: "#9ecae1", 2: "#4292c6", 3: "#2171b5", 4: "#08306b"}
OBSERVED_COLOR = "#e6550d"
MAX_POINTS = 3000                                  # keep the map responsive
CARTO_KEY = os.getenv("CARTO_API_KEY", "")         # CARTO basemaps need ?key= (otherwise "API key required" tiles)
CARTO_ATTR = "© OpenStreetMap contributors © CARTO"
BASEMAPS = {                                       # name: (tile URL, attribution); first one is shown by default
    "Light (CARTO)": (f"https://basemaps.cartocdn.com/rastertiles/light_all/{{z}}/{{x}}/{{y}}.png?key={CARTO_KEY}", CARTO_ATTR),
    "Streets (CARTO)": (f"https://basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png?key={CARTO_KEY}", CARTO_ATTR),
    "Satellite (Esri)": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                         "Tiles © Esri, Maxar, Earthstar Geographics"),
}
if not CARTO_KEY:                                  # keyless fallback: satellite only
    BASEMAPS = {k: v for k, v in BASEMAPS.items() if "CARTO" not in k}
EXPOSED_COL = {"rp10": "buildings_rp10", "rp100": "buildings_rp100", "rp500": "buildings_rp500",
               "observed_2021": "buildings_flooded_2021"}

st.set_page_config(page_title="Flood impact card", page_icon="🌊", layout="wide")


@st.cache_resource
def load():
    munis = gpd.read_file(DATA / "municipalities.gpkg")
    extents = {k: gpd.read_file(DATA / "flood_extents.gpkg", layer=k) for k in SCENARIOS.values()}
    buildings = gpd.read_parquet(DATA / "buildings.parquet")
    meta = json.loads((DATA / "metadata.json").read_text(encoding="utf-8"))
    return munis, extents, buildings, meta


if not (DATA / "metadata.json").exists():
    st.error("No data yet: run `python pipeline/build_wallonia.py` first.")
    st.stop()
munis, extents, buildings, meta = load()

# ---------------- sidebar ----------------
st.sidebar.title("🌊 Flood impact card")
label = st.sidebar.radio("Flood scenario", list(SCENARIOS))
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
lau_id = st.sidebar.selectbox("Municipality (sorted by exposure in this scenario)", list(labels),
                              format_func=labels.get)
st.sidebar.caption("⚠ = EMS mapped less than half of the municipality.")

muni = munis[munis["LAU_ID"] == lau_id].iloc[0]
name = muni["name"]
b = buildings[buildings["LAU_ID"] == muni["LAU_ID"]].copy()
b["exposed"] = b["flooded_2021"] if observed else b[f"depth_{key}"] > 0
if not observed:
    b["depth_class"] = pd.cut(b[f"depth_{key}"], DEPTH_BINS, labels=list(DEPTH_LABELS), right=True)
exp = b[b["exposed"]]

# ---------------- header & tiles ----------------
st.title(f"{name} · {label}")
if muni["coverage"] < 0.99:
    st.info(f"Copernicus EMS mapped {muni['coverage']:.0%} of {name}. All figures refer to that part only.")

flooded_km2 = muni[f"{key}_km2"]
c = st.columns(4)
c[0].metric("Flooded area", f"{flooded_km2:.2f} km²")
c[1].metric("Buildings exposed", f"{len(exp):,}", f"{len(exp) / max(len(b), 1):.1%} of buildings", delta_color="off")
if observed:
    c[2].metric("Satellite passes", "15 & 17 July 2021")
else:
    deep = (exp[f"depth_{key}"] > 1.5).sum()
    c[2].metric("Exposed with water > 1.5 m", f"{deep:,}", "ground floor submerged", delta_color="off")
c[3].metric("Exposed with unknown height", f"{exp['height'].isna().mean():.0%}" if len(exp) else "–")

# ---------------- tabs ----------------
tab_map, tab_cmp, tab_bld, tab_lim = st.tabs(["Map", "Compare with 2021", "Buildings", "Data & limits"])

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

    pts = exp.sample(min(len(exp), MAX_POINTS), random_state=0)
    layer = folium.FeatureGroup(name="Exposed buildings")
    for row in pts.itertuples():
        color = OBSERVED_COLOR if observed else DEPTH_COLORS[int(row.depth_class)]
        tip = f"height {row.height:.1f} m" if pd.notna(row.height) else "height unknown"
        if not observed:
            tip += f" · water {getattr(row, f'depth_{key}'):.1f} m"
        folium.CircleMarker([row.geometry.y, row.geometry.x], radius=2, color=color, fill=True,
                            fill_opacity=0.9, weight=0, tooltip=tip).add_to(layer)
    layer.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

    legend = ("🟧 observed flood extent" if observed else
              " · ".join(f"<span style='color:{DEPTH_COLORS[k]}'>■</span> {v}" for k, v in DEPTH_LABELS.items()))
    st.caption(legend + (f" · map shows {MAX_POINTS:,} of {len(exp):,} exposed buildings" if len(exp) > MAX_POINTS else ""),
               unsafe_allow_html=True)

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
    if flooded.sum():
        missed = {r["Scenario"]: r["Flooded in 2021 but NOT predicted"] / flooded.sum() for r in rows[:3]}
        st.markdown("**Share of buildings flooded in 2021 that each scenario missed:** " +
                    " · ".join(f"{k.split('(')[1][:-1]}: {v:.0%}" for k, v in missed.items()))
    st.caption("A modelled return period is not a forecast of the 2021 event: EFAS maps river floods, while 2021 also "
               "involved flash floods on small streams. EMS extents are snapshots at satellite pass time and can miss "
               "water that had already receded or was under trees and buildings.")

with tab_bld:
    if exp.empty:
        st.write("No exposed buildings in this scenario.")
    else:
        left, right = st.columns(2)
        if not observed:
            left.markdown("**Exposed buildings by water depth**")
            left.bar_chart(exp["depth_class"].map(DEPTH_LABELS).value_counts().reindex(DEPTH_LABELS.values()).fillna(0))
        right.markdown("**Exposed buildings by height**")
        h = pd.cut(exp["height"], [0, 3, 6, 9, 15, np.inf], labels=["≤ 3 m", "3–6 m", "6–9 m", "9–15 m", "> 15 m"])
        right.bar_chart(h.value_counts().sort_index())
        left2, right2 = st.columns(2)
        left2.markdown("**By `use` code** (meaning: OBAT documentation)")
        left2.dataframe(exp["use"].value_counts().rename("buildings"), width="stretch")
        right2.markdown("**By `epoch` code** (meaning: OBAT documentation)")
        right2.dataframe(exp["epoch"].value_counts().rename("buildings"), width="stretch")

with tab_lim:
    st.markdown(f"**Region:** {meta['region']}  \n**Observed 2021:** {meta['observed_2021_sources']}  \n"
                f"**Municipality boundaries:** {meta['municipality_boundaries']}")
    st.markdown("**Assumptions**\n" + "\n".join(f"- {a}" for a in meta["assumptions"]))
    st.markdown("**Not yet included:** schools, hospitals, roads, population and evacuation priority (next pipeline steps).")
