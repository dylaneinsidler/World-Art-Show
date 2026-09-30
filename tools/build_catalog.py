"""Builds catalog.json: recent hand-made and digital art by living artists, from museums, Wikidata and DeviantArt.

GitHub runs this every few hours (.github/workflows/update.yml) and publishes the result with the show, so
the show has the newest list every time it opens. To run it yourself:
    python tools/build_catalog.py              # re-download the sources, reuse the slower lookups
    python tools/build_catalog.py --fresh      # redo everything

Sources:
  - Art Institute of Chicago      https://api.artic.edu/docs/
  - Minneapolis Institute of Art  https://search.artsmia.org/
  - SMK, National Gallery of Denmark  https://open.smk.dk/en/api
  - Wikidata + Wikimedia Commons  https://query.wikidata.org/
  - DeviantArt (staff-picked Daily Deviations), collected on the PC by tools/fetch_deviantart.py and merged
    from deviantart.json
"""

import argparse
import datetime
import gzip
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from countries import country_from_label, countries_from_nationality

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'catalog.json'
CACHE = Path(os.environ.get('WORLD_ART_SHOW_CACHE')
             or Path(os.environ.get('LOCALAPPDATA', HERE)) / 'WorldArtShow' / 'build-cache')
UA = 'WorldArtShow/1.0 (personal art slideshow; https://github.com/dylaneinsidler)'

THIS_YEAR = time.localtime().tm_year
MADE_SINCE = 2010        # only art made in this year or later
BORN_AFTER = 1925        # older than ~100: treat as not living even if no death date is recorded
MAX_PER_ARTIST = 20      # keeps a few very prolific artists from filling the catalog
MIN_SIDE = 800           # skip images too small to look good on a large screen

# Photographs, film and video, recognised by what the work is made of ("gelatin silver print",
# "inkjet print", "single-channel video"). Inkjet and pigment prints in museums are nearly always photographs.
PHOTO_MEDIUM = re.compile(
    r'photo|gelatin|gelatine|chromogenic|c-print|inkjet|ink jet|pigment print|pigmented print|archival print|'
    r'dye transfer|dye destruction|silver dye|cibachrome|ilfochrome|platinum|palladium|cyanotype|daguerreotype|'
    r'tintype|ambrotype|polaroid|lambda|light ?jet|giclée|giclee|video|film|projection|camera', re.I)


# ---------------------------------------------------------------- downloading

def fetch_json(url, body=None, headers=None, tries=4, form=None):
    h = {'User-Agent': UA, 'Accept': 'application/json', 'Accept-Encoding': 'gzip'}
    if body is not None:
        h['Content-Type'] = 'application/json'
    h.update(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    if form is not None:   # a form POST, for requests too long to fit in a URL
        data = urllib.parse.urlencode(form).encode()
        h['Content-Type'] = 'application/x-www-form-urlencoded'
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=90) as r:
                raw = r.read()
                raw = gzip.decompress(raw) if r.headers.get('Content-Encoding') == 'gzip' else raw
                try:
                    return json.loads(raw)
                except ValueError:
                    # Say what came back instead (a block page, an empty reply...). Only the address's path is
                    # shown: its query can hold a key.
                    raise ValueError(f'not JSON from {urllib.parse.urlsplit(url).path} (HTTP {r.status}, '
                                     f'{r.headers.get("Content-Type")}): {raw[:160]!r}') from None
        except Exception as e:
            if attempt == tries - 1 or (isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 403, 404)):
                raise
            where = urllib.parse.urlsplit(url).path
            print(f'    retry after {getattr(e, "code", "")} {e if not isinstance(e, urllib.error.HTTPError) else e.reason} ({where})', flush=True)
            time.sleep(5 * (attempt + 1))


def cached(name, max_age_hours, download):
    """Source downloads are kept for a while so the filtering below can be re-run without downloading again."""
    path = CACHE / f'{name}.json'
    if path.exists() and time.time() - path.stat().st_mtime < max_age_hours * 3600:
        return json.loads(path.read_text(encoding='utf-8'))
    print(f'Downloading {name}...', flush=True)
    try:
        data = download()
    except Exception as e:
        # One source being down shouldn't stop the others: use its last good download, if there is one.
        print(f'  {name} failed ({e}); using its last download instead', flush=True)
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    save_cache(name, data)
    return data


