// Resident view: nearest candidate shelter reachable by a dry route. Static: all data comes from data/*.json.
// The location (tap or GPS) never leaves the browser; only map tiles and the JSON files are requested.
"use strict";

const T = {
  fr: {
    title: "Abri en cas d'inondation", adminView: "Vue administration", notOfficial: "Pas une consigne officielle d'évacuation.",
    call112: "En cas d'urgence : appelez le 112 et suivez BE-Alert et votre commune.",
    muniLabel: "Votre commune", locate: "Me localiser", tapHint: "Ou touchez la carte à l'endroit où vous êtes.",
    scenarioLabel: "Quelle inondation ?", rp10: "Fréquente (≈ tous les 10 ans)", rp100: "Rare (≈ tous les 100 ans)",
    rp500: "Extrême (≈ tous les 500 ans)", observed: "Juillet 2021 (observée)",
    prmLabel: "Mobilité réduite (pas d'escaliers)",
    prmMode: "Mode mobilité réduite : itinéraires sans escaliers, abris de plain-pied uniquement (les autres sont grisés).",
    footerCandidates: "Les abris proposés sont des bâtiments publics candidats (écoles, églises, salles de sport), pas les centres d'accueil officiels de votre commune. Capacité et ouverture non garanties.",
    footerPrivacy: "Votre position reste sur votre appareil : rien n'est envoyé ni enregistré.",
    choose: "Choisissez votre commune, puis touchez la carte ou utilisez « Me localiser ».",
    inFlood: "Votre zone est dans l'emprise d'inondation modélisée.",
    outFlood: "Votre zone est hors de l'emprise d'inondation modélisée (ce n'est pas une garantie).",
    inFlood2021: "Votre zone a été inondée selon les images satellite de juillet 2021.",
    outFlood2021: "Votre zone n'apparaît pas inondée sur les images satellite de juillet 2021, qui en ont manqué beaucoup (vallée de la Vesdre).",
    notModelled: "Le modèle ne couvre aucune rivière dans cette commune : il ne peut pas évaluer votre risque (petits ruisseaux et ruissellement non modélisés).",
    nearest: "Abri candidat le plus proche par un chemin au sec", walk: "à pied", min: "min",
    upper: "Rez-de-chaussée inondé : utiliser les étages.", dry: "Bâtiment hors de l'emprise inondée.",
    capacity: "Capacité estimée", people: "personnes (estimation grossière)",
    prmYes: "Accès PMR indiqué (OpenStreetMap).", prmLimited: "Accès PMR limité (OpenStreetMap).", prmUnknown: "Accès PMR inconnu.",
    noRouteFlood: "Aucun chemin au sec trouvé depuis votre zone. Montez à un étage supérieur et appelez le 112 si vous êtes en danger.",
    noRouteDry: "Aucun abri candidat accessible par un chemin au sec dans un rayon de 15 km.",
    others: "Autres abris candidats proches (à vol d'oiseau, chemin non vérifié)",
    line: "La ligne pointillée bleue est la ligne droite vers l'abri, pas un itinéraire.",
    routeShown: "Ligne verte : itinéraire à pied qui évite les tronçons inondés modélisés (chemins OpenStreetMap). Suivez toujours les consignes sur place.",
    routeOnlyInFlood: "Votre zone est hors de l'emprise inondée : seule la ligne droite est affichée.",
    noCell: "Pas de données d'habitation ici. Touchez un endroit plus proche des maisons.",
    outside: "Ce lieu est hors de la zone couverte par l'application.",
    gpsError: "Localisation impossible. Touchez la carte à la place.",
    legendDepth: "Profondeur modélisée", legendObserved: "Inondé en 2021 (satellite)",
    legendDry: "Abri candidat au sec", legendUpper: "Étages utilisables", legendNo: "Non utilisable",
    legendDam: "Barrage / seuil : zone à éviter", dam: "Barrage", weir: "Seuil (déversoir)",
    damZone: "à éviter en cas de crue (lâchers d'eau, courant violent, débris). Ne vous en approchez pas.",
    cat: ["École", "Hôpital", "Église", "Salle de sport / stade"],
  },
  de: {
    title: "Schutz bei Hochwasser", adminView: "Verwaltungsansicht", notOfficial: "Keine offizielle Evakuierungsanweisung.",
    call112: "Im Notfall: 112 anrufen und BE-Alert sowie Ihrer Gemeinde folgen.",
    muniLabel: "Ihre Gemeinde", locate: "Mich orten", tapHint: "Oder tippen Sie auf die Karte, wo Sie sind.",
    scenarioLabel: "Welches Hochwasser?", rp10: "Häufig (≈ alle 10 Jahre)", rp100: "Selten (≈ alle 100 Jahre)",
    rp500: "Extrem (≈ alle 500 Jahre)", observed: "Juli 2021 (beobachtet)",
    prmLabel: "Eingeschränkte Mobilität (keine Treppen)",
    prmMode: "Modus eingeschränkte Mobilität: Wege ohne Treppen, nur ebenerdige Schutzorte (andere sind grau).",
    footerCandidates: "Die vorgeschlagenen Orte sind öffentliche Gebäude (Schulen, Kirchen, Sporthallen), nicht die offiziellen Aufnahmezentren Ihrer Gemeinde. Kapazität und Öffnung nicht garantiert.",
    footerPrivacy: "Ihr Standort bleibt auf Ihrem Gerät: nichts wird gesendet oder gespeichert.",
    choose: "Wählen Sie Ihre Gemeinde, dann tippen Sie auf die Karte oder nutzen Sie „Mich orten“.",
    inFlood: "Ihr Gebiet liegt in der modellierten Überflutungsfläche.",
    outFlood: "Ihr Gebiet liegt außerhalb der modellierten Überflutungsfläche (keine Garantie).",
    inFlood2021: "Ihr Gebiet war laut Satellitenbildern vom Juli 2021 überflutet.",
    outFlood2021: "Ihr Gebiet erscheint auf den Satellitenbildern vom Juli 2021 nicht überflutet; diese haben vieles verpasst (Wesertal).",
    notModelled: "Das Modell erfasst in dieser Gemeinde keinen Fluss: Ihr Risiko kann nicht bewertet werden (kleine Bäche und Oberflächenabfluss nicht modelliert).",
    nearest: "Nächster möglicher Schutzort über einen trockenen Weg", walk: "zu Fuß", min: "Min.",
    upper: "Erdgeschoss überflutet: obere Etagen nutzen.", dry: "Gebäude außerhalb der Überflutungsfläche.",
    capacity: "Geschätzte Kapazität", people: "Personen (grobe Schätzung)",
    prmYes: "Barrierefrei laut OpenStreetMap.", prmLimited: "Eingeschränkt barrierefrei (OpenStreetMap).", prmUnknown: "Barrierefreiheit unbekannt.",
    noRouteFlood: "Kein trockener Weg von Ihrem Gebiet gefunden. Gehen Sie in ein oberes Stockwerk und rufen Sie 112 an, wenn Sie in Gefahr sind.",
    noRouteDry: "Kein möglicher Schutzort über einen trockenen Weg im Umkreis von 15 km.",
    others: "Weitere mögliche Schutzorte in der Nähe (Luftlinie, Weg nicht geprüft)",
    line: "Die blaue gestrichelte Linie ist die Luftlinie zum Schutzort, kein Weg.",
    routeShown: "Grüne Linie: Fußweg, der die modellierten überfluteten Abschnitte meidet (OpenStreetMap-Wege). Folgen Sie immer den Anweisungen vor Ort.",
    routeOnlyInFlood: "Ihr Gebiet liegt außerhalb der Überflutungsfläche: nur die Luftlinie wird angezeigt.",
    noCell: "Hier keine Wohndaten. Tippen Sie näher an Häuser.",
    outside: "Dieser Ort liegt außerhalb des abgedeckten Gebiets.",
    gpsError: "Ortung nicht möglich. Tippen Sie stattdessen auf die Karte.",
    legendDepth: "Modellierte Tiefe", legendObserved: "2021 überflutet (Satellit)",
    legendDry: "Möglicher Schutzort, trocken", legendUpper: "Obere Etagen nutzbar", legendNo: "Nicht nutzbar",
    legendDam: "Talsperre / Wehr: meiden", dam: "Talsperre", weir: "Wehr",
    damZone: "bei Hochwasser meiden (Wasserabgaben, starke Strömung, Treibgut). Nicht nähern.",
    cat: ["Schule", "Krankenhaus", "Kirche", "Sporthalle / Stadion"],
  },
  en: {
    title: "Flood shelter finder", adminView: "Administration view", notOfficial: "Not official evacuation guidance.",
    call112: "In an emergency call 112 and follow BE-Alert and your municipality.",
    muniLabel: "Your municipality", locate: "Locate me", tapHint: "Or tap the map where you are.",
    scenarioLabel: "Which flood?", rp10: "Frequent (≈ every 10 years)", rp100: "Rare (≈ every 100 years)",
    rp500: "Extreme (≈ every 500 years)", observed: "July 2021 (observed)",
    prmLabel: "Reduced mobility (no stairs)",
    prmMode: "Reduced-mobility mode: routes without steps, ground-level shelters only (others are greyed out).",
    footerCandidates: "Suggested places are candidate public buildings (schools, churches, sports halls), not your municipality's official reception centres. Capacity and opening are not guaranteed.",
    footerPrivacy: "Your location stays on your device: nothing is sent or stored.",
    choose: "Choose your municipality, then tap the map or use “Locate me”.",
    inFlood: "Your area is inside the modelled flood extent.",
    outFlood: "Your area is outside the modelled flood extent (this is not a guarantee).",
    inFlood2021: "Your area was flooded according to July 2021 satellite images.",
    outFlood2021: "Your area does not appear flooded on the July 2021 satellite images, which missed a lot (Vesdre valley).",
    notModelled: "The model covers no river in this municipality, so it cannot assess your risk (small streams and runoff are not modelled).",
    nearest: "Nearest candidate shelter by a dry route", walk: "on foot", min: "min",
    upper: "Ground floor flooded: use the upper floors.", dry: "Building outside the flood extent.",
    capacity: "Estimated capacity", people: "people (rough estimate)",
    prmYes: "Wheelchair access recorded (OpenStreetMap).", prmLimited: "Limited wheelchair access (OpenStreetMap).", prmUnknown: "Wheelchair access unknown.",
    noRouteFlood: "No dry route found from your area. Go to an upper floor and call 112 if you are in danger.",
    noRouteDry: "No candidate shelter reachable by a dry route within 15 km.",
    others: "Other candidate shelters nearby (straight line, route not checked)",
    line: "The blue dashed line is the straight line to the shelter, not a route.",
    routeShown: "Green line: walking route that avoids the modelled flooded sections (OpenStreetMap paths). Always follow instructions on site.",
    routeOnlyInFlood: "Your area is outside the flood extent: only the straight line is shown.",
    noCell: "No housing data here. Tap closer to homes.",
    outside: "This place is outside the area covered by the app.",
    gpsError: "Could not locate you. Tap the map instead.",
    legendDepth: "Modelled depth", legendObserved: "Flooded in 2021 (satellite)",
    legendDry: "Candidate shelter, dry", legendUpper: "Upper floors usable", legendNo: "Not usable",
    legendDam: "Dam / weir: keep away", dam: "Dam", weir: "Weir",
    damZone: "keep away during floods (water releases, strong currents, debris).",
    cat: ["School", "Hospital", "Church", "Sports hall / stadium"],
  },
};
const ICONS = ["🏫", "🏥", "⛪", "🏟️"];
const DEPTH_COLORS = { 1: "#9ecae1", 2: "#4292c6", 3: "#2171b5", 4: "#08306b" };
const DEPTH_LABELS = { 1: "≤ 0.5 m", 2: "0.5–1.5 m", 3: "1.5–3 m", 4: "> 3 m" };
const OBSERVED_COLOR = "#e6550d";
const USABLE = new Set([0, 1, 4]);                 // status codes: dry, upper floors usable, dry in 2021
const PRM_EXCLUDED = new Set([2, 4, 5]);           // PRM codes: "No (OSM)", upper floors only, not usable
const MAX_CELL_M = 400;                            // tap further than this from any housing cell: no answer

