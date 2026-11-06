"""Builds catalog.json: recent hand-made and digital art by living artists, from museums and DeviantArt.

GitHub runs this every few hours (.github/workflows/update.yml) and publishes the result with the show, so
the show has the newest list every time it opens. To run it yourself:
    python tools/build_catalog.py              # re-download the sources, reuse the slower lookups
    python tools/build_catalog.py --fresh      # redo everything

Sources:
  - Art Institute of Chicago      https://api.artic.edu/docs/
  - Minneapolis Institute of Art  https://search.artsmia.org/
  - SMK, National Gallery of Denmark  https://open.smk.dk/en/api
  - Victoria and Albert Museum    https://developers.vam.ac.uk/  (2.14)
  - Rijksmuseum                   https://data.rijksmuseum.nl/  (2.14)
  - Wikidata (https://query.wikidata.org/) only to check that artists are still alive, and for the V&A's and the
    Rijksmuseum's artists, their country. Its own artworks aren't used: too many of their pictures are snapshots of
    a wall, a street or a gallery room.
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

from countries import countries_from_nationality, country_from_label

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'catalog.json'
CACHE = Path(os.environ.get('WORLD_ART_SHOW_CACHE')
             or Path(os.environ.get('LOCALAPPDATA', HERE)) / 'WorldArtShow' / 'build-cache')
UA = 'WorldArtShow/1.0 (personal art slideshow; https://github.com/dylaneinsidler)'

THIS_YEAR = time.localtime().tm_year
MADE_SINCE = 2000        # only art made in this year or later (2010 until 2.14; Dylan, 2026-11-05: five times the art)
BORN_AFTER = 1925        # older than ~100: treat as not living even if no death date is recorded
MAX_PER_ARTIST = 20      # keeps a few very prolific artists from filling the catalog
MIN_SIDE = 760           # skip images too small to look good on a large screen (800 until 2.14: the V&A serves
                         # recent work at 768 pixels; the other museums at 800 to 843)

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


def download_vam():
    """The V&A's prints, drawings and paintings made since MADE_SINCE that have a picture (its search records): by
    category, and by object type, since many (most of its drawings) are filed under another category."""
    rows, seen = [], set()
    searches = [f'id_category={c}' for c in ('THES48903', 'THES48889', 'THES48885')] + \
               [f'q_object_type={t}' for t in ('print', 'drawing', 'painting', 'woodcut', 'etching', 'screenprint',
                                               'lithograph', 'linocut', 'watercolour', 'collage')]
    for search in searches:
        page = 1
        while True:
            d = fetch_json(f'https://api.vam.ac.uk/v2/objects/search?year_made_from={MADE_SINCE}&images_exist=1'
                           f'&{search}&page_size=100&page={page}')
            for r in d['records']:
                if r['systemNumber'] not in seen:
                    seen.add(r['systemNumber'])
                    rows.append(r)
            if page >= d['info']['pages']:
                break
            page += 1
            time.sleep(0.3)
    print(f'  V&A: {len(rows)}')
    return rows


LINKED_ART = {'Accept': 'application/ld+json'}


def download_rijks():
    """The Rijksmuseum's prints, drawings and paintings made since MADE_SINCE that have a picture: just where each
    record is, with the year searched for. The records themselves are looked up once and kept (rijks_records)."""
    found = {}
    for kind in ('print', 'drawing', 'painting'):
        for year in range(MADE_SINCE, THIS_YEAR + 1):
            url = f'https://data.rijksmuseum.nl/search/collection?type={kind}&creationDate={year}&imageAvailable=true'
            while url:
                d = fetch_json(url)
                for it in d.get('orderedItems') or []:
                    found.setdefault(it['id'], [it['id'], year, kind])
                url = (d.get('next') or {}).get('id')
                time.sleep(0.2)
    print(f'  Rijksmuseum: {len(found)}')
    return list(found.values())


def english(notations):
    """The English one of a Rijksmuseum record's labels ([{"@language": "en", "@value": "print"}, ...])."""
    for n in notations or []:
        if n.get('@language') == 'en':
            return n.get('@value') or ''
    return (notations or [{}])[0].get('@value') or ''