def load_cache(name, fresh, max_age_days=None):
    """Lookups that are slow to redo (death checks, image checks, artist profiles), kept between runs."""
    path = CACHE / f'{name}.json'
    if fresh or not path.exists() or (max_age_days and time.time() - path.stat().st_mtime > max_age_days * 86400):
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def save_cache(name, data):
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def download_aic():
    fields = ['id', 'title', 'date_display', 'artist_display', 'artist_title', 'image_id', 'thumbnail',
              'artwork_type_title', 'department_title', 'medium_display']
    rows = []

    def search(years, ids, limit, page=1):
        query = {'bool': {'must': [
            {'exists': {'field': 'image_id'}},
            {'match': {'artist_display': 'born'}},
            {'range': {'date_start': {'gte': years[0], 'lte': years[1]}}},
            {'range': {'id': {'gte': ids[0], 'lte': ids[1]}}},
        ]}}
        time.sleep(1)   # AIC asks for at most 60 requests a minute
        return fetch_json('https://api.artic.edu/api/v1/artworks/search',
                          {'query': query, 'fields': fields, 'limit': limit, 'page': page},
                          {'AIC-User-Agent': UA})

    # The search API returns at most 1,000 results per query: halve the years (then the ids) until it fits.
    def gather(years, ids):
        total = search(years, ids, 0)['pagination']['total']
        if total > 1000:
            if years[0] < years[1]:
                mid = (years[0] + years[1]) // 2
                gather((years[0], mid), ids)
                gather((mid + 1, years[1]), ids)
            else:
                mid = (ids[0] + ids[1]) // 2
                gather(years, (ids[0], mid))
                gather(years, (mid + 1, ids[1]))
            return
        for page in range(1, math.ceil(total / 100) + 1):
            rows.extend(search(years, ids, 100, page)['data'])
            print(f'  AIC: {len(rows)}', end='\r', flush=True)

    # Starting a few years early catches works dated "c. 2010" or "2008–2012".
    gather((MADE_SINCE - 5, THIS_YEAR), (0, 1_000_000))
    print()
    return rows


def download_mia():
    years = ' OR '.join(str(y) for y in range(MADE_SINCE, THIS_YEAR + 1))
    q = urllib.parse.quote(f'image:valid AND life_date:born AND dated:({years})')
    rows, start = [], 0
    while True:
        d = fetch_json(f'https://search.artsmia.org/{q}?size=500&from={start}')
        hits = d['hits']['hits']
        rows += [h['_source'] for h in hits]
        start += len(hits)
        if not hits or start >= min(d['hits']['total']['value'], 10000):
            break
        time.sleep(0.5)
    print(f'  Mia: {len(rows)}')
    return rows


def download_smk():
    rows, start = [], 0
    filters = urllib.parse.quote('[has_image:true],[public_domain:false]')
    since = urllib.parse.quote(f'[production_dates_start:{{{MADE_SINCE}-01-01T00:00:00.000Z;*}}]')
    # Full records are large enough that SMK's server drops the connection; ask only for what's used.
    fields = ('object_number,titles,production,production_date,image_iiif_id,image_width,image_height,'
              'object_names,techniques')
    while True:
        d = fetch_json(f'https://api.smk.dk/api/v1/art/search/?keys=*&offset={start}&rows=250'
                       f'&filters={filters}&range={since}&lang=en&fields={fields}')
        rows += d.get('items') or []
        start += 250
        if start >= d['found']:
            break
        time.sleep(0.5)
    print(f'  SMK: {len(rows)}')
    return rows


# Kinds of artwork asked for on Wikidata: hand-made and digital pictures only. (Its sculpture, installations
# and murals are photos taken on the street, which look like photographs rather than art.)
WIKIDATA_KINDS = {
    'painting': '?work wdt:P31 wd:Q3305213 .',
    'drawing': 'VALUES ?k { wd:Q93184 wd:Q18761202 wd:Q178659 } ?work wdt:P31 ?k .',   # + watercolor, illustration
    'print': '?work wdt:P31 wd:Q11060274 .',
    # digital art, digital painting, computer, generative, pixel and fractal art, as a type or a genre
    'digital art': 'VALUES ?k { wd:Q860372 wd:Q1225029 wd:Q1376265 wd:Q1502032 wd:Q811179 wd:Q777696 } '
                   '{ ?work wdt:P31 ?k } UNION { ?work wdt:P136 ?k }',
}
WIKIDATA_QUERY = '''
SELECT ?work ?workLabel ?image ?made ?creator ?creatorLabel ?born ?country ?countryLabel WHERE {
  %(kind)s
  ?work wdt:P571 ?made . FILTER(?made >= "%(since)d-01-01"^^xsd:dateTime)
  ?work wdt:P18 ?image ; wdt:P170 ?creator .
  ?creator wdt:P31 wd:Q5 ; wdt:P569 ?born .
  FILTER(?born >= "%(born)d-01-01"^^xsd:dateTime)
  FILTER NOT EXISTS { ?creator wdt:P570 [] }
  ?creator wdt:P27 ?country .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}'''


