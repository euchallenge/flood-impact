# Improvement plan – Flood impact card (Wallonia, July 2021)

Built from 4 review agents (code, data, `export-upload` template, shelter research), then checked by 4 adversarial
verifiers and a completeness critic. Every number below was recomputed from `app_data/` or the challenge bucket unless
marked **(to verify)**. Challenge data, external sources and assumptions are kept apart.

## 0. Headline findings
1. **The pipeline cannot run as committed.** `pipeline/build_wallonia.py` line 1 starts with 4 spaces → `IndentationError`.
   `app_data/` cannot be rebuilt until fixed (1-minute fix).
2. **Observed 2021 vs model is the story, and also the trap.** EMS observed flooding hits only **203** of 473,524 buildings;
   EFAS RP100 puts **64,366** (13.6%) in a flooded cell. Verviers, Pepinster, Trooz, Chaudfontaine and Limbourg show **0** observed.
3. **The Vesdre gap is not a pipeline bug** (verified against the bucket and the EMS website: EMSR518 has only AOI01 Liège and
   AOI02 Rochefort, delineation only, and MONIT01 contains everything in PRODUCT). It is a limit of the EMS product:
   - **Timing and coverage:** the 15 July delineation did not cover Verviers, Pepinster or Trooz. These towns were only mapped from
     images taken in the evening of 17 July.
   - **Radar non-detection:** even where the 15 July image was used (Liège, most of Chaudfontaine), almost nothing was detected.
   - Suggested wording: *"limitation of the EMS rapid-mapping product (late acquisition in the Vesdre plus radar non-detection)"*.
     Do not write "radar missed narrow valleys" as the only cause.
4. **The jury includes the JRC**, which produces EFAS, GHSL/OBAT and runs CEMS. Do not frame "64k vs 203" as model error.
   Frame it as: *observed = lower bound, modelled = undefended hazard; the gap is the policy question.*

## 1. P0 – fix before showing anything
| # | Fix | Where | Effort |
|---|---|---|---|
| 1 | Remove the 4 leading spaces | `pipeline/build_wallonia.py:1` | 1 min |
| 2 | State the depth unit as confirmed metres (JRC EFAS README v3.1.1, field D10 "Units: meters"), not "assumed" | `build_wallonia.py:28,131`, app "Data & limits" | 10 min |
| 3 | Add a warning banner on the "Observed July 2021" scenario: "satellite-detected only; Vesdre not captured" | `app/app.py` | 20 min |
| 4 | Drop or gate the "% missed" line in the Compare tab: most municipalities have 1–9 flooded buildings, so percentages are noise. Show n, or only show it when n ≥ 30 | `app.py:155-158` | 15 min |
| 5 | Fix the "unknown height" KPI. It counts only NaN (0.8%), but **22.3%** sit at **2.5 m**, which is the documented *lower clamp* of GHS-OBAT (not a missing-value code). Label them "≤ 2.5 m (model floor)" and stop mixing them into the "≤ 3 m" bin | `app.py:96,172` | 30 min |
| 6 | Soften labels: "exposed" → "in a modelled flood cell (~90 m)"; "ground floor submerged" → "modelled cell depth > 1.5 m" | `app.py:95` | 10 min |
| 7 | Decode OBAT codes. `use`: 0 outside built-up, 1 residential, 2 non-residential. `epoch`: 1 <1980, 2 1980-90, 3 1990-2000, 4 2000-10, 5 2010-20 (GHS-OBAT doc in bucket) | `app.py:175-178` | 20 min |
| 8 | Remove the "Not yet included: schools, hospitals, roads…" promise unless you build it | `app.py:184` | 2 min |
| 9 | Make all numbers come from one source: a script exporting KPIs from `app_data` to the brief, tool and slides | new | 1 h |

## 2. Evidence and method
- **Flag spurious depths.** 853 buildings have an RP100 depth > 10 m (max 21.6 m); 830 of them lie in JRC's own "spurious depth areas" layer.
  Either mask them or flag them. (The JRC layer is an **external source**: label it as such.)
- **Permanent water** is still inside the EFAS km² and depths. The JRC permanent-water layer (external, same grid) would mask it.
  Trade-off: riverbank buildings sit in those cells too, so flag them rather than delete them.
- **EFAS covers nothing east of lon 5.94.** All RPs show 0 for Eupen, Kelmis, Lontzen, Plombières, Raeren and Welkenraedt
  (22,666 buildings). Show "no model coverage", not "0 exposed".
