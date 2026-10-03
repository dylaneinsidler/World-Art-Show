"""Collects DeviantArt's Daily Deviations (the pieces its staff pick each day) and sends them to GitHub as
deviantart.json, where the art list build merges them in.

This runs on the PC because DeviantArt blocks requests from GitHub's servers. launch.ps1 starts it when the show
opens (at most every 6 hours), and install.ps1 sets up a daily run. It needs the free DeviantArt key, saved in
    %LOCALAPPDATA%\\WorldArtShow\\deviantart-key.txt
as two lines: "client_id=..." and "client_secret=...". Run it yourself with: python tools/fetch_deviantart.py
"""

import base64
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from build_catalog import CACHE, UA, fetch_json, item, load_cache, save_cache
from countries import country_from_label

HERE = Path(__file__).resolve().parent
HOME = Path(os.environ.get('LOCALAPPDATA', HERE)) / 'WorldArtShow'
KEY_FILE = HOME / 'deviantart-key.txt'
REPO = 'dylaneinsidler/World-Art-Show'

DAYS = 730      # how far back to collect Daily Deviations
# DeviantArt slows everything down after a few hundred quick requests, so each run does a batch and the
# rest come in on later runs (the show opening, and the daily task).
DAYS_PER_RUN = 150
TAGS_PER_RUN = 2000     # pieces, 10 per request
PROFILES_PER_RUN = 300
PAUSE = 1.0             # seconds between requests


def read_key():
    values = {}
    if KEY_FILE.exists():
        for line in KEY_FILE.read_text(encoding='utf-8-sig').splitlines():
            name, _, value = line.partition('=')
            values[name.strip().lower()] = value.strip()
    cid = os.environ.get('DEVIANTART_CLIENT_ID') or values.get('client_id')
    secret = os.environ.get('DEVIANTART_CLIENT_SECRET') or values.get('client_secret')
    if not cid or not secret or 'paste' in cid.lower() or 'paste' in secret.lower():
        sys.exit(f'No DeviantArt key yet: put client_id and client_secret in {KEY_FILE}')
    return cid, secret


def token(cid, secret):
    return fetch_json('https://www.deviantart.com/oauth2/token', form={
        'grant_type': 'client_credentials', 'client_id': cid, 'client_secret': secret})['access_token']


def api(access, path, **params):
    """A DeviantArt API call. The access pass goes in a header: DeviantArt ignores it in the address."""
    return fetch_json(f'https://www.deviantart.com/api/v1/oauth2/{path}?' + urllib.parse.urlencode(params, doseq=True),
                      headers={'Authorization': f'Bearer {access}'})


def download_days(access):
    """Past days never change, so each day is fetched once and kept. Today and yesterday are fetched again."""
    days = load_cache('deviantart-days', False)
    today = datetime.date.today()
    recent = str(today - datetime.timedelta(days=1))
    todo = [str(today - datetime.timedelta(days=n)) for n in range(DAYS)]
    todo = [d for d in todo if d not in days or d >= recent][:DAYS_PER_RUN]
    print(f'Fetching {len(todo)} days of Daily Deviations ({len(days)} days already kept)...', flush=True)
    for n, date in enumerate(todo, 1):
        d = api(access, 'browse/dailydeviations', date=date, mature_content='false')
        days[date] = [{k: x.get(k) for k in ('deviationid', 'url', 'title', 'author', 'content', 'published_time',
                                              'is_mature')} for x in d.get('results', [])]
        if n % 25 == 0 or n == len(todo):
            save_cache('deviantart-days', days)
        time.sleep(PAUSE)
    return [x for day in days.values() for x in day]