const state = { lang: "fr", index: null, data: null, scen: "rp100", prm: false, loc: null, byId: new Map(), adminUrl: "",
                routeCache: new Map() };
const $ = (s) => document.querySelector(s);
const t = (k) => T[state.lang][k];

const map = L.map("map", { zoomControl: true }).setView([50.45, 5.6], 9);
const base = {
  "OpenStreetMap": L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map),
  "Satellite": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19, attribution: "Tiles © Esri, Maxar, Earthstar Geographics" }),
};
L.control.layers(base).addTo(map);
const floodLayer = L.layerGroup().addTo(map);
const shelterLayer = L.layerGroup().addTo(map);
const youLayer = L.layerGroup().addTo(map);
const damLayer = L.layerGroup().addTo(map);
const DAM_COLOR = "#b2182b";
let legend = null;

function el(tag, cls, text) {                     // text via textContent: OSM names are untrusted input
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function meters(a, b) {                            // haversine, metres
  const R = 6371000, r = Math.PI / 180;
  const dLat = (b[0] - a[0]) * r, dLon = (b[1] - a[1]) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function applyLang() {
  document.documentElement.lang = state.lang;
  document.title = `walert · ${t("title")}`;
  document.querySelectorAll("[data-t]").forEach((e) => { e.textContent = t(e.dataset.t); });
  document.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === state.lang));
  drawLegend();
  if (state.data) drawDams();
  renderResult();
}