def rijks_compact(o):
    """The parts of a Rijksmuseum (Linked Art) record the show uses."""
    is_english = lambda x: any((l.get('id') or '').endswith('300388277') for l in x.get('language') or [])
    names = [x for x in o.get('identified_by') or [] if x.get('type') == 'Name' and x.get('content')]
    title = next((x['content'] for x in names if is_english(x)), names[0]['content'] if names else '')
    number = next((x['content'] for x in o.get('identified_by') or [] if x.get('type') == 'Identifier'), '')
    prod = o.get('produced_by') or {}
    parts = prod.get('part') or [prod]
    makers = []
    for part in parts:
        role = ', '.join(english(t.get('notation')) for t in part.get('technique') or [])
        if not role:   # then it's in the words: "printmaker: Karel Wetselaar (signed by artist)"
            role = next((t['content'].split(':')[0] for t in part.get('referred_to_by') or []
                         if is_english(t) and ':' in (t.get('content') or '')), '')
        # The maker is named right there, or (about half the time) only pointed to, as an attribution.
        people = list(part.get('carried_out_by') or [])
        people += [p for a in part.get('assigned_by') or [] if a.get('assigned_property') == 'carried_out_by'
                   for p in a.get('assigned') or [] if p.get('type') == 'Person']
        for p in people:
            wikidata = next((e['id'].rsplit('/', 1)[1] for e in p.get('equivalent') or [] if 'wikidata.org' in e.get('id', '')), '')
            makers.append({'id': p.get('id'), 'name': english(p.get('notation')), 'wikidata': wikidata, 'role': role})
    span = prod.get('timespan') or next((p['timespan'] for p in parts if p.get('timespan')), {})
    years = sorted({int(t[:4]) for t in (span.get('begin_of_the_begin'), span.get('end_of_the_end')) if t and t[:4].isdigit()})
    return {'title': title, 'number': number, 'makers': makers,
            'date': '–'.join(str(y) for y in years),
            'kind': ', '.join(english(c.get('notation')) for c in o.get('classified_as') or [] if english(c.get('notation'))),
            'materials': ', '.join(english(m.get('notation')) for m in o.get('made_of') or []),
            'visual': ((o.get('shows') or [{}])[0]).get('id')}


def rijks_person(pid):
    """A maker the record only points to: their own Rijksmuseum record's name, Wikidata id, birth and death years."""
    p = fetch_json(pid, headers=LINKED_ART, tries=2)
    names = [x['content'] for x in p.get('identified_by') or [] if x.get('type') == 'Name' and x.get('content')]
    year = lambda event: (((event or {}).get('timespan') or {}).get('begin_of_the_begin') or '')[:4]
    return {'name': names[0] if names else '', 'born': year(p.get('born')), 'died': year(p.get('died')),
            'wikidata': next((e['id'].rsplit('/', 1)[1] for e in p.get('equivalent') or []
                              if 'wikidata.org' in e.get('id', '')), '')}


def rijks_records(found, fresh):
    """Each Rijksmuseum piece's record, its picture's address and size: three or four lookups a piece, so they're
    done once and kept (records hardly change). v 2: makers given only as an attribution are looked up too."""
    known = load_cache('rijks-records', fresh)
    persons = load_cache('rijks-people', fresh)
    todo = [oid for oid, _, _ in found if (known.get(oid) or {}).get('v') != 2]

    def look(oid):
        try:
            rec = rijks_compact(fetch_json(oid, headers=LINKED_ART, tries=2))
            rec['v'] = 2
            for m in rec['makers']:
                if m['id'] and not (m['name'] and m['wikidata']):
                    if m['id'] not in persons:
                        persons[m['id']] = rijks_person(m['id'])
                    p = persons[m['id']]
                    m.update(name=m['name'] or p['name'], wikidata=m['wikidata'] or p['wikidata'], born=p['born'], died=p['died'])
            if rec['visual']:
                visual = fetch_json(rec['visual'], headers=LINKED_ART, tries=2)
                digital = fetch_json(visual['digitally_shown_by'][0]['id'], headers=LINKED_ART, tries=2)
                base = digital['access_point'][0]['id'].split('/full/')[0]   # https://iiif.micr.io/<id>
                info = fetch_json(base + '/info.json', tries=2)
                rec.update(iiif=base, w=info.get('width') or 0, h=info.get('height') or 0)
            return oid, rec
        except Exception:
            return oid, None   # try again next time

    if todo:
        print(f'Looking up {len(todo)} Rijksmuseum records...', flush=True)
        with ThreadPoolExecutor(6) as pool:
            for n, (oid, rec) in enumerate(pool.map(look, todo), 1):
                if rec is not None:
                    known[oid] = rec
                if n % 200 == 0:
                    print(f'  {n} of {len(todo)}', flush=True)
                    save_cache('rijks-records', known)
        save_cache('rijks-records', known)
        save_cache('rijks-people', persons)
    return known