def look_up_tags(access, rows):
    """DeviantArt no longer says what kind of art a piece is; its tags do ("photography", "ai", "fanart")."""
    known = load_cache('deviantart-tags', False)
    todo = [r['deviationid'] for r in rows if r.get('deviationid') and r['deviationid'] not in known][:TAGS_PER_RUN]
    print(f'Looking up tags for {len(todo)} pieces ({len(known)} already known)...', flush=True)
    for i in range(0, len(todo), 10):
        d = api(access, 'deviation/metadata', **{'deviationids[]': todo[i:i + 10]})
        for m in d.get('metadata', []):
            known[m['deviationid']] = [t['tag_name'].lower() for t in m.get('tags', [])]
        for dev in todo[i:i + 10]:
            known.setdefault(dev, [])
        if i % 250 == 0 or i + 10 >= len(todo):
            save_cache('deviantart-tags', known)
        time.sleep(PAUSE)
    return known


def look_up_countries(access, usernames):
    """An artist's country is on their DeviantArt profile, when they've filled it in. Checked again every 60 days."""
    known = load_cache('deviantart-profiles', False, max_age_days=60)
    todo = sorted(set(usernames) - known.keys())[:PROFILES_PER_RUN]
    print(f'Looking up {len(todo)} artists ({len(known)} already known)...', flush=True)
    for n, user in enumerate(todo, 1):
        try:
            known[user] = api(access, f'user/profile/{urllib.parse.quote(user)}').get('country') or ''
        except urllib.error.HTTPError:
            known[user] = ''
        if n % 50 == 0 or n == len(todo):
            save_cache('deviantart-profiles', known)
        time.sleep(PAUSE)
    return known


# Tags (and titles) that mean the piece isn't a hand-made or digital artwork to show: photographs, AI-made images,
# fan art of existing characters, video game art (pixel art included), crafts and 3D objects, tutorials and stock
# resources, and character-sale posts (adoptables, commissions, YCH auctions).
PHOTO_TAGS = re.compile(r'photo|cosplay|model|nikon|canon|sony|lens')
AI_TAGS = re.compile(r'^(ai|aiart|ai_art|aiartwork|aigenerated|ai_generated|aiartcommunity|aiassisted|ai_assisted|'
                     r'aiartist|dalle|dall_e|dalle3|novelai|leonardoai|nightcafe|aiwork|aiimage|generativeai|sdxl|flux|'
                     r'comfyui)$|midjourney|stablediffusion|synthography')
AI_NAME = re.compile(r'(^|[-_])ai([-_]|$)|aiart|ai$', re.I)
FANART_TAGS = re.compile(r'fanart|fan_art|anime|manga|genshin|pokemon|mlp|mylittlepony|marvel|dc_comics|starwars|'
                         r'harrypotter|zelda|sonic|naruto|onepiece|honkai|vtuber|fandom|bioshock|fnaf|undertale|'
                         r'deltarune|hazbin|helluva|overwatch|minecraft|disney|transformers|spiderman|batman|warhammer|'
                         r'splatoon|kirby|touhou|hololive|chibi|fursona|furry|anthro|kemono|technoblade|dreamsmp|lotr|'
                         r'lordoftherings|tolkien|witcher|eldenring|darksouls|finalfantasy|skyrim|mario|dragonball|'
                         r'sailormoon|hollowknight|arcane|leagueoflegends|valorant|jujutsu|demonslayer|evangelion|'
                         r'ghibli|doctorwho|startrek|digimon|dccomics|justiceleague|aquaman|superman|wonderwoman|'
                         r'avengers|xmen|deadpool|harleyquinn|tmnt')
FANART_TITLE = re.compile(r'\b(LOTR|Lord of the Rings|Star Wars|Pok[eé]mon|Zelda|Genshin|Marvel|Batman|Spider-?Man|'
                          r'Harry Potter|Witcher|Elden Ring|Dark Souls|Final Fantasy|Skyrim|Minecraft|Overwatch|'
                          r'Fortnite|Mario|Sonic|Naruto|One Piece|Dragon Ball|Sailor Moon|Hollow Knight|Undertale|'
                          r'League of Legends|Valorant|Warhammer|Aquaman|Superman|Wonder Woman|Avengers|Deadpool|'
                          r'Fan ?art)\b', re.I)