function drawLegend() {
  if (legend) legend.remove();
  legend = L.control({ position: "bottomleft" });
  legend.onAdd = () => {
    const d = el("div", "legend");
    const item = (color, label) => { const r = el("div"); const i = el("i"); i.style.background = color; r.append(i, label); d.append(r); };
    if (state.scen === "observed_2021") item(OBSERVED_COLOR, t("legendObserved"));
    else { d.append(el("div", null, t("legendDepth"))); Object.entries(DEPTH_LABELS).forEach(([k, v]) => item(DEPTH_COLORS[k], v)); }
    item("#1a9850", t("legendDry")); item("#fdae61", t("legendUpper")); item("#9e9e9e", t("legendNo"));
    item(DAM_COLOR, t("legendDam"));
    return d;
  };
  legend.addTo(map);
}

function updateAdminLink() {                       // same ?m=&s= parameters as the Streamlit admin view
  const a = $("#adminLink");
  if (!state.adminUrl) return;
  const p = new URLSearchParams({ s: state.scen });
  if (state.data) p.set("m", state.data.id);
  a.href = `${state.adminUrl}/?${p}`;
  a.hidden = false;
  history.replaceState(null, "", `?${p}`);         // shareable URL; never includes the location
}

async function loadMuni(id, fit = true) {
  const res = await fetch(`data/m/${id}.json`);
  state.data = await res.json();
  state.byId = new Map(state.data.shelters.map((s) => [s[0], s]));
  state.routeCache = new Map();
  $("#muni").value = id;
  drawDams();
  if (fit) { const [w, s, e, n] = state.data.bounds; map.fitBounds([[s, w], [n, e]]); }
  drawScenario();
  updateAdminLink();
}