def download_wikidata():
    rows = []
    for name, kind in WIKIDATA_KINDS.items():
        query = WIKIDATA_QUERY % {'kind': kind, 'since': MADE_SINCE, 'born': BORN_AFTER}
        url = 'https://query.wikidata.org/sparql?' + urllib.parse.urlencode({'query': query, 'format': 'json'})
        d = fetch_json(url, headers={'Accept': 'application/sparql-results+json'})
        found = [{k: v['value'] for k, v in b.items()} | {'kind': name} for b in d['results']['bindings']]
        print(f'  Wikidata {name}: {len(found)} rows', flush=True)
        rows += found
        time.sleep(2)
    return rows


# ---------------------------------------------------------------- normalizing

def clean(s):
    return re.sub(r'\s+', ' ', (s or '').replace(' ', ' ')).strip()


def made_since(date):
    """True when the date text says the work was made in MADE_SINCE or later ('2012', 'c. 2015', '2011–14')."""
    years = [int(y) for y in re.findall(r'\b(1[89]\d\d|20\d\d)\b', date or '')]
    return bool(years) and min(years) >= MADE_SINCE


def living_birth_year(life):
    """'Japanese, born 1962' -> 1962. None when the text shows a death year or no birth year."""
    life = clean(life)
    if re.search(r'\d{4}\s*[-–—]\s*\d{2,4}', life) or re.search(r'\b(died|d\.)\s', life):
        return None
    m = re.search(r'\b(?:born|b\.)\s+(?:[^,;]*?,\s*)?(\d{4})\b', life)
    return int(m.group(1)) if m else None


def item(source, page, image, title, date, artist, born, countries, width, height, kind=''):
    return {'source': source, 'page': page, 'image': image, 'title': clean(title) or 'Untitled',
            'date': clean(date), 'artist': clean(artist), 'born': born, 'country': ' / '.join(countries[:2]),
            'w': int(width or 0), 'h': int(height or 0), 'kind': kind}


# Only flat, hand-made art: paintings, drawings, watercolors, prints, collages. Photographs are out, and so are
# 3D objects (sculpture, ceramics, glass, textiles...): a photo of an object looks like a photograph, not like art.
AIC_TYPES = {'Painting', 'Drawing and Watercolor', 'Print'}
AIC_SKIP_DEPARTMENTS = {'Photography and Media', 'Architecture and Design',
                        'Ryerson and Burnham Libraries Special Collections', 'AIC Archives'}
FLAT_ART = re.compile(r'painting|drawing|print|works? on paper|collage|calligraphy|watercolou?r|gouache|pastel|'
                      r'etching|lithograph|woodcut|linocut|serigraph|screenprint|engraving|aquatint|intaglio|sketch', re.I)
NOT_FLAT = re.compile(r'photo|video|film|installation|performance|sculpture|statue|relief|ceramic|glass|wood(?!cut)|'
                      r'metal|lacquer|bamboo|textile|jewel|furniture|costume|multiple|object|wall piece|'
                      r'matri(x|ces)|book|publication|judaica|architecture|time-based', re.I)


def flat_art(kind):
    return bool(FLAT_ART.search(kind or '')) and not NOT_FLAT.search(kind or '')


