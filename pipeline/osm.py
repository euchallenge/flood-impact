"""Shared OpenStreetMap download via the Overpass API (tiled, retried, cached)."""
import json, time
import numpy as np
import requests

OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
                 "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
TILE_DEG = 0.3
MAX_SPLITS = 2                                     # a failing tile is split into 4, at most twice (0.075° tiles)


def _query(tags, bbox, log, split=0):
    """Elements in one bbox (s, w, n, e); if every server fails, split the bbox into 4 and try the quarters."""
    s, w, n, e = bbox
    bbox_txt = f"{s},{w},{n},{e}"
    query = "[out:json][timeout:180];(" + "".join(f'nwr["{k}"="{v}"]({bbox_txt});' for k, v in tags) + ");out tags geom;"
    for attempt, url in enumerate(OVERPASS_URLS):  # busy servers: try each once, then split
        try:
            r = requests.post(url, data={"data": query}, timeout=240,
                              headers={"User-Agent": "eu-ai-challenge-flood-impact/1.0"})
            r.raise_for_status()
            return r.json()["elements"]
        except requests.RequestException as err:
            log(f"Overpass {url} failed on {bbox_txt} ({err})")
            time.sleep(10 * (attempt + 1))
    if split >= MAX_SPLITS:
        raise RuntimeError(f"all Overpass servers failed on {bbox_txt}")
    log(f"splitting {bbox_txt} into 4")
    ym, xm = (s + n) / 2, (w + e) / 2
    return [el for q in [(s, w, ym, xm), (s, xm, ym, e), (ym, w, n, xm), (ym, xm, n, e)]
            for el in _query(tags, q, log, split + 1)]


def fetch(tags, bounds, cache_file, log=print):
    """All nodes/ways/relations with any of the exact (key, value) tags in bounds (w, s, e, n), with geometry."""
    if cache_file.exists():                        # cached: one download is enough
        return json.loads(cache_file.read_text(encoding="utf-8"))
    # exact tag matches (indexed, unlike regex) on small tiles keep each query light for the public servers
    w, s, e, n = bounds
    tile_dir = cache_file.with_name(cache_file.stem + "_tiles")   # per-tile cache: a failed run resumes where it stopped
    tile_dir.mkdir(parents=True, exist_ok=True)
    elements = {}
    for x0 in np.arange(w, e, TILE_DEG):
        for y0 in np.arange(s, n, TILE_DEG):
            tile_file = tile_dir / f"{x0:.3f}_{y0:.3f}.json"
            if tile_file.exists():
                tile_elements = json.loads(tile_file.read_text(encoding="utf-8"))
            else:
                tile_elements = _query(tags, (y0, x0, min(y0 + TILE_DEG, n), min(x0 + TILE_DEG, e)), log)
                tile_file.write_text(json.dumps(tile_elements), encoding="utf-8")
                log(f"Overpass tile {x0:.3f},{y0:.3f} done")
            elements.update({(el["type"], el["id"]): el for el in tile_elements})
    data = {"elements": list(elements.values())}
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data
