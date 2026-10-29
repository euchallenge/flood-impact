# Flood impact card – July 2021 floods (Wallonia)

European AI Challenge 2026. Pick a municipality and a flood scenario (EFAS return period RP10 / RP100 / RP500, or the
observed July 2021 extent from Copernicus EMS) and see the flooded area and exposed buildings, compared with 2021.

## Setup
```
pip install -r requirements.txt
```
Create a `.env` file in the project root (never commit it):
```
CARTO_API_KEY=<your CARTO basemaps key>
```
Without it the map falls back to satellite imagery only.

## Run
1. Optional: rebuild the data. The precomputed files are already in `app_data/`; the pipeline reads the public
   challenge bucket and takes about 7 minutes:
   ```
   python pipeline/build_wallonia.py
   ```
   It also needs the Eurostat GISCO LAU 2021 boundaries at `data/external/lau/LAU_RG_01M_2021_4326.parquet`
   (from https://gisco-services.ec.europa.eu/distribution/v2/lau/parquet/LAU_RG_01M_2021_4326.parquet).
2. Start the app:
   ```
   python -m streamlit run app/app.py
   ```

## Data and limits
- Challenge data: Copernicus EMS EMSR518 (MONIT01 products), EFAS flood hazard, GHS-OBAT buildings.
- External: Eurostat GISCO LAU 2021 municipality boundaries; CARTO and Esri basemaps.
- Assumptions and known limits are listed in the app's "Data & limits" tab. Most importantly, the EMS 2021 extent
  (radar, 15 and 17 July) misses most flooding in narrow urban valleys such as the Vesdre.