def iiif_sizes(bases, fresh):
    """Each picture's size, from its IIIF info.json (also shows the picture is there). Kept between runs."""
    known = load_cache('iiif-sizes', fresh)
    todo = sorted(set(bases) - known.keys())

    def look(base):
        try:
            info = fetch_json(base.rstrip('/') + '/info.json', tries=2)
            return base, [info.get('width') or 0, info.get('height') or 0]
        except urllib.error.HTTPError as e:
            return base, [0, -1] if e.code in (403, 404, 410) else None   # -1: no picture there
        except Exception:
            return base, None

    if todo:
        print(f'Checking {len(todo)} picture sizes...', flush=True)
        with ThreadPoolExecutor(6) as pool:
            for base, size in pool.map(look, todo):
                if size is not None:
                    known[base] = size
        save_cache('iiif-sizes', known)
    return known


# Life and country of the V&A's and the Rijksmuseum's artists, from Wikidata. The Rijksmuseum links most of its
# makers to their Wikidata entry; the V&A gives only a name, so a name counts only when it belongs to exactly one
# artist on Wikidata (a painter, printmaker, illustrator...): a namesake mustn't decide who's alive.
PEOPLE_QUERY = '''
SELECT ?p ?born ?died ?country WHERE {
  VALUES ?p { %s }
  OPTIONAL { ?p wdt:P569 ?b . BIND(YEAR(?b) AS ?born) }
  OPTIONAL { ?p wdt:P570 ?d . BIND(YEAR(?d) AS ?died) }
  OPTIONAL { ?p wdt:P27 ?c . ?c rdfs:label ?country . FILTER(LANG(?country) = "en") }
}'''
NAMES_QUERY = '''
SELECT ?name ?p ?born ?died ?country WHERE {
  VALUES ?name { %s }
  VALUES ?job { wd:Q483501 wd:Q1028181 wd:Q11569986 wd:Q3391743 wd:Q644687 wd:Q15296811 wd:Q329439 wd:Q627325
                wd:Q1281618 wd:Q3303330 wd:Q1925963 wd:Q7541856 }
  ?p rdfs:label ?name ; wdt:P31 wd:Q5 ; wdt:P106 ?job .
  OPTIONAL { ?p wdt:P569 ?b . BIND(YEAR(?b) AS ?born) }
  OPTIONAL { ?p wdt:P570 ?d . BIND(YEAR(?d) AS ?died) }
  OPTIONAL { ?p wdt:P27 ?c . ?c rdfs:label ?country . FILTER(LANG(?country) = "en") }
}'''


def wikidata_people(keys, by_name, fresh):
    """{Wikidata id or name: {'born', 'died', 'countries'}}, or {} when Wikidata can't say. Checked again each month."""
    cache = 'wikidata-names' if by_name else 'wikidata-people'
    known = load_cache(cache, fresh, max_age_days=30)
    todo = sorted(set(k for k in keys if k) - known.keys())
    if todo:
        print(f'Looking up {len(todo)} artists on Wikidata...', flush=True)
    for i in range(0, len(todo), 80):
        batch = todo[i:i + 80]
        if by_name:
            values = ' '.join(f'"{n}"@{lang}' for n in (x.replace('\\', '\\\\').replace('"', '\\"') for x in batch)
                              for lang in ('en', 'mul'))
        else:
            values = ' '.join(f'wd:{q}' for q in batch if re.fullmatch(r'Q\d+', q))
        url = 'https://query.wikidata.org/sparql?' + urllib.parse.urlencode(
            {'query': (NAMES_QUERY if by_name else PEOPLE_QUERY) % values, 'format': 'json'})
        rows = fetch_json(url, headers={'Accept': 'application/sparql-results+json'})['results']['bindings']
        found = defaultdict(lambda: defaultdict(lambda: {'born': None, 'died': None, 'countries': []}))
        for r in rows:
            key = r['name']['value'] if by_name else r['p']['value'].rsplit('/', 1)[1]
            person = found[key][r['p']['value']]
            if 'born' in r:
                person['born'] = int(r['born']['value'])
            if 'died' in r:
                person['died'] = int(r['died']['value'])
            if 'country' in r and r['country']['value'] not in person['countries']:
                person['countries'].append(r['country']['value'])
        for key in batch:
            matches = list(found[key].values()) if key in found else []
            known[key] = matches[0] if len(matches) == 1 else {}
        time.sleep(1)
    if todo:
        save_cache(cache, known)
    return known


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
    title = re.sub(r'<[^>]+>', '', title or '')   # the V&A writes some titles with <i>...</i>
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
                      r'matri(x|ces)|book|publication|judaica|architecture|time-based|'
                      r'computer print|digital print|laser print', re.I)   # museum digital prints are nearly all photos