def from_aic(rows, unknown):
    out = []
    for r in rows:
        lines = [clean(x) for x in (r.get('artist_display') or '').split('\n') if clean(x)]
        if not lines or not r.get('image_id') or r.get('artwork_type_title') not in AIC_TYPES \
                or r.get('department_title') in AIC_SKIP_DEPARTMENTS or PHOTO_MEDIUM.search(r.get('medium_display') or '') \
                or not made_since(r.get('date_display')):
            continue
        # One person: "Peter Doig" / "Scottish, born 1959". Several (printers, publishers...): the artist
        # comes first with their details in brackets, "Jasper Johns (American, born 1930)".
        m = re.fullmatch(r'(.+?)\s*\((.+)\)(?:\s+(?:with|and))?', lines[0])
        if m:
            name, life = m.groups()
        elif len(lines) > 1:
            name, life = lines[:2]
        else:
            continue
        born = living_birth_year(life)
        if not born or born < BORN_AFTER or 'founded' in life:
            continue
        nationality = life.split(',')[0]
        countries = countries_from_nationality(nationality)
        if not countries:
            unknown[('AIC', nationality)] += 1
            continue
        t = r.get('thumbnail') or {}
        out.append(item('Art Institute of Chicago', f'https://www.artic.edu/artworks/{r["id"]}',
                        f'https://www.artic.edu/iiif/2/{r["image_id"]}/full/843,/0/default.jpg',
                        r.get('title'), r.get('date_display'), r.get('artist_title') or name, born, countries,
                        t.get('width'), t.get('height'), r.get('artwork_type_title') or ''))
    return out


def from_mia(rows, unknown):
    out = []
    for r in rows:
        born = living_birth_year(r.get('life_date'))
        artist = clean(r.get('artist'))
        # Skip group credits like "Artist; Publisher: X" where the dates may belong to someone else.
        if not born or born < BORN_AFTER or not artist or ';' in artist or r.get('image') != 'valid' \
                or not flat_art(r.get('classification')) or PHOTO_MEDIUM.search(r.get('medium') or '') \
                or not made_since(r.get('dated')):
            continue
        nationality = clean(r.get('nationality')) or clean(r.get('life_date')).split(',')[0]
        countries = countries_from_nationality(nationality)
        if not countries:
            unknown[('Mia', nationality)] += 1
            continue
        artist = re.sub(r'^(Artist|Designer|Maker|Photographer|Author):\s*', '', artist)
        out.append(item('Minneapolis Institute of Art', f'https://collections.artsmia.org/art/{r["id"]}',
                        f'https://{int(r["id"]) % 7}.api.artsmia.org/800/{r["id"]}.jpg',
                        r.get('title'), r.get('dated'), artist, born, countries,
                        r.get('image_width'), r.get('image_height'), clean(r.get('classification'))))
    return out


def from_smk(rows, unknown):
    out = []
    for r in rows:
        makers = [p for p in (r.get('production') or []) if p.get('creator')]
        kind = ', '.join(o.get('name', '') for o in r.get('object_names') or [])
        date = (r.get('production_date') or [{}])[0].get('period') or ''
        if not makers or not r.get('image_iiif_id') or not flat_art(kind) \
                or PHOTO_MEDIUM.search(' '.join(r.get('techniques') or [])) or not made_since(date):
            continue
        p = makers[0]
        birth = p.get('creator_date_of_birth') or ''
        if p.get('creator_date_of_death') or not birth[:4].isdigit() or int(birth[:4]) < BORN_AFTER:
            continue
        nationality = clean(p.get('creator_nationality'))
        countries = []
        for part in re.split(r'[,/;]| and ', nationality):
            countries += [c for c in countries_from_nationality(clean(part)) if c not in countries]
        if not countries:
            unknown[('SMK', nationality)] += 1
            continue
        titles = r.get('titles') or [{}]
        # SMK stores names as "Surname, Forename"; forename_surname is the display form when present.
        artist = p.get('creator_forename') and p.get('creator_surname') and \
            f'{p["creator_forename"]} {p["creator_surname"]}' or p['creator']
        out.append(item('SMK – National Gallery of Denmark', f'https://open.smk.dk/artwork/image/{r["object_number"]}',
                        f'{r["image_iiif_id"]}/full/!1600,1600/0/default.jpg',
                        titles[0].get('title'), date, artist, int(birth[:4]), countries,
                        r.get('image_width'), r.get('image_height'), kind))
    return out