- **Depth monotonicity breaks** in 80 buildings (RP100 < RP10), all on permanent-water cells. Mention it in the limits.
- **EFAS undefended hazard.** Dottori et al. 2022 (ESSD) says the maps ignore local defences such as dykes. This explains Liège's high RP numbers.
  Say so on screen.
- **Add population (GHS-POP)**, the number policy makers care about most. Use `patterns.area_weighted_population` from
  export-upload. Check the GHS-POP CRS (possibly Mollweide) first. 1–2 h.
- **Fairer observed-vs-model comparison.** Rasterise EMS to the EFAS grid and report hits, misses and false alarms by area
  (`patterns.overlap_stats`), not only by building. Present it as "agreement", never as "validation".
- **RP results may be clipped to the EMS mapping area (to verify).** If so, compute RP exposure on full municipality boundaries
  and keep the clipping only for the 2021 comparison. `POP_2021` is whole-municipality, so don't mix it with the clipped area.
- **Pipeline hygiene.** Remove the global `warnings.filterwarnings("ignore")` (`build_wallonia.py:11`); read `crs=r.crs` instead of
  hard-coding 4326 (correct today, fragile later).

## 3. App, UX and deployment
- **Named actor and "so what" box** on the main screen (see §5 and §6).
- **Performance:** 3,000 `CircleMarker`s are rebuilt on every widget change. Use one `GeoJson` layer or cache the map.
- **Accessibility:** depth is shown by colour only, and observed by an emoji. Add a text table, plain labels and larger targets.
- **CARTO key ends up in the browser** (`app.py:29-30` puts it in tile URLs). Use a domain-locked key or keyless OSM/CARTO tiles,
  and never put it in an exported HTML.
- **Split `requirements.txt`** into `requirements.txt` (app) and `requirements-pipeline.txt` (gcsfs, rasterio), and pin versions.
  The app uses newer Streamlit APIs (`width="stretch"`).
- Add an `st.secrets` fallback if deploying to Streamlit Cloud.
- Small fix: depth label "< 0.5 m" should be "≤ 0.5 m" (`app.py:22`; `pd.cut` includes 0.5).

## 4. What to take from `export-upload` (include / drop)
**Recommendation: Streamlit for analysis, template for the deliverable.** The template builds one HTML file that opens by
double-click and holds no secrets. Folium is already Leaflet, so styles carry over.

| Include | Why | Effort |
|---|---|---|
| Single-HTML deliverable | emailable, offline-ish | 2–3 h (`pipeline/export_template.py`) |
| Story mode for the jury demo | 3–5 steps matching the brief's headings | 1 h |
| `area_weighted_population` | adds GHS-POP | 1–2 h |
| `overlap_stats`, `check_crs` | fair comparison, CRS safety | 1 h |
| Public edition | hosts the resident view (§5) | 3–4 h |

| Drop / don't | Why |
|---|---|
| Android app | phone install never tested, not scored |
| Full migration away from Streamlit | you lose the picker and charts |
| All 473k buildings in the HTML | 17.7 MB parquet > 15 MB layer limit. Export municipality aggregates plus exposed buildings in 2–3 story municipalities |

Known template bugs (verified):
- **`count_buildings`** silently drops NaN groups and double-counts when polygons share a `poly_id`.
- **`build_layers.py`** lets `layers.json` overwrite `data`/`type`.
- **Basemap needs internet.** The tool doesn't round coordinates.
- **Size check is incomplete.** The 15 MB check ignores inlined PNGs.

## 5. Resident perspective: "I'm looking for a shelter"
Key facts (verified):
- **No open official shelter list exists.** Reception centres sit in each municipality's emergency plan (PGUI, annex "Fiche 1.3
  Centres d'accueil"), usually confidential.
- **OSM is not usable for capacity.** Liège province has 44 `emergency=assembly_point` nodes, almost all untagged. `amenity=shelter`
  (1,584) means bus stops and picnic huts.
- **2021 shows "go up, not out" was often the only option.** Chaudfontaine decided to evacuate a zone of 1,351 homes (~1,763
  people), but access was impossible and residents were told to go upstairs (La Libre, 14/07/2021). Trooz lacked suitable
  equipment and called the army.
- **Warning failed for many.** 33% of Walloon respondents said they were never warned and 28% were warned officially
  (EGU25-15747, n=550 Belgian survey).

