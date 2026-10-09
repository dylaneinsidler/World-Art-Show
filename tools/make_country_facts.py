"""Writes country-facts.js for the desktop show's right screen: each country's capital, region, languages,
two-letter code (for its flag picture), map number and where it sits on the globe, from the world-countries data set (mledoze/countries).

    python tools/make_country_facts.py

Run it again only if countries change; the file it writes is kept in the repository.
"""
import json
import os
import urllib.request

SOURCE = 'https://cdn.jsdelivr.net/npm/world-countries@5.1.0/countries.json'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'country-facts.js')

data = json.load(urllib.request.urlopen(SOURCE, timeout=60))
facts = {}
for c in data:
    facts[c['name']['common']] = {
        'official': c['name']['official'],
        'capital': c.get('capital') or [],
        'region': c.get('region', ''),
        'subregion': c.get('subregion', ''),
        'languages': list((c.get('languages') or {}).values()),
        'cca2': c.get('cca2', ''),
        'ccn3': c.get('ccn3', ''),
        'latlng': c.get('latlng') or [],
        'area': c.get('area'),
        'alt': [a for a in c.get('altSpellings', []) if len(a) > 3],
    }

with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
    f.write('// Made by tools/make_country_facts.py from the world-countries data set. Facts about each country\n')
    f.write('// for the desktop show\'s right screen: capital, region, languages, two-letter code (for the flag) and its number on the map.\n')
    f.write('window.COUNTRY_FACTS = ')
    json.dump(facts, f, ensure_ascii=False, separators=(',', ':'))
    f.write(';\n')
print(f'{len(facts)} countries -> {os.path.normpath(OUT)} ({os.path.getsize(OUT) // 1024} KB)')