function drawDams() {                             // same for every scenario: keep-away zones around dams and weirs
  damLayer.clearLayers();
  for (const [kind, name, radius, lat, lon] of state.data.dams || []) {
    const label = `⚠ ${kind === 0 ? t("dam") : t("weir")}${name ? " · " + name : ""}`.replace(/</g, "&lt;");
    L.circle([lat, lon], { radius, color: DAM_COLOR, weight: 2, dashArray: "4 4", fillColor: DAM_COLOR, fillOpacity: 0.15 })
      .bindTooltip(`${label}<br>${t("damZone")}`).addTo(damLayer);
  }
}

function damNearby(loc) {                          // the dam or weir whose keep-away zone contains loc, if any
  return (state.data.dams || []).find(([, , radius, lat, lon]) => meters(loc, [lat, lon]) <= radius);
}

function drawScenario() {
  floodLayer.clearLayers(); shelterLayer.clearLayers();
  if (!state.data) return;
  const k = state.scen;
  L.geoJSON(state.data.extents[k], {
    style: (f) => k === "observed_2021"
      ? { weight: 0, fillColor: OBSERVED_COLOR, fillOpacity: 0.5 }
      : { weight: 0, fillColor: DEPTH_COLORS[f.properties.depth_class], fillOpacity: 0.55 },
    interactive: false,
  }).addTo(floodLayer);
  for (const s of state.data.shelters) {
    const [, name, cat, lat, lon, , sc] = s;
    const [status, , prm] = sc[k];
    const prmOut = state.prm && PRM_EXCLUDED.has(prm);   // no wheelchair access, or reachable only upstairs
    const color = prmOut ? "#9e9e9e" : status === 0 || status === 4 ? "#1a9850" : status === 1 ? "#fdae61" : "#9e9e9e";
    L.circleMarker([lat, lon], { radius: 7, weight: 2, color: "#fff", fillColor: color, fillOpacity: 0.95 })
      .bindTooltip(`${ICONS[cat]} ${name || T[state.lang].cat[cat]}`.replace(/</g, "&lt;"))
      .addTo(shelterLayer);
  }
  drawLegend();
  renderResult();
}