**Feasible in the hackathon**
1. Permanent banner: *"Not official evacuation guidance. In an emergency call 112, follow BE-Alert and your municipality."*
2. "Is my area in a flood zone?" Pick a municipality or click the map, with no address entry or storage. Show it against 2021
   observed, RP100 and RP500, plus "not mapped / no model coverage" where true.
3. **Can I go up?** (vertical evacuation proxy) Compare cell depth with OBAT height. Critic's rough count: for RP100, ~6,975
   exposed buildings have depth ≥ height (to recheck). Present it per municipality only, never per house.
4. Shelter-gap indicator per municipality: exposed population (GHS-POP) vs candidate public buildings (schools, sports and
   community centres from OSM) outside all extents. Label it a proxy with no capacity data.
5. Languages: FR and DE at minimum (Eupen, Kelmis, Lontzen and Raeren are in the 66), NL if time allows.
6. Never write "safe". Use "outside all mapped / modelled extents".

**Stretch:** straight-line distance to the nearest candidate building; a printable municipal sheet.
**Out of scope:** evacuation routes (no roads or DEM), real-time alerts, official capacities, address geocoding,
building-level risk for private homes (privacy, insurance).

## 6. Policy-maker perspective (mayors, governor, Walloon Government)
Drafted per government level (municipal, provincial/federal, regional/EU), each draft adversarially checked against official sources and `app_data`, then merged.

**Scope.** All figures cover only the part of the 66 communes that Copernicus EMS mapped (EMSR518 AOI01/02). That area spans three provinces: Liège (47 of its 84 communes), Luxembourg (13 of 44) and Namur (6 of 38). In 21 of the 66 communes, less than 50% of the area is mapped. Baelen, Stavelot, Malmedy, Huy, Dinant and Namur are not in the data.

### 6.1 Who decides what

| Actor | Level | Competence (floods/shelter) | Source |
|---|---|---|---|
| Mayor (bourgmestre) | Commune | Draws up the emergency plan (PGUI) and triggers the communal phase. Can order compulsory evacuation and assign a temporary place to stay (art. 182). Can requisition buildings and buses (art. 181). Can send BE-Alert messages. | [L07] art. 9 §4, 181, 182; [ULg] |
| Emergency planning officer (PLANU) + safety cell (D1–D5) | Commune | Prepares the PGUI and the flood plan (PPUI), including reception sites. That these sites are confidential is (to verify). | [ULg]; federal circular of 14 May 2024 |
| Municipal council | Commune | Approves the PGUI before the governor does. Confirms the mayor's emergency orders (art. 134 of the communal law). | [L07] art. 9 §4; UVCW art-1627 |
| Municipal executive (collège communal) | Commune | Building permits: can refuse or attach conditions in a flood-hazard zone (CoDT D.IV.57 3°). Manages 3rd-category streams. **Exception:** Eupen, Kelmis, Lontzen and Raeren fall under the German-speaking Community. | [CIRC]; [DG] |
| Social welfare centre (CPAS) | Commune | Rehousing. A reference address can be given with the commune's agreement. | [RR] |
| Governors of Liège, Luxembourg and Namur | Province (acting for the federal state) | Trigger and lead the provincial phase. Can send BE-Alert messages. Support communes with their PGUI (RD 2019 art. 29). Start emergency plans for dams (inquiry recommendation 106). | [INQ]; [LUX]; [BEA] |
| Interior Minister, supported by the National Crisis Centre (NCCN) | Federal | Federal phase. The NCCN runs BE-Alert. | [BEA]; PRGC 2025 |
| Rescue zones: IILE-SRI, VHP, HEMECO, Zone Luxembourg, DINAPHI, ZS5 WAL, Zone DG | Zone | Fire and rescue operations (D1). Inter-zone command is a federal procedure (recommendation 81). | [KCCE] |
| Walloon Government: Desquesnes (spatial planning, public works), Neven (housing) | Region | Flood-hazard map (AGW 4/3/2021). Flood risk plans 2022–27 (AGW 19/1/2023). €25M for buying and demolishing exposed property in 9 communes. Calamity fund. | [ALEA]; [W5] |
| CORTEX (SPW) | Region | Regional crisis centre and interface with governors and communes (decree of 13/7/2023). | [CTX] |
| SPW MI (Eupen and Gileppe dams) | Region | Dam releases (to verify). | [INQ] rec. 106 |
| Red Cross | Partner | Reception support. Formal role (to verify). | — |