def from_wikidata(rows, unknown):
    by_work = {}
    for r in rows:
        born = int(r['born'][:4]) if r.get('born', '')[:4].isdigit() else 0
        if born < BORN_AFTER or r['kind'] not in WIKIDATA_KINDS or not made_since((r.get('made') or '')[:4]):
            continue
        w = by_work.setdefault(r['work'], {**r, 'countries': []})
        country = country_from_label(r.get('countryLabel', ''))
        if country is None:
            unknown[('Wikidata', r.get('countryLabel', ''))] += 1
        elif country and country not in w['countries']:
            w['countries'].append(country)
    out = []
    for w in by_work.values():
        title = w.get('workLabel', '')
        # Unlabelled items come back as their Q-number; the artwork's file name reads better than that.
        file = urllib.parse.unquote(w['image'].rsplit('/', 1)[-1])
        if re.fullmatch(r'Q\d+', title):
            title = re.sub(r'\.\w+$', '', file).replace('_', ' ')
        if not w['countries'] or re.fullmatch(r'Q\d+', w.get('creatorLabel', '')):
            continue
        commons = 'https://commons.wikimedia.org/wiki/File:' + urllib.parse.quote(file.replace(' ', '_'))
        image = 'https://commons.wikimedia.org/wiki/Special:FilePath/' + urllib.parse.quote(file) + '?width=1920'
        out.append(item('Wikimedia Commons', commons, image, title, (w.get('made') or '')[:4],
                        w['creatorLabel'], int(w['born'][:4]), sorted(w['countries']), 0, 0, w['kind']))
    return out


# ---------------------------------------------------------------- checks

def mia_images_that_load(items, fresh):
    """Mia's image server refuses some works' images (about 1 in 5) with nothing in the data saying which.
    Ask for each once (a HEAD request, no download) and keep the ones it serves."""
    known = load_cache('mia-images', fresh)
    todo = [it['image'] for it in items if it['image'] not in known]

    def check(url):
        try:
            req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return url, r.status == 200
        except urllib.error.HTTPError as e:
            return url, e.code not in (403, 404, 410) and None   # None: couldn't tell, ask again next time
        except Exception:
            return url, None

    if todo:
        print(f'Checking {len(todo)} Minneapolis images...', flush=True)
        with ThreadPoolExecutor(6) as pool:
            for url, ok in pool.map(check, todo):
                if ok is not None:
                    known[url] = ok
        save_cache('mia-images', known)
    return [it for it in items if known.get(it['image'], True)]


def add_commons_sizes(items, fresh):
    """Wikidata doesn't say how big an image is; ask Commons, 50 files at a time."""
    known = load_cache('commons-sizes', fresh)

    def name(it):
        return urllib.parse.unquote(it['page'].rsplit('File:', 1)[1]).replace('_', ' ')

    files = sorted({name(it) for it in items} - known.keys())
    if files:
        print(f'Looking up {len(files)} image sizes on Wikimedia Commons...', flush=True)
    for i in range(0, len(files), 50):
        d = fetch_json('https://commons.wikimedia.org/w/api.php', form={
            'action': 'query', 'titles': '|'.join('File:' + f for f in files[i:i + 50]), 'prop': 'imageinfo',
            'iiprop': 'size', 'format': 'json', 'formatversion': 2})
        names = {n['to']: n['from'] for n in d['query'].get('normalized', [])}
        for f in files[i:i + 50]:
            known.setdefault(f, [0, 0])
        for p in d['query']['pages']:
            info = (p.get('imageinfo') or [{}])[0]
            known[names.get(p['title'], p['title']).removeprefix('File:')] = [info.get('width', 0), info.get('height', 0)]
        time.sleep(0.5)
    if files:
        save_cache('commons-sizes', known)
    kept = []
    for it in items:
        it['w'], it['h'] = known.get(name(it), [0, 0])
        if it['w'] and it['h']:   # no size means the file is gone
            kept.append(it)
    return kept


DEATHS_QUERY = '''
SELECT ?name ?born WHERE {
  VALUES ?name { %s }
  ?person rdfs:label ?name ; wdt:P31 wd:Q5 ; wdt:P570 [] ; wdt:P569 ?birth .
  BIND(YEAR(?birth) AS ?born)
}'''