function nearestCell(loc) {
  let best = null, bestD = Infinity;
  for (const c of state.data.cells) {
    const d = meters(loc, [c[0], c[1]]);
    if (d < bestD) { bestD = d; best = c; }
  }
  return bestD <= MAX_CELL_M ? best : null;
}

function routePath(start) {                        // follow the route tree from the start node to the shelter
  const mode = state.prm ? "prm" : "walk", key = `${state.scen}/${mode}`;
  if (!state.routeCache.has(key)) {
    const rows = (state.data.routes[state.scen] || {})[mode] || [];
    state.routeCache.set(key, new Map(rows.map(([n, next, lat, lon]) => [n, [next, lat, lon]])));
  }
  const tree = state.routeCache.get(key), path = [];
  for (let n = start, guard = 0; n >= 0 && tree.has(n) && guard < 20000; guard++) {
    const [next, lat, lon] = tree.get(n);
    path.push([lat, lon]);
    n = next;
  }
  return path;
}

function shelterCard(s, minutes, start) {
  const k = state.scen, [, name, cat, lat, lon, , sc] = s, [status, cap, prm] = sc[k];
  const card = el("div", "card");
  card.append(el("h2", null, t("nearest")));
  card.append(el("p", "big", `${ICONS[cat]} ${name || t("cat")[cat]}`));
  card.append(el("p", null, `${t("cat")[cat]} · ${minutes} ${t("min")} ${t("walk")}`));
  card.append(el("p", status === 1 ? "mid" : "ok", status === 1 ? t("upper") : t("dry")));
  if (cap > 0) card.append(el("p", "muted", `${t("capacity")}: ~${cap} ${t("people")}`));
  card.append(el("p", "muted", prm === 0 ? t("prmYes") : prm === 1 ? t("prmLimited") : t("prmUnknown")));
  L.polyline([state.loc, [lat, lon]], { dashArray: "6 6", color: "#0b5cad", weight: 2, opacity: 0.8 }).addTo(youLayer);
  const path = start >= 0 ? routePath(start) : [];
  if (path.length > 1) {                           // connectors: you → first path node, last path node → shelter
    L.polyline([state.loc, ...path, [lat, lon]], { color: "#ffffff", weight: 9, opacity: 0.9 }).addTo(youLayer);
    L.polyline([state.loc, ...path, [lat, lon]], { color: "#1a7f37", weight: 5 }).addTo(youLayer);
    card.append(el("p", "ok", t("routeShown")));
  } else {
    card.append(el("p", "muted", t("routeOnlyInFlood")));
  }
  card.append(el("p", "muted", t("line")));
  return card;
}