Caveat: a 2024 federal draft law would repeal RD 22/05/2019. Check on ejustice whether it is in force.

### 6.2 Top decisions

**Before**
- Mayor and PLANU: where to draw the flood-plan perimeter. Are the reception sites, the crisis room and the fire posts inside the flood extent? (Recommendation 75: update the PGUI every 6 years with a shelter and evacuation plan.)
- Mayor: is the commune subscribed to BE-Alert, with messages drafted in advance? Several Vesdre communes were not subscribed in 2021 [ULg]. Which buildings and buses would be requisitioned, and where would evacuees stay?
- Governors: which communes to support first. Who coordinates across zones and provinces? The Vesdre runs through Zone DG, then VHP, then IILE-SRI. The Ourthe runs through Zone Luxembourg, then HEMECO, then IILE-SRI.
- Region: update the hazard map with 2021 evidence. The EU Floods Directive review was due 22 Dec 2025, and no revised map was found as of Oct 2026. Third flood risk plan due 22 Dec 2027.

**During**
- When to trigger the communal, provincial or federal phase.
- Whom to evacuate, and whether to send people out of the valley or upstairs.
- Which reception site to open, and which zone to target with BE-Alert.
- When dams release water, and when to ask for EU assets.

**After**
- Which buildings to inspect for stability, and which to declare uninhabitable (Walloon housing code art. 7 §3, to verify).
- How many households the CPAS must rehouse.
- Whether to rebuild with conditions or buy and demolish (the €25M envelope).

### 6.3 Tool features, ranked

**[R]** = reuses the resident/shelter view.

| # | Feature | Serves | Data | Effort | Priority |
|---|---|---|---|---|---|
| 1 | Coverage banner ("mapped part only"; the 2021 observed layer is a lower bound) | All | Current | <1h | High |
| 2 | Multi-commune triage table, filterable by province, arrondissement and rescue zone, with CSV export | Governors, CORTEX, ministers | Current + KCCE zone table | <1h | High |
| 3 | Plain labels: frequent / rare / extreme (RP10/100/500), showing that the extents are nested | Mayor, PLANU | Current | <1h | High |
| 4 | Residents in the flood extent per commune, and shelter gap **[R]** | PLANU, CPAS, governor | Needs GHS-POP | Half-day | High |
| 5 | Reception-site check: inside / within X m / outside the mapped area. Sites stay local and are not stored. **[R]** | PLANU, governor | Current + sites from the user or OSM | Half-day | High |
| 6 | Overlay of the Walloon hazard map and the SPW July 2021 flooded-zones map | Municipal executive, SPW | External WMS (to verify) | Half-day | High |
| 7 | "Layers disagree" panel (Vesdre, Theux, observed buildings outside all scenarios) | Region, governors | Current | <1h | Medium |
| 8 | Export of a draft perimeter (GeoJSON) and a one-page municipal card | PLANU, council | Current | <1h | Medium |
| 9 | Care homes, schools and campsites inside the extent **[R]** | PLANU, governor | External (OSM/AViQ) | Half-day | Medium |
| 10 | Depth guard: classes per municipality only, flag depths >10 m | All | Current | <1h | Medium |
| 11 | 2000–2020 construction inside the extent, as a pre-2021 baseline at grid-cell level | Municipal executive, SPW | Current (epoch) | <1h | Low |
| 12 | Roads, access, social vulnerability | — | External + DEM | Not feasible in the hackathon | Low |
| 13 | Forecasts, dam scenarios, € damage | — | — | — | Do not build |

### 6.4 Key numbers

All recomputed from `app_data/`. Method: count of buildings with depth_rp* > 0 in buildings.parquet, joined to municipalities.gpkg on LAU_ID.