def dead_on_wikidata(items, fresh):
    """Museums can take years to record a death. Look every artist up on Wikidata and return the ones
    recorded there as dead, matched on name and birth year so a namesake doesn't knock out a living artist.
    Checked again each month."""
    known = load_cache('wikidata-deaths', fresh, max_age_days=30)
    names = sorted({it['artist'] for it in items} - known.keys())
    if names:
        print(f'Checking {len(names)} artists against Wikidata...', flush=True)
    for i in range(0, len(names), 100):
        batch = names[i:i + 100]
        literals = ' '.join(f'"{n}"@{lang}' for n in (x.replace('\\', '\\\\').replace('"', '\\"') for x in batch)
                            for lang in ('en', 'mul'))
        url = 'https://query.wikidata.org/sparql?' + urllib.parse.urlencode(
            {'query': DEATHS_QUERY % literals, 'format': 'json'})
        rows = fetch_json(url, headers={'Accept': 'application/sparql-results+json'})['results']['bindings']
        for n in batch:
            known[n] = []
        for r in rows:
            if 'born' in r:   # missing when Wikidata has the birth date as "unknown"
                known[r['name']['value']].append(int(r['born']['value']))
        time.sleep(1)
    if names:
        save_cache('wikidata-deaths', known)
    return {(it['artist'], it['born']) for it in items
            if any(abs(b - it['born']) <= 1 for b in known.get(it['artist'], []))}


def load_deviantart():
    """DeviantArt blocks requests from GitHub's servers, so its picks are collected on the PC
    (tools/fetch_deviantart.py) and sent up as deviantart.json. Merge the latest one, if there is one."""
    path = HERE.parent / 'deviantart.json'
    if not path.exists():
        print('DeviantArt: no deviantart.json yet (tools/fetch_deviantart.py makes it on the PC).')
        return []
    d = json.loads(path.read_text(encoding='utf-8'))
    print(f'DeviantArt: {len(d["works"])} pieces, collected {d["collected"]}')
    return d['works']


# ---------------------------------------------------------------- assembling

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fresh', action='store_true', help='redo everything, including the slow lookups')
    ap.add_argument('--max-age', type=float, default=1, metavar='HOURS',
                    help='re-download a source when its last download is older than this (default 1)')
    args = ap.parse_args()
    age = 0 if args.fresh else args.max_age

    unknown = Counter()
    museums = (from_aic(cached('aic', age, download_aic), unknown)
               + mia_images_that_load(from_mia(cached('mia', age, download_mia), unknown), args.fresh)
               + from_smk(cached('smk', age, download_smk), unknown))
    dead = dead_on_wikidata(museums, args.fresh)
    if dead:
        print(f'Leaving out {len(dead)} artists Wikidata records as having died, e.g. '
              + ', '.join(sorted(a for a, _ in dead)[:8]))
    items = ([it for it in museums if (it['artist'], it['born']) not in dead]
             + add_commons_sizes(from_wikidata(cached('wikidata', age, download_wikidata), unknown), args.fresh))

    items += load_deviantart()

    # Drop images known to be too small, and exact duplicates (the same file listed twice).
    seen, kept = set(), []
    for it in items:
        if (it['w'] and it['h'] and max(it['w'], it['h']) < MIN_SIDE) or it['image'] in seen:
            continue
        seen.add(it['image'])
        kept.append(it)

    # Cap each artist, choosing their works at random so the cap isn't always the oldest ones.
    random.seed(7)
    random.shuffle(kept)
    per_artist = defaultdict(list)
    for it in kept:
        key = (it['artist'].casefold(), it['country'])
        if len(per_artist[key]) < MAX_PER_ARTIST:
            per_artist[key].append(it)
    final = sorted((it for works in per_artist.values() for it in works),
                   key=lambda it: (it['country'], it['artist'], it['title']))

    fields = ['artist', 'country', 'title', 'date', 'source', 'page', 'image']
    catalog = {'built': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
               'fields': fields, 'works': [[it[f] for f in fields] for it in final]}
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    by_source = Counter(it['source'] for it in final)
    countries = Counter(it['country'].split(' / ')[0] for it in final)
    artists = {(it['artist'], it['country']) for it in final}
    print(f'\n{len(final)} works by {len(artists)} living artists from {len(countries)} countries, made '
          f'{MADE_SINCE} or later -> {OUT.name} ({OUT.stat().st_size // 1024} KB)')
    for s, n in by_source.most_common():
        print(f'  {n:6}  {s}')
    print('Most works:', ', '.join(f'{c} {n}' for c, n in countries.most_common(12)))
    if unknown:
        print('\nUnrecognized nationalities (add them to countries.py):')
        for (src, nat), n in unknown.most_common(40):
            print(f'  {n:5}  {src}: {nat!r}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
