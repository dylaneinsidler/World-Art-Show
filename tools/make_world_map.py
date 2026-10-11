"""Makes world-map.js: a small, simplified outline of the world's countries for the iPad's details sheet
(swipe up on the art). Run it again only if the map should change:

    python tools/make_world_map.py [countries-110m.json]

The outline is Natural Earth's 1:110m countries (public domain), as world-atlas 2.0.2 publishes it
(https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json; downloaded when no file is given).
Each country is drawn ahead of time on a Miller map (a flat map whose left and right edges meet, so it can
repeat sideways and a line can cross the Pacific), as SVG path text in whole map units, keyed by the
country's number (the same "ccn3" number as in country-facts.js). Antarctica is left out.
"""
import json
import math
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'world-map.js'
SOURCE = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json'

W = 10000                 # map units across the whole world (360 degrees)
TOP, BOTTOM = 84, -57     # latitudes kept: north of Greenland down to Tierra del Fuego
K = W / (2 * math.pi)     # map units per radian


def miller(lat):
    phi = math.radians(max(-89.9, min(89.9, lat)))
    return 1.25 * math.log(math.tan(math.pi / 4 + 0.4 * phi))


H = round(K * (miller(TOP) - miller(BOTTOM)))


def project(lon, lat):
    return (round((lon + 180) / 360 * W), round(K * (miller(TOP) - miller(lat))))


def load(path):
    if path:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    with urllib.request.urlopen(SOURCE, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def decode_arcs(topo):
    (sx, sy), (tx, ty) = topo['transform']['scale'], topo['transform']['translate']
    arcs = []
    for arc in topo['arcs']:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * sx + tx, y * sy + ty))
        arcs.append(points)
    return arcs


def ring_points(ring, arcs):
    points = []
    for i in ring:
        part = arcs[i] if i >= 0 else arcs[~i][::-1]
        points.extend(part if not points else part[1:])
    # A shape that crosses the line where the map's edges meet (eastern Russia, Fiji) jumps from one edge to
    # the other: keep it in one piece instead, running past the edge (the map repeats sideways).
    for n in range(1, len(points)):
        lon, lat = points[n]
        while lon - points[n - 1][0] > 180:
            lon -= 360
        while lon - points[n - 1][0] < -180:
            lon += 360
        points[n] = (lon, lat)
    return points


def area(points):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))) / 2


def path_text(rings):
    """SVG path text: an absolute start for each ring, then small relative steps (the shortest way to write it)."""
    out = []
    for ring in rings:
        last = None
        steps = []
        for p in ring:
            if last is None:
                out.append(f'M{p[0]} {p[1]}')
            elif p != last:
                steps.append(f'{p[0] - last[0]} {p[1] - last[1]}')
            last = p
        if len(steps) >= 2:
            out.append('l' + ' '.join(steps).replace(' -', '-') + 'z')
        else:
            out.pop()
    return ''.join(out)


def main():
    topo = load(sys.argv[1] if len(sys.argv) > 1 else None)
    arcs = decode_arcs(topo)
    land = {}
    for g in topo['objects']['countries']['geometries']:
        cid = g.get('id')
        if cid == '010':                        # Antarctica
            continue
        polygons = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']] if g['type'] == 'Polygon' else []
        rings, biggest = [], None
        for polygon in polygons:
            for n, ring in enumerate(polygon):
                pts = [project(lon, lat) for lon, lat in ring_points(ring, arcs)]
                rings.append(pts)
                if n == 0 and (biggest is None or area(pts) > area(biggest)):
                    biggest = pts
        if not rings:
            continue
        key = cid or '_'                        # a few places have no number; they're drawn but never picked
        text = path_text(rings)
        if key in land:
            land[key][0] += text
            continue
        xs, ys = [p[0] for p in biggest], [p[1] for p in biggest]
        land[key] = [text, [min(xs), min(ys), max(xs), max(ys)]]   # the main part's box, for zooming in on it

    data = {'w': W, 'h': H, 'top': TOP, 'bottom': BOTTOM, 'land': land}
    OUT.write_text(
        '// Made by tools/make_world_map.py from Natural Earth\'s 1:110m countries (public domain, via world-atlas 2.0.2).\n'
        '// A simplified outline of the world for the iPad\'s details sheet: each country\'s shape on a Miller map,\n'
        '// as SVG path text keyed by its number (as in country-facts.js), with the box around its main part.\n'
        'window.WORLD_MAP = ' + json.dumps(data, separators=(',', ':')) + ';\n', encoding='utf-8')
    print(f'{OUT.name}: {len(land)} countries, {OUT.stat().st_size // 1024} KB, {W} x {H} map units')


if __name__ == '__main__':
    main()