- **64,366 of 473,524 buildings (13.6%)** are in the RP100 extent. By province (first digit of LAU_ID): Liège 56,265, Luxembourg 6,486, Namur 1,615.
- The extents are nested: **55,685 (86.5%)** are already in RP10, and RP500 adds only **3,219** (total 67,585).
- Concentration: Liège city has **26,837 (41.7%)**. 12 communes hold 80% of exposed buildings. Only 37 of the 66 communes have any.
- Vesdre five (Verviers, Pepinster, Limbourg, Chaudfontaine, Trooz): **5,521** in RP100, with **0** observed in 2021. Adding Theux (1,601) gives **7,122**.
- EMS 2021 observed layer: **203** buildings in 17 communes. **47** of them are outside every modelled scenario.
- Liège: **23,408** buildings in RP10, but **0** observed flooded in 2021. The modelled extent is likely an upper bound there (whether flood defences are modelled is unverified).
- **21 of 66** communes are less than 50% mapped (Eupen 6%, Jalhay 33%). Limbourg is 57% mapped.
- Upper Ourthe (Durbuy, Hotton, La Roche, Rendeux): **5,740** in RP100.
- **853** buildings have an RP100 depth above 10 m, likely model artefacts.

### 6.5 Recommendation options

1. **Mayors of Verviers, Pepinster, Limbourg, Trooz, Chaudfontaine and Theux:** have PLANU check every reception site and crisis post against RP100/RP500 and the SPW 2021 map, not against the satellite layer (0 observed vs 7,122 modelled).
2. **Governor of the Province of Liège, with the Governor of Luxembourg for the Ourthe:** bring the Vesdre and Ourthe mayors together to build one shared inventory of dry reception capacity outside the valley floors, sized with GHS-POP (inquiry recommendations 30 and 75).
3. **Minister Desquesnes / SPW, with CORTEX:** start the overdue hazard-map review where the EU layers and the 2021 evidence disagree.
4. **CPAS presidents of the Vesdre communes:** agree rehousing procedures in advance (reference address, modular housing), sized on residents inside the RP100 extent.

**Pick: option 2.** It names one actor who can bring several communes together, and the governor already leads cross-commune crises. Exposure crosses commune borders, so one commune's valley-floor shelters may be unusable in the same event. It links directly to the resident/shelter view (features 4 and 5), and GHS-POP can be added during the hackathon. Use "bring together" or "ask", not "require": the governor's power to impose this is unverified.

### 6.6 What NOT to show or claim

- Do not present the 203 observed buildings as the 2021 damage. The 0 in the Vesdre is a limit of the EMS product (Vesdre mapped only from 17 July images, plus radar non-detection), not an absence of flooding.
- Do not say "X buildings flood every 10 years" or "a third of Liège floods".
- No depth for individual buildings, no "ground floor submerged", and no reading of OBAT height as a number of floors.
- Do not estimate people as POP_2021 × exposed share. POP_2021 counts the whole commune.
- Do not present the EFAS extent as the legal flood zone. The Walloon hazard map is the legal reference for permits and insurance.
- Do not present totals as commune or province totals. They cover the mapped part only.
- Do not link EFAS RP500 to the 2021 "yellow zone" evacuation decision. Those zones came from the Walloon hazard map, and the witness accounts are contested.
- Do not treat epoch 4–5 as proof that land-use rules worked.
- No PGUI reception sites, no addresses, no ranking or blaming of mayors.
- No forecasts, alert triggers or € damage figures.
- Unverified, do not cite: art. 129 of the 2014 insurance law and the 18-month exclusion, the "two mayors can trigger the provincial phase" rule (that was the 2006 regime), Verified elsewhere and OK to cite with care: "161 recommendations (187 with sub-recommendations)" (Walloon Government, 17/04/2025) and "33% of Walloon respondents never warned" (EGU25-15747, Belgian survey n=550).

**Sources:**
- [L07] https://kcce.eu/sites/default/files/2007-05-15l_loi_securite_civile_-_04-2024.pdf
- [ULg] https://www.wallonie.be/sites/default/files/2021-10/annexe_b_-_organisation_de_la_gestion_de_crise_-_uliege.pdf
- [CIRC] https://territoire.wallonie.be/storage/territoire/documents/content/page/inondations/circulaireinondations-231221.pdf
- [INQ] https://www.wallonie.be/sites/default/files/2022-11/Inondations%20rapport%20de%20la%20commission%20parlementaire.pdf
- [W5] https://wallonie.be/fr/actualites/5-ans-apres-les-inondations-de-2021-ou-en-est
- [ALEA] https://wallonie.be/fr/demarches/sinformer-sur-la-carte-de-lalea-dinondation-en-wallonie
- [BEA] https://www.be-alert.be/en/how-does-be-alert-work/which-emergency-situations-will-i-receive-message
- [KCCE] https://kcce.eu/sites/default/files/2009-02-02r_zones_de_secours_-_07-2024.pdf
- [RR] https://www.rijksregister.fgov.be/sites/default/files/documents/fr/population/circulaires/Circulaire_27072021.pdf
- [DG] https://uvcw.be/amenagement-territoire/actus/art-2496
- [CTX] https://spw.wallonie.be/sites/default/files/2024-07/Communique%20Presse_CORTEX_FR.%2818.04.2024%29pdf.pdf
- [LUX] https://gouverneur-luxembourg.be/wp-content/uploads/2022/04/20220425_Plaquette-bourgmestres_avec-couverture.pdf