GAME_TAGS = re.compile(r'^(game|games|gaming|gamer|rpg|jrpg|mmorpg|arpg|rpgmaker|steam|playstation|nintendo|xbox|'
                       r'twitch|fortnite|roblox|gacha|gachalife|osu|8bit|16bit|32bit|sprite|sprites|pixel|pixels|'
                       r'pixelated|pixilart|voxel|voxelart|isometric)$|videogame|gameart|game_art|gamedev|indiegame|'
                       r'indiedev|pixelart|pixel_art|spriteart|spritework')
OBJECT_TAGS = re.compile(r'crochet|knit|amigurumi|craft|sculpt|assemblage|foundobject|figurine|polymerclay|^clay$|'
                         r'ceramic|pottery|jewel|doll|plush|embroider|sewing|quilt|tutorial|howto|^guide$|^stock$|'
                         r'stockimage|resource|texture|brushes|template')
SALE_TAGS = re.compile(r'adopt|commission|^ych|auction|refsheet|reference_?sheet|forsale|^sale$|^closed$|^open$|'
                       r'^f2u$|^p2u$|freebase|^base$|pixelbase')
# In titles, sales posts write "OPEN"/"CLOSED" in capitals or brackets; "Open Water" is just a title.
SALE_TITLE = re.compile(r'(?i:\b(ych|adopts?|adoptables?|commissions?|auction|ota|f2u|p2u|for sale)\b)|'
                        r'\b(OPEN|CLOSED)\b|(?i:[\[(]\s*(open|closed)\s*[\])])')
# A piece only gets in when a tag says how it was made: painted, drawn, printed or made digitally. Pieces tagged
# only with subjects ("sea waves", "glamour") are too often photographs.
MEDIUM_TAGS = re.compile(r'paint|acrylic|^oil|oilpaint|oils$|watercol|aquarel|gouache|^ink|inking|ink$|penandink|^pen$|'
                         r'pencil|graphite|charcoal|pastel|drawing|^draw|sketch|canvas|traditional|illustrat|marker|'
                         r'copic|crayon|tempera|mixedmedia|collage|linocut|woodcut|etching|lithograph|screenprint|'
                         r'printmaking|lineart|digitalart|digital_art|digitalpaint|digitalillustration|procreate|krita|'
                         r'clipstudio|csp|artrage|ibispaint|medibang|paintool|fantasyart|conceptart|characterdesign|'
                         r'comicart|cartoon|vectorart|fractal|blender|zbrush|3dart|3drender|matte')
WRITING_TAGS = re.compile(r'^(poetry|poem|poems|freeverse|spokenword|prose|story|stories|literature|writing|haiku|'
                          r'quote|quotes|shortstory|flashfiction)$')


def skip_reason(r, t):
    """Why a Daily Deviation shouldn't be shown, judged by its tags and title; None if it can be."""
    title, user = r.get('title') or '', (r.get('author') or {}).get('username') or ''
    if r.get('is_mature'):
        return 'mature'
    if not (r.get('content') or {}).get('src'):
        return 'not a picture (writing, video...)'
    if t is None:
        return 'tags not looked up yet'
    if not t:
        return 'no tags to tell what it is'
    if any(PHOTO_TAGS.search(x) for x in t):
        return 'photography'
    if any(WRITING_TAGS.search(x) for x in t):
        return 'writing'
    if not any(MEDIUM_TAGS.search(x) for x in t):
        return 'no tag saying it was painted, drawn or made digitally'
    if AI_NAME.search(user) or any(AI_TAGS.search(x) for x in t):
        return 'AI-made'
    if any(FANART_TAGS.search(x) for x in t) or FANART_TITLE.search(title):
        return 'fan art'
    if any(GAME_TAGS.search(x) for x in t):
        return 'video game or pixel art'
    if any(OBJECT_TAGS.search(x) for x in t):
        return 'crafts, objects, tutorials, stock'
    if any(SALE_TAGS.search(x) for x in t) or SALE_TITLE.search(title):
        return 'character sales (adoptables, commissions)'
    return None