function renderResult() {
  const box = $("#result");
  box.replaceChildren();
  if (state.prm) box.append(el("p", "mid", t("prmMode")));
  if (!state.data || !state.loc) { box.append(el("p", "muted", t("choose"))); return; }
  youLayer.clearLayers();
  L.circleMarker(state.loc, { radius: 9, weight: 3, color: "#fff", fillColor: "#d62728", fillOpacity: 1 }).addTo(youLayer);
  const k = state.scen, cell = nearestCell(state.loc);
  if (!cell) { box.append(el("div", "card", t("noCell"))); return; }
  const [inFlood, sid, wmin, psid, pmin] = cell[2][k];
  const obs = k === "observed_2021";
  const status = el("div", "card");
  status.append(el("p", inFlood ? "bad" : "ok", obs ? (inFlood ? t("inFlood2021") : t("outFlood2021"))
                                                  : (inFlood ? t("inFlood") : t("outFlood"))));
  if (!obs && !state.data.efas_modelled) status.append(el("p", "mid", t("notModelled")));
  box.append(status);
  const dam = damNearby(state.loc);
  if (dam) box.append(el("div", "card bad", `⚠ ${dam[0] === 0 ? t("dam") : t("weir")}${dam[1] ? " · " + dam[1] : ""}: ${t("damZone")}`));

  const id = state.prm ? psid : sid, minutes = state.prm ? pmin : wmin;
  const chosen = id >= 0 ? state.byId.get(id) : null;
  if (chosen) box.append(shelterCard(chosen, minutes, state.prm ? cell[2][k][6] : cell[2][k][5]));
  else box.append(el("div", "card bad", inFlood ? t("noRouteFlood") : t("noRouteDry")));

  const others = state.data.shelters
    .filter((s) => s[0] !== id && USABLE.has(s[6][k][0]) && s[6][k][1] > 0 && !(state.prm && PRM_EXCLUDED.has(s[6][k][2])))
    .map((s) => [meters(state.loc, [s[3], s[4]]), s]).sort((a, b) => a[0] - b[0]).slice(0, 2);
  if (others.length) {
    const card = el("div", "card");
    card.append(el("h2", null, t("others")));
    const ul = el("ul", "others");
    for (const [d, s] of others) ul.append(el("li", null, `${ICONS[s[2]]} ${s[1] || t("cat")[s[2]]} · ${(d / 1000).toFixed(1)} km`));
    card.append(ul);
    box.append(card);
  }
}

function setLocation(latlng) {
  state.loc = [latlng.lat, latlng.lng];
  renderResult();
}

async function locate() {
  if (!navigator.geolocation) { alert(t("gpsError")); return; }
  navigator.geolocation.getCurrentPosition(async (pos) => {
    const p = [pos.coords.latitude, pos.coords.longitude];
    const hits = state.index.municipalities.filter((m) => p[1] >= m.bounds[0] && p[0] >= m.bounds[1] && p[1] <= m.bounds[2] && p[0] <= m.bounds[3]);
    if (!hits.length) { alert(t("outside")); return; }
    hits.sort((a, b) => (a.bounds[2] - a.bounds[0]) * (a.bounds[3] - a.bounds[1]) - (b.bounds[2] - b.bounds[0]) * (b.bounds[3] - b.bounds[1]));
    if (!state.data || state.data.id !== hits[0].id) await loadMuni(hits[0].id, false);
    map.setView(p, 15);
    setLocation({ lat: p[0], lng: p[1] });
  }, () => alert(t("gpsError")), { enableHighAccuracy: true, timeout: 15000 });
}

async function init() {
  const pref = (navigator.language || "fr").slice(0, 2);
  state.lang = T[pref] ? pref : "fr";
  state.index = await (await fetch("data/index.json")).json();
  const sel = $("#muni");
  sel.append(el("option", null, "—"));
  for (const m of state.index.municipalities) { const o = el("option", null, m.name); o.value = m.id; sel.append(o); }
  sel.addEventListener("change", () => sel.value !== "—" && loadMuni(sel.value));
  $("#sources").textContent = state.index.sources;
  $("#locate").addEventListener("click", locate);
  $("#prm").addEventListener("change", (e) => { state.prm = e.target.checked; drawScenario(); });
  document.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => { state.lang = b.dataset.lang; applyLang(); }));
  document.querySelectorAll("[data-scen]").forEach((b) => b.addEventListener("click", () => {
    state.scen = b.dataset.scen;
    document.querySelectorAll("[data-scen]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    drawScenario();
    updateAdminLink();
  }));
  map.on("click", (e) => state.data && setLocation(e.latlng));

  // config.json holds the admin view URL (edit it after deploying); links arrive as ?m=<LAU_ID>&s=<scenario>
  try { state.adminUrl = ((await (await fetch("config.json")).json()).adminUrl || "").replace(/\/$/, ""); } catch (e) { /* no link */ }
  const q = new URLSearchParams(location.search);
  if (state.index.scenarios.includes(q.get("s"))) state.scen = q.get("s");
  document.querySelector(`[data-scen="${state.scen}"]`).setAttribute("aria-pressed", "true");
  applyLang();
  if (state.index.municipalities.some((m) => m.id === q.get("m"))) await loadMuni(q.get("m"));
  else updateAdminLink();
}

init();