## 7. Responsible AI and AI sheet
- **Pre-event prep.** Check Annex 3 on whether it is allowed. `export-upload/template/TEMPLATE-NOTE.md` already discloses it
  (personal account, built the day before). Update "phone install: not yet tested".
- **Event-day AI work** needs its own AI sheet lines: both repo commits are co-authored by Claude. Keep a running log
  (prompt → output → how checked).
- **Team number.** Use one consistently across commits, the brief and the AI sheet (they currently differ).
- **Sources.** Credit GISCO LAU, the JRC layers (permanent water, spurious depth), OSM (ODbL), Leaflet, Esri/CARTO and
  SPW (licence per dataset record) as **external** sources, separate from challenge data.
- **Statistics.** Fill each number's "how checked" line with an independent recount by a second team member.

## 8. Explicitly NOT doing
- Present EMS-vs-EFAS as model validation or accuracy.
- Invent shelters, capacities, warning lead times or evacuee totals. No open Wallonia-wide evacuee total was found.
- Draw evacuation routes.
- Publish building-level flood flags for private homes.
- Keep working on Android, or expand to DE/NL on day 1. Cross-border (Geul → NL; `ems_de`, `ems_nl` in the bucket) is a "next step" line.
- Put the CARTO key in the HTML, or send datasets through the team API key.

## 9. Demo-day plan
- Present from the story-mode HTML. Keep Streamlit as backup.
- Record a fallback video and screenshots (basemaps need internet).
- Story steps = brief headings = one named actor = one measurable action.

## Sources (verified)
- EMS EMSR518: https://mapping.emergency.copernicus.eu/activations/EMSR518
- JRC EFAS flood hazard README v3.1.1: https://jeodpp.jrc.ec.europa.eu/ftp/public/JRC-OpenData/CEMS-EFAS/flood_hazard/README.txt
- Dottori et al. 2022, ESSD 14:1549: https://essd.copernicus.org/articles/14/1549/2022/
- La Libre live, 14/07/2021 (Chaudfontaine, Trooz): https://www.lalibre.be/belgique/societe/2021/07/14/intemperies-en-belgique-leau-ne-cesse-de-monter-des-habitants-de-certaines-communes-evacues-avec-laide-de-larmee-direct-KUHBIYMOSVEZJFUW66BUQL2EXY/
- L'Avenir, 15/07/2021 (Grivegnée, >1,000 received by that evening): https://www.lavenir.net/cnt/dmf20210715_01597896/plus-de-1-000-liegeois-accueillis-au-centre-de-crise-de-grivegnee-la-situation-dans-les-quartiers-du-centre-ville-liegeois-stable-a-21h
- La Libre, 22/10/2021 (Verviers alert email): https://www.lalibre.be/regions/liege/2021/10/22/commission-inondations-a-verviers-la-bourgmestre-faisant-fonction-na-pas-recu-le-mail-dalerte-provinciale-YCCOQBCUHJH7HBKHR5LERBO3UQ/
- EGU25-15747 (warning survey): https://meetingorganizer.copernicus.org/EGU25/EGU25-15747.html
- Walloon Government, July 2022 review (39 deaths, 100,000 affected): https://www.wallonie.be/sites/default/files/2022-07/%5BCP%5D%20-%20Inondations%20de%20juillet%202021%20-%20Bilan%20et%20perspectives.pdf
- Walloon Government, 17/04/2025 (161 recommendations, 187 with sub-points): https://wallonie.be/fr/acteurs-et-institutions/wallonie/gouvernement-de-wallonie/communiques-presse/2025-04-17
- UVCW on emergency planning (Royal Decree 22 May 2019): https://www.uvcw.be/police/focus/art-2292
- SPW flood hazard service: https://geoservices.wallonie.be/arcgis/rest/services/EAU/ALEA_INOND/MapServer