MAX_ASPECT = 3.5         # panoramas and scrolls this much wider (or taller) than the screen show as thin strips
# Pieces whose only image isn't the artwork itself (e.g. a photo of the gallery room), found by looking:
# one address per line in leave_out.txt.
LEAVE_OUT = HERE / 'leave_out.txt'


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


# The V&A names where a piece was made, not the artist's country: used when Wikidata doesn't know the artist.
VAM_PLACES = {'london': 'United Kingdom', 'britain': 'United Kingdom', 'england': 'England', 'scotland': 'Scotland',
              'wales': 'Wales', 'edinburgh': 'Scotland', 'glasgow': 'Scotland', 'cardiff': 'Wales',
              'manchester': 'United Kingdom', 'bristol': 'United Kingdom', 'kyoto': 'Japan', 'tokyo': 'Japan',
              'osaka': 'Japan', 'montreal': 'Canada', 'toronto': 'Canada', 'new york': 'United States',
              'paris': 'France', 'berlin': 'Germany', 'seoul': 'South Korea', 'beijing': 'China',
              'shanghai': 'China', 'hong kong': 'Hong Kong', 'mumbai': 'India', 'delhi': 'India', 'new delhi': 'India',
              'amsterdam': 'Netherlands', 'dublin': 'Ireland', 'taipei': 'Taiwan', 'america': 'United States',
              'wimbledon': 'United Kingdom', 'brighton': 'United Kingdom', 'hackney wick': 'United Kingdom',
              'oxford': 'United Kingdom', 'margate': 'United Kingdom', 'bath': 'United Kingdom', 'devon': 'England',
              'dundee': 'Scotland', 'arles': 'France', 'liege': 'Belgium', 'mallorca': 'Spain', 'madrid': 'Spain',
              'california': 'United States', 'connecticut': 'United States', 'philadelphia': 'United States',
              'new jersey': 'United States', 'moscow': 'Russia', 'rio de janeiro': 'Brazil', 'lisbon': 'Portugal',
              'munich': 'Germany', 'buenos aires': 'Argentina', 'jaipur': 'India', 'gujarat': 'India',
              'diriyah': 'Saudi Arabia', 'torres strait islands': 'Australia'}
# Makers that are a business, not an artist ("Somenotsukasa Yoshioka dye workshop", "Curwen Press").
NOT_A_PERSON = re.compile(r'\b(unknown|anonymous|workshop|studio|press|ltd|limited|company|co\.|editions?|gallery|'
                          r'publishers?|printers?|school|group|collective|society|museum|council)\b', re.I)
VAM_NOT_ART = re.compile(r'poster|postcard|album|sample|card|label|wrapper|calendar|book|design', re.I)


def vam_artist(r):
    """'Ainslie, Prudence' -> 'Prudence Ainslie'; '' for a business or an unnamed maker."""
    m = r.get('_primaryMaker') or {}
    name, role = clean(m.get('name')), (m.get('association') or '').lower()
    if not name or NOT_A_PERSON.search(name) or re.search(r'publish|printer|manufactur|retail|distribut', role):
        return ''
    last, comma, first = name.partition(', ')
    return f'{first} {last}' if comma and first and not re.search(r'\d', first) else name


def from_vam(rows, people, sizes, unknown):
    out = []
    for r in rows:
        kind, artist = clean(r.get('objectType')), vam_artist(r)
        base = (r.get('_images') or {}).get('_iiif_image_base_url')
        if not base or not artist or not flat_art(kind) or VAM_NOT_ART.search(kind) or not made_since(r.get('_primaryDate')):
            continue
        p = people.get(artist) or {}
        if p.get('died') or (p.get('born') and p['born'] < BORN_AFTER):
            continue
        if not p and ' ' not in artist:   # a surname alone ("Freud"): no telling who, or whether they're alive
            continue
        countries = [c for c in (country_from_label(x) for x in p.get('countries') or []) if c]
        if not countries:
            place = clean(r.get('_primaryPlace'))
            country = country_from_label(place) or VAM_PLACES.get(place.casefold())
            if not country:
                unknown[('V&A place', place)] += 1
                continue
            countries = [country]
        w, h = sizes.get(base, (0, 0))
        if h < 0:   # the picture isn't there
            continue
        out.append(item('Victoria and Albert Museum', f'https://collections.vam.ac.uk/item/{r["systemNumber"]}/',
                        f'{base}full/!1600,1600/0/default.jpg', r.get('_primaryTitle'), r.get('_primaryDate'),
                        artist, p.get('born') or 0, countries, w, h, kind))
    return out


