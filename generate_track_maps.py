"""
Extracts real GPS track outlines from F1 telemetry (FastF1) or
OpenStreetMap (Overpass API) and outputs SVG path data + a JS file.
"""

import fastf1
import numpy as np
import os
import urllib.request
import urllib.parse
import json

fastf1.Cache.enable_cache('f1_cache')

SVG_W = 600
SVG_H = 400
PADDING = 40

# FastF1 tracks: (track_id, year, gp_name, session_type)
F1_TRACKS = [
    ('monaco',      2023, 'Monaco Grand Prix',   'Q'),
    ('silverstone', 2023, 'British Grand Prix',  'Q'),
    ('spa',         2023, 'Belgian Grand Prix',  'Q'),
    ('monza',       2023, 'Italian Grand Prix',  'Q'),
    ('nurburgring', 2020, 'Eifel Grand Prix',    'Q'),
]

# OSM tracks: (track_id, overpass_relation_id)
OSM_TRACKS = [
    ('nordschleife', 38566),
]


def coords_to_svg_path(x, y):
    # Flip Y (SVG Y-axis is inverted vs telemetry)
    y = -y

    x_min, x_max = x.min(), x.max()
    y_min, y_max = y.min(), y.max()

    scale = min(
        (SVG_W - 2 * PADDING) / (x_max - x_min),
        (SVG_H - 2 * PADDING) / (y_max - y_min),
    )

    x_off = PADDING + ((SVG_W - 2 * PADDING) - (x_max - x_min) * scale) / 2
    y_off = PADDING + ((SVG_H - 2 * PADDING) - (y_max - y_min) * scale) / 2

    sx = (x - x_min) * scale + x_off
    sy = (y - y_min) * scale + y_off

    # Downsample — keep every Nth point to avoid massive paths
    step = max(1, len(sx) // 800)
    sx, sy = sx[::step], sy[::step]

    pts = " ".join(
        f"{'M' if i == 0 else 'L'}{px:.1f},{py:.1f}"
        for i, (px, py) in enumerate(zip(sx, sy))
    )
    return pts + " Z"


def get_f1_track_path(year, gp_name, session_type):
    print(f"  Loading {gp_name} {year} {session_type} via FastF1...")
    session = fastf1.get_session(year, gp_name, session_type)
    session.load(telemetry=True, laps=True, weather=False, messages=False)

    fastest = session.laps.pick_fastest()
    tel = fastest.get_telemetry()

    x = tel['X'].values.astype(float)
    y = tel['Y'].values.astype(float)

    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]

    return coords_to_svg_path(x, y)


def get_osm_track_path(relation_id):
    print(f"  Fetching OSM relation {relation_id} via Overpass API...")
    query = f"""
[out:json][timeout:30];
relation({relation_id});
way(r);
(._;>;);
out body;
"""
    url = "https://overpass-api.de/api/interpreter"
    body = urllib.parse.urlencode({"data": query.strip()}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "tractition-track-extractor/1.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    nodes = {n['id']: (n['lon'], n['lat']) for n in data['elements'] if n['type'] == 'node'}
    ways = [e for e in data['elements'] if e['type'] == 'way']

    if not ways:
        raise ValueError("No ways found in OSM relation")

    # Build lookup: node_id -> list of ways that start or end there
    ends = {}
    for w in ways:
        for end in (w['nodes'][0], w['nodes'][-1]):
            ends.setdefault(end, []).append(w)

    # Greedily chain ways into a single ordered sequence
    remaining = {w['id']: w for w in ways}
    chain = [ways[0]]
    remaining.pop(ways[0]['id'])

    while remaining:
        tail = chain[-1]['nodes'][-1]
        candidates = [w for w in ends.get(tail, []) if w['id'] in remaining]
        if not candidates:
            # Try reversing — find a way whose last node matches our tail
            candidates = [w for w in remaining.values() if w['nodes'][-1] == tail]
            if candidates:
                w = candidates[0]
                w['nodes'] = list(reversed(w['nodes']))
            else:
                # Gap in topology — just append remaining in order
                candidates = list(remaining.values())
            chain.append(candidates[0])
        else:
            w = candidates[0]
            if w['nodes'][0] != tail:
                w['nodes'] = list(reversed(w['nodes']))
            chain.append(w)
        remaining.pop(chain[-1]['id'])

    coords = []
    for way in chain:
        for nid in way['nodes']:
            if nid in nodes:
                coords.append(nodes[nid])

    lons = np.array([c[0] for c in coords])
    lats = np.array([c[1] for c in coords])

    lat0 = np.mean(lats)
    x = (lons - np.mean(lons)) * np.cos(np.radians(lat0)) * 111320
    y = (lats - np.mean(lats)) * 111320

    return coords_to_svg_path(x, y)


def main():
    os.makedirs('f1_cache', exist_ok=True)
    os.makedirs('lambdas_frontend', exist_ok=True)

    results = {}

    for track_id, year, gp_name, session_type in F1_TRACKS:
        print(f"\n[{track_id.upper()}]")
        try:
            path = get_f1_track_path(year, gp_name, session_type)
            results[track_id] = path
            print(f"  OK — {len(path)} chars of SVG path data")
        except Exception as e:
            print(f"  FAILED: {e}")

    for track_id, relation_id in OSM_TRACKS:
        print(f"\n[{track_id.upper()}]")
        try:
            path = get_osm_track_path(relation_id)
            results[track_id] = path
            print(f"  OK — {len(path)} chars of SVG path data")
        except Exception as e:
            print(f"  FAILED: {e}")

    total = len(F1_TRACKS) + len(OSM_TRACKS)
    js_lines = ["// Auto-generated by generate_track_maps.py — do not edit manually", "const TRACK_PATHS = {"]
    for tid, path in results.items():
        js_lines.append(f'  {tid}: `{path}`,')
    js_lines.append("};")

    out_path = "lambdas_frontend/track_paths.js"
    with open(out_path, "w") as f:
        f.write("\n".join(js_lines) + "\n")

    print(f"\nWrote {out_path} with {len(results)}/{total} tracks.")


if __name__ == "__main__":
    main()
