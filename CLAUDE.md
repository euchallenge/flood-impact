# Flood impact card – European AI Challenge 2026

Hackathon project (FARI × JRC, Brussels, 29–30 Oct 2026) on the July 2021 floods. Deliverables: a policy tool,
a policy brief (Annex 6 template) and an AI sheet (Annex 7). Judged on evidence, policy usefulness, clarity and
responsible AI use (Annex 4). The annexes in `Annexes/` are the source of truth; don't reconstruct them from memory.

**The tool:** a flood-shelter app with two views on the same precomputed data, for a flood severity
(EFAS RP10 / RP100 / RP500, or the observed July 2021 extent from Copernicus EMS):
- **Resident view** (mobile first, static web page, planned in `resident/`): candidate shelters outside the modelled
  flood extent, reachable by a dry road, with access for persons with reduced mobility (PRM) where known.
  Location stays in the browser; nothing is stored.
- **Administration view** (Streamlit, `app/app.py`): risk per shelter and municipality, vulnerable groups, flooded roads,
  railways and networks, comparison with 2021. For mayors, emergency planning officers and governors.

Candidate shelters are not official reception centres. Never write "safe". No flood flags for individual private homes.

Repo: https://github.com/euchallenge/flood-impact (private). Plan and status: see `PLAN.md`.

## Layout
- `pipeline/build_wallonia.py` – steps 1–3: analysis areas, flood extents, buildings (about 5–7 min, reads the bucket)
- `pipeline/build_facilities.py` – step 4: shelter candidates (OSM) and EMS building categories
- `pipeline/build_population.py` – step 6: population and age, total and exposed
- `app/app.py` – Streamlit app; reads only `app_data/`, never the bucket
- `app_data/` – precomputed outputs (committed so the app runs after cloning)
- `data/external/` – external downloads (gitignored): GISCO LAU, OSM, Statbel, Eurostat census grid, OBAT docs

Deploy: admin view on Streamlit Community Cloud (`requirements.txt` is app only; pipeline uses
`requirements-pipeline.txt`). Streamlit can't run on Vercel; Vercel only serves the static `resident/` folder.

Run order: `build_wallonia.py` → `build_facilities.py both` → `build_roads.py` → `build_population.py` →
`build_quality.py`, then `python -m streamlit run app/app.py`. After rebuilding data, clear the Streamlit cache
(press C) or restart. Write parquet files only through `common.save_parquet` (temp file + swap): a direct overwrite
that fails on Windows can delete the file.

## Data
- Challenge data: public bucket `datasets_challenge/working_data` (anonymous gcsfs, GDAL `/vsigs/`). EMS EMSR518 BE
  (use the cumulative `MONIT01` products), EFAS depth RP10/100/500, GHS-OBAT BE (points, read with `bbox=` only:
  1.4 GB), GHS-POP 2020.
- OBAT codes: `use` 0 outside built-up / 1 residential / 2 non-residential; `epoch` 1 <1980, 2 1980s, 3 1990s,
  4 2000s, 5 2010s; `height` is a 100 m cell average, minimum 2.5 m.
- External: GISCO LAU 2021 (boundaries, `LAU_ID` = NIS code), OpenStreetMap via Overpass (shelter candidates;
  public servers are often overloaded, `pipeline/osm.py` caches per tile and splits failing tiles),
  Infrabel main tracks (railways, CC0, `data/external/infrabel/geosporen.geojson`),
  Eurostat Census 2021 1 km grid (age <15 / 15–64 / 65+), Statbel 2021 population by single year of age.
  Always label external data as such. No open disability data per municipality exists; 65+/80+ is the proxy.
- Known limits to keep visible: EMS 2021 extent misses most flooding in narrow urban valleys (Vesdre);
  EFAS is modelled hazard, not the 2021 event; riverside building depths may include the river channel.

## Guidelines
- Commits: one sentence, no body, no Claude co-author line. Push only when asked.
- Secrets live in `.env` (`CARTO_API_KEY`), loaded with python-dotenv; never hard-code or commit keys.
  The team Claude API key has a spending limit: never send datasets through it, only small aggregates.
- Never invent figures or column names; check the data or the annexes.
- Match the existing code style: short comments on the why, constants at the top, `log()` timings in pipelines.
- Windows quirks: set `PYTHONIOENCODING=utf-8` when printing names with accents; end pipeline scripts with
  `os._exit(0)` (gcsfs can hang on exit) and flush output first; don't redirect binary output in PowerShell.
- CARTO basemaps need `?key=`; OSM tiles may be refused by the tile server; Esri satellite needs no key.