def pick(rows, tags, countries):
    """Keeps hand-made and digital art, by artists whose country is known."""
    out, skipped, unknown = [], Counter(), Counter()
    for r in rows:
        t = tags.get(r.get('deviationid'))
        user = (r.get('author') or {}).get('username') or ''
        reason = skip_reason(r, t)
        if not reason and user not in countries:
            reason = 'artist not looked up yet'
        if not reason:
            label = countries[user]
            country = country_from_label(label) if label and label != 'Unknown' else ''
            if label and label != 'Unknown' and country is None:
                unknown[label] += 1
            if not country:
                reason = 'no country on profile'
        if reason:
            skipped[reason] += 1
            continue
        content = r['content']
        year = time.gmtime(int(r['published_time'])).tm_year if r.get('published_time') else ''
        out.append(item('DeviantArt', r['url'], content['src'], r.get('title'), str(year), user,
                        0, [country], content.get('width'), content.get('height'), ' '.join(t)))
    print(f'{len(rows)} Daily Deviations, {len(out)} kept. Left out: '
          + ', '.join(f'{n} {why}' for why, n in skipped.most_common()))
    if unknown:
        print('Countries not recognized (add them to countries.py):', dict(unknown.most_common(15)))
    return out


def github_token():
    """The GitHub sign-in git already has saved on this PC."""
    r = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                       capture_output=True, text=True, timeout=60)
    return next((l.split('=', 1)[1] for l in r.stdout.splitlines() if l.startswith('password=')), None)


def send_to_github(data):
    """Puts deviantart.json in the repository (no local git changes needed). That starts a rebuild of the art list."""
    gh = github_token()
    if not gh:
        sys.exit('No saved GitHub sign-in on this PC; deviantart.json was not sent.')
    url = f'https://api.github.com/repos/{REPO}/contents/deviantart.json'
    headers = {'Authorization': f'Bearer {gh}', 'Accept': 'application/vnd.github+json', 'User-Agent': UA}
    body = json.dumps(data, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
            current = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        current = None
    if current:
        # GitHub skips the content field for large files; fetch it raw to compare.
        raw = urllib.request.urlopen(urllib.request.Request(
            url, headers={**headers, 'Accept': 'application/vnd.github.raw'}), timeout=60).read().decode('utf-8')
        old = json.loads(raw)
        if old.get('works') == data['works']:
            print('No new DeviantArt picks since the last send.')
            return
    req = urllib.request.Request(url, method='PUT', headers=headers, data=json.dumps({
        'message': f'DeviantArt picks, {data["collected"]}',
        'content': base64.b64encode(body.encode('utf-8')).decode(),
        **({'sha': current['sha']} if current else {}),
    }).encode())
    with urllib.request.urlopen(req, timeout=120) as r:
        print(f'Sent {len(data["works"])} DeviantArt pieces to GitHub (HTTP {r.status}); the show updates in a few minutes.')


def main():
    cid, secret = read_key()
    access = token(cid, secret)
    rows = download_days(access)
    tags = look_up_tags(access, rows)
    countries = look_up_countries(access, {(r.get('author') or {}).get('username') for r in rows} - {None})
    works = pick(rows, tags, countries)
    fields = ['artist', 'country', 'title', 'date', 'source', 'page', 'image', 'w', 'h']
    works = sorted(({f: w[f] for f in fields} for w in works), key=lambda w: w['page'])
    send_to_github({'collected': time.strftime('%Y-%m-%d %H:%M'), 'works': works})
    (HOME / 'deviantart-last-run.txt').write_text(time.strftime('%Y-%m-%d %H:%M:%S'), encoding='utf-8')


if __name__ == '__main__':
    HOME.mkdir(parents=True, exist_ok=True)
    if '--log' in sys.argv or sys.stdout is None:
        # Started in the background (no window): write what happens to a log file instead.
        sys.stdout = sys.stderr = open(HOME / 'deviantart.log', 'a', encoding='utf-8', buffering=1)
        print(f'\n--- {time.strftime("%Y-%m-%d %H:%M:%S")}')
    else:
        sys.stdout.reconfigure(encoding='utf-8')
    main()
