# Flood impact card – July 2021 floods (Wallonia)

European AI Challenge 2026. Pick a municipality and a flood scenario (EFAS return period RP10 / RP100 / RP500, or the
observed July 2021 extent from Copernicus EMS) and see the flooded area and exposed buildings, compared with 2021.

## Setup
```
pip install -r requirements.txt            # app only
pip install -r requirements-pipeline.txt   # also needed to rebuild the data (adds gcsfs, rasterio)
```
Create a `.env` file in the project root (never commit it):
```
CARTO_API_KEY=<your CARTO basemaps key>
```
Without it the map falls back to satellite imagery only.

## Run
1. Optional: rebuild the data. The precomputed files are already in `app_data/`. Run the steps in this order
   (the first reads the public challenge bucket and takes about 7 minutes; the others take seconds to minutes):
   ```
   python pipeline/build_wallonia.py        # 1-3: municipalities, flood extents, buildings
   python pipeline/build_facilities.py both # 4: shelter candidates (EMS + OpenStreetMap), building categories
   python pipeline/build_roads.py           # 5: roads (EMS) and railway lines (Infrabel)
   python pipeline/build_population.py      # 6: population and age
   python pipeline/build_quality.py         # 7: data-quality flags and limits
   python pipeline/build_access.py          # 9: dry walking routes to shelters (8 runs inside build_facilities.py)
   python pipeline/build_dams.py            # dams and weirs (keep-away zones)
   python pipeline/build_risks.py           # 10: priority issues per municipality (admin view)
   python pipeline/export_resident.py       # data for the resident web app
   ```
   Stop the app first: on Windows a running app keeps `app_data/buildings.parquet` locked.
   External files to download once into `data/external/`:
   - `lau/LAU_RG_01M_2021_4326.parquet`: https://gisco-services.ec.europa.eu/distribution/v2/lau/parquet/LAU_RG_01M_2021_4326.parquet
   - `infrabel/geosporen.geojson`: https://opendata.infrabel.be/api/explore/v2.1/catalog/datasets/geosporen/exports/geojson
   - `demographics/statbel_pop_struct_2021/TF_SOC_POP_STRUCT_2021.txt`: unzip
     https://statbel.fgov.be/sites/default/files/files/opendata/bevolking%20naar%20woonplaats%2C%20nationaliteit%20burgelijke%20staat%20%2C%20leeftijd%20en%20geslacht/TF_SOC_POP_STRUCT_2021.zip
   - `demographics/eurostat_census_grid_2021_v3/ESTAT_Census_2021_V3_BE.csv`: Belgian rows of
     https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip
   - OpenStreetMap shelter candidates are downloaded automatically (cached in `data/external/osm/`).
   - `osm/geofabrik/belgium-latest.osm.pbf` (about 700 MB): https://download.geofabrik.de/europe/belgium-latest.osm.pbf
2. Start the app:
   ```
   python -m streamlit run app/app.py
   ```

## Deploy
- **Administration view (Streamlit):** Streamlit Community Cloud (share.streamlit.io), repo `euchallenge/flood-impact`,
  branch `main`, main file `app/app.py`, Python 3.13. It installs `requirements.txt` and reads `app_data/` from the repo.
  Leave the CARTO key out of the app's secrets: tile URLs carry it to every viewer's browser. Without it the map
  uses OpenStreetMap and Esri tiles.
- **Resident view (Vercel):** `vercel.json` sets the framework to "Other" and serves `resident/` as static files.
  Streamlit can't run on Vercel (no `app` ASGI/WSGI object, no WebSockets in Vercel Functions), so don't remove it:
  without it Vercel's Python preset fails on `app/app.py`. Refresh its data with `python pipeline/export_resident.py`
  after any pipeline run.
- **Switch between the two views:** each view links to the other with `?m=<LAU_ID>&s=<scenario>`.
  - Admin → resident: set `RESIDENT_URL` (the Vercel URL) in the Streamlit app's secrets or `.env`.
    Default `http://localhost:8000`.
  - Resident → admin: set `adminUrl` in `resident/config.json` (the Streamlit Cloud URL). Default
    `http://localhost:8501`; leave it empty to hide the link.
  - The admin view shows building-level data. Before sharing the resident URL publicly, either make the Streamlit
    app private (viewer access in Streamlit Cloud) or empty `adminUrl`.

## Data and limits
- Challenge data: Copernicus EMS EMSR518 (MONIT01 products), EFAS flood hazard, GHS-OBAT buildings.
- External: Eurostat GISCO LAU 2021 municipality boundaries; CARTO and Esri basemaps.
- Assumptions and known limits are listed in the app's "Data & limits" tab. Most importantly, the EMS 2021 extent
  (radar, 15 and 17 July) misses most flooding in narrow urban valleys such as the Vesdre.