# Rijksmuseum roles that aren't the artist (the print's publisher, the printer, the person it was made after).
RIJKS_NOT_ARTIST = re.compile(r'publisher|printer\b|editor|commission|dedicat|after|intermediar|attributed|workshop|'
                              r'client|author', re.I)


def from_rijks(found, records, people, unknown):
    out = []
    for oid, year, kind in found:
        rec = records.get(oid) or {}
        makers = [m for m in rec.get('makers') or [] if m.get('name') and not RIJKS_NOT_ARTIST.search(m.get('role') or '')]
        if not rec.get('iiif') or not makers or NOT_A_PERSON.search(makers[0]['name']) \
                or PHOTO_MEDIUM.search(f"{rec.get('kind')} {rec.get('materials')} {makers[0].get('role')}"):
            continue
        m, date = makers[0], rec.get('date') or str(year)
        p = people.get(m.get('wikidata')) or {}
        born = p.get('born') or (int(m['born']) if (m.get('born') or '').isdigit() else 0)
        if p.get('died') or m.get('died') or not born or born < BORN_AFTER or not made_since(date):
            continue
        if not p:
            unknown[('Rijksmuseum', 'artist not on Wikidata')] += 1
            continue
        countries = [c for c in (country_from_label(x) for x in p.get('countries') or []) if c]
        if not countries:
            unknown[('Rijksmuseum', ', '.join(p.get('countries') or []) or 'no country')] += 1
            continue
        out.append(item('Rijksmuseum', f'https://www.rijksmuseum.nl/en/collection/{rec["number"]}',
                        f'{rec["iiif"]}/full/!1600,1600/0/default.jpg', rec.get('title'), date, m['name'],
                        born, countries, rec.get('w'), rec.get('h'), rec.get('kind') or kind))
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
    # The V&A and the Rijksmuseum (2.14): their artists' lives and countries come from Wikidata.
    vam = cached('vam', age, download_vam)
    vam_people = wikidata_people({vam_artist(r) for r in vam}, True, args.fresh)
    vam_sizes = iiif_sizes([(r.get('_images') or {}).get('_iiif_image_base_url') for r in vam
                            if (r.get('_images') or {}).get('_iiif_image_base_url')], args.fresh)
    museums += from_vam(vam, vam_people, vam_sizes, unknown)
    rijks = cached('rijks', age, download_rijks)
    records = rijks_records(rijks, args.fresh)
    rijks_people = wikidata_people({m.get('wikidata') for r in records.values() for m in r.get('makers') or []}, False, args.fresh)
    museums += from_rijks(rijks, records, rijks_people, unknown)
    dead = dead_on_wikidata([it for it in museums if it['born']], args.fresh)
    if dead:
        print(f'Leaving out {len(dead)} artists Wikidata records as having died, e.g. '
              + ', '.join(sorted(a for a, _ in dead)[:8]))
    items = [it for it in museums if (it['artist'], it['born']) not in dead]
    items += load_deviantart()

    # Drop images known to be too small or too long and thin, exact duplicates (the same file listed twice),
    # and pieces on the leave-out list.
    leave_out = {line.strip() for line in LEAVE_OUT.read_text(encoding='utf-8').splitlines()
                 if line.strip() and not line.startswith('#')} if LEAVE_OUT.exists() else set()
    seen, kept = set(), []
    for it in items:
        w, h = it['w'], it['h']
        if (w and h and (max(w, h) < MIN_SIDE or max(w, h) / min(w, h) > MAX_ASPECT)) \
                or it['image'] in seen or it['page'] in leave_out:
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

    # w, h: image shape (0 = unknown). medium: 'hand' (painted, drawn, printed: every museum piece, and DeviantArt's
    # pieces tagged with a traditional medium) or 'digital'; the show's "Digital art: Off" keeps to 'hand' (2.12).
    for it in final:
        it['medium'] = it.get('medium') or ('digital' if it['source'] == 'DeviantArt' else 'hand')
    fields = ['artist', 'country', 'title', 'date', 'source', 'page', 'image', 'w', 'h', 'medium']
    catalog = {'built': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
               'fields': fields, 'works': [[it[f] for f in fields] for it in final]}
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    by_source = Counter(it['source'] + (' (hand-made)' if it['source'] == 'DeviantArt' and it['medium'] == 'hand' else '')
                        for it in final)
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
