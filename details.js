'use strict';
// The details sheet on the iPad and iPhone. Swipe up on the art (or tap "Details", bottom left) and a sheet
// slides up with everything about the piece: what it is and what it's about, the artist (born, hometown and a
// short biography), where it came from on a small world map (the artist's country, with a line to the museum),
// and where it is now (the museum and its city, on view or not). Swipe it down, or tap the art above it, to
// hide it. Every new piece starts with it hidden, and while it's open the clock waits, so the piece stays.
// Swipes left and right still change the piece.
//
// index.html (without ?desktop) loads this; the PC's two screens don't use it (their right screen, about.html,
// shows all of this all the time). The museum, Wikipedia and Wikidata lookups are the same as about.js's
// (change both together); DeviantArt pieces show what the art list holds, since DeviantArt needs the PC's key.
// The map (world-map.js, made by tools/make_world_map.py) and the countries (country-facts.js) load the first
// time the sheet opens.
(() => {
  if (new URLSearchParams(location.search).has('desktop')) return;

  const MUSEUMS = {
    'Art Institute of Chicago': { the: 'the Art Institute of Chicago', city: 'Chicago, Illinois, USA', short: 'Chicago', at: [-87.6237, 41.8796] },
    'Minneapolis Institute of Art': { the: 'the Minneapolis Institute of Art', city: 'Minneapolis, Minnesota, USA', short: 'Minneapolis', at: [-93.2737, 44.9586] },
    'SMK – National Gallery of Denmark': { the: 'SMK, the National Gallery of Denmark', city: 'Copenhagen, Denmark', short: 'Copenhagen', at: [12.5779, 55.6888] },
  };

  // ---------------------------------------------------------------- little helpers

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  async function getJSON(url, ms = 20000) {
    const stop = new AbortController();
    const timer = setTimeout(() => stop.abort(), ms);
    try {
      const r = await fetch(url, { signal: stop.signal });
      if (!r.ok) throw new Error(url + ' ' + r.status);
      return await r.json();
    } finally { clearTimeout(timer); }
  }

  // Museum texts can arrive as HTML. Keep only the words, as paragraphs (nothing from them runs).
  function paragraphs(text, isHtml) {
    if (!text) return [];
    if (isHtml) {
      const doc = new DOMParser().parseFromString(text, 'text/html');
      doc.querySelectorAll('br').forEach(b => b.replaceWith('\n'));
      doc.querySelectorAll('p, div, li, h1, h2, h3, h4, blockquote').forEach(b => b.append('\n\n'));
      text = doc.body.textContent;
    }
    return text.split(/\n\s*\n|\n/).map(s => s.replace(/\s+/g, ' ').trim()).filter(Boolean);
  }

  function bornYear(text) {
    const m = /born[^0-9]{0,20}(\d{4})/i.exec(text || '') || /\b(1[89]\d\d|20[0-2]\d)\s*[–-]/.exec(text || '');
    return m ? +m[1] : null;
  }

  // A biography short enough for the sheet: whole sentences, up to about 600 letters.
  function short(text, most = 600) {
    if (!text || text.length <= most) return text || '';
    const cut = text.slice(0, most);
    const end = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('.” '));
    return end > 200 ? cut.slice(0, end + 1) : cut.replace(/\s+\S*$/, '') + '…';
  }

  const hostName = url => { try { return new URL(url).host.replace(/^www\./, ''); } catch { return ''; } };

  // ---------------------------------------------------------------- the piece's record at its museum

  // { story: [paragraphs], life, facts: [..], englishTitle, onView: true / false, now: 'On view now, ...',
  //   more: [credit line, object number, ...], born }
  async function museumRecord(work) {
    const id = work.page.split('/').filter(Boolean).pop();
    const notOnView = 'In the collection, not on view right now';
    if (work.source === 'Art Institute of Chicago') {
      const d = (await getJSON(`https://api.artic.edu/api/v1/artworks/${id}?fields=artist_display,medium_display,` +
        'dimensions,credit_line,description,short_description,is_on_view,gallery_title,main_reference_number')).data;
      return {
        story: d.description ? paragraphs(d.description, true) : paragraphs(d.short_description),
        life: (d.artist_display || '').split('\n').slice(1).join(', '),
        facts: [d.medium_display, d.dimensions],
        onView: !!d.is_on_view,
        now: d.is_on_view ? `On view now${d.gallery_title ? ', ' + d.gallery_title : ''}` : notOnView,
        more: [d.credit_line, d.main_reference_number && `Object number ${d.main_reference_number}`],
        born: bornYear(d.artist_display),
      };
    }
    if (work.source === 'Minneapolis Institute of Art') {
      const d = await getJSON(`https://search.artsmia.org/id/${id}`);
      const on = !!d.room && d.room !== 'Not on View';
      return {
        story: paragraphs(d.text),
        life: d.life_date,
        facts: [d.medium, d.dimension],
        onView: on,
        now: on ? `On view now, gallery ${d.room.replace(/^G/, '')}` : notOnView,
        more: [d.creditline, d.accession_number && `Object number ${d.accession_number}`],
        born: bornYear(d.life_date),
      };
    }
    if (work.source.startsWith('SMK')) {
      const d = (await getJSON(`https://api.smk.dk/api/v1/art/?object_number=${encodeURIComponent(id)}&lang=en`)).items[0];
      const maker = (d.production || [])[0] || {};
      const born = maker.creator_date_of_birth ? +maker.creator_date_of_birth.slice(0, 4) : null;
      const english = (d.titles || []).find(t => /engelsk|english/i.test(t.language || ''));
      const danish = { dansk: 'Danish', svensk: 'Swedish', norsk: 'Norwegian', tysk: 'German', fransk: 'French',
        amerikansk: 'American', britisk: 'British', engelsk: 'English', islandsk: 'Icelandic', 'færøsk': 'Faroese',
        finsk: 'Finnish', hollandsk: 'Dutch', italiensk: 'Italian', spansk: 'Spanish', polsk: 'Polish' };
      const n = maker.creator_nationality || '';
      const nationality = danish[n.toLowerCase()] || (/^[A-Z]/.test(n) ? n : '');
      return {
        story: [...(d.labels || []).map(l => l.text), ...(d.content_description || []), ...(d.notes || [])]
          .flatMap(t => paragraphs(t, /<\w/.test(t))),
        life: [nationality, born && `born ${born}`].filter(Boolean).join(', '),
        facts: [(d.object_names || []).map(o => o.name).join(', '), smkSize(d.dimensions)],
        englishTitle: english && english.title,
        onView: !!d.on_display,
        now: d.on_display ? 'On view now' : notOnView,
        more: [d.acquisition_date_precision && `Joined the collection in ${d.acquisition_date_precision}`,
               ...(d.credit_line || []), d.object_number && `Object number ${d.object_number}`],
        born,
      };
    }
    return null;
  }

  // SMK gives sizes in millimetres (the type in Danish or English): the first height and width, in cm.
  function smkSize(dims) {
    if (!dims) return '';
    const pick = types => dims.find(x => types.includes((x.type || '').toLowerCase()));
    const h = pick(['højde', 'height']), w = pick(['bredde', 'width']);
    if (!h || !w) return '';
    const cm = x => +(/^(mm|millimeter)$/i.test(x.unit || '') ? x.value / 10 : x.value).toFixed(1);
    return `${cm(h)} × ${cm(w)} cm`;
  }

  // ---------------------------------------------------------------- the artist: Wikipedia and Wikidata

  async function wikiSummary(title) {
    try {
      return await getJSON(`https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title.replace(/ /g, '_'))}?redirect=true`, 12000);
    } catch { return null; }
  }

  // Only a page that's plainly about an artist with this name, and not one born in a different year.
  const ART_WORDS = /\b(artist|painter|sculptor|illustrator|printmaker|photographer|draughtsman|draftsman|designer|ceramicist|muralist|cartoonist|animator|engraver)/i;
  async function wikiArtist(name, born) {
    const s = await wikiSummary(name);
    if (!s || s.type !== 'standard') return null;
    const text = `${s.description || ''} ${s.extract || ''}`;
    if (!ART_WORDS.test(text)) return null;
    const theirs = bornYear(text);
    if (born && theirs && Math.abs(theirs - born) > 1) return null;
    return s;
  }

  // Their hometown from the artist's Wikidata record: their place of birth, or else where they live, as
  // "City, State, Country" (the state only for countries that have them), and where it is on the globe.
  const STATE_KINDS = new Set(['Q35657', 'Q11828004', 'Q9357527', 'Q5852411', 'Q485258', 'Q15149663', 'Q131541']);
  const SHORT_COUNTRY = { 'United States of America': 'USA', 'United States': 'USA', "People's Republic of China": 'China' };
  async function wikidata(ids, props) {
    const url = `https://www.wikidata.org/w/api.php?action=wbgetentities&ids=${ids.join('|')}&props=${props}&languages=en&format=json&origin=*`;
    return (await getJSON(url, 12000)).entities || {};
  }
  const claimIds = (e, p) => (e?.claims?.[p] || []).map(c => c.mainsnak?.datavalue?.value?.id).filter(Boolean);
  const labelOf = e => e?.labels?.en?.value || '';

  async function hometown(qid) {
    try {
      const artist = (await wikidata([qid], 'claims'))[qid];
      const placeId = claimIds(artist, 'P19')[0] || claimIds(artist, 'P551')[0];
      if (!placeId) return null;
      const place = (await wikidata([placeId], 'labels|claims'))[placeId];
      const coord = place?.claims?.P625?.[0]?.mainsnak?.datavalue?.value;
      let state = '', up = claimIds(place, 'P131');
      for (let depth = 0; depth < 4 && up.length && !state; depth++) {
        const found = Object.values(await wikidata(up.slice(0, 5), 'labels|claims'));
        const s = found.find(e => claimIds(e, 'P31').some(k => STATE_KINDS.has(k)));
        if (s) state = labelOf(s);
        up = [...new Set(found.flatMap(e => claimIds(e, 'P131')))];
      }
      const countryId = claimIds(place, 'P17')[0];
      let country = countryId ? labelOf((await wikidata([countryId], 'labels'))[countryId]) : '';
      country = SHORT_COUNTRY[country] || country;
      const parts = [labelOf(place), state, country].filter((x, i, all) => x && all.indexOf(x) === i);
      return parts.length ? { text: parts.join(', '), at: coord ? [coord.longitude, coord.latitude] : null } : null;
    } catch { return null; }
  }

  // Each piece is looked up once; opening the sheet again for it shows what was found.
  const lookups = new Map();
  function lookUp(work) {
    if (lookups.has(work.page)) return lookups.get(work.page);
    const museum = work.source === 'DeviantArt' ? Promise.resolve(null) : museumRecord(work).catch(() => 'failed');
    const artist = work.source === 'DeviantArt' ? Promise.resolve(null)
      : museum.then(r => wikiArtist(work.artist, r && r !== 'failed' ? r.born : null));
    const town = artist.then(s => s && s.wikibase_item ? hometown(s.wikibase_item) : null);
    const found = { museum, artist, town };
    lookups.set(work.page, found);
    if (lookups.size > 40) lookups.delete(lookups.keys().next().value);
    return found;
  }

  // ---------------------------------------------------------------- countries and the map (loaded when first needed)

  let mapData = null;
  function loadMapData() {
    mapData ??= Promise.all(['world-map.js', 'country-facts.js'].map(src => new Promise((ok, fail) => {
      const s = document.createElement('script');
      s.src = src;
      s.onload = ok;
      s.onerror = () => fail(new Error(src));
      document.head.append(s);
    }))).catch(e => { mapData = null; throw e; });
    return mapData;
  }

  const ALIASES = { "côte d'ivoire": 'Ivory Coast', 'turkey': 'Türkiye', 'czech republic': 'Czechia',
                    'macedonia': 'North Macedonia', 'swaziland': 'Eswatini', 'burma': 'Myanmar' };
  const UK_PARTS = { 'Scotland': { flag: 'gb-sct', latlng: [56.5, -4.2] }, 'England': { flag: 'gb-eng', latlng: [52.5, -1.5] },
                     'Wales': { flag: 'gb-wls', latlng: [52.3, -3.7] }, 'Northern Ireland': { flag: 'gb-nir', latlng: [54.6, -6.7] } };
  let countryNames = null;
  function country(label) {
    const facts = window.COUNTRY_FACTS || {};
    if (!countryNames) {
      countryNames = new Map();
      for (const [name, f] of Object.entries(facts)) for (const n of [name, f.official, ...f.alt]) countryNames.set(n.toLowerCase(), name);
    }
    if (UK_PARTS[label] && facts['United Kingdom']) return { ...facts['United Kingdom'], ...UK_PARTS[label] };
    const lower = label.toLowerCase();
    const f = facts[countryNames.get((ALIASES[lower] || label).toLowerCase())];
    return f ? { ...f, flag: f.cca2.toLowerCase() } : null;
  }

  // The world on a Miller map (world-map.js), repeated sideways so a line can cross the Pacific.
  function project([lon, lat]) {
    const M = window.WORLD_MAP, rad = Math.PI / 180, k = M.w / (2 * Math.PI);
    const miller = a => 1.25 * Math.log(Math.tan(Math.PI / 4 + 0.4 * Math.max(-89.9, Math.min(89.9, a)) * rad));
    return [(lon + 180) / 360 * M.w, k * (miller(M.top) - miller(lat))];
  }

  // The shortest way round the globe from a to b ([longitude, latitude]), as points that never jump at the
  // map's edge (the longitude keeps going past 180 instead).
  function greatCircle(a, b, steps = 64) {
    const rad = Math.PI / 180;
    const vec = ([lon, lat]) => [Math.cos(lat * rad) * Math.cos(lon * rad), Math.cos(lat * rad) * Math.sin(lon * rad), Math.sin(lat * rad)];
    const va = vec(a), vb = vec(b);
    const d = Math.acos(Math.max(-1, Math.min(1, va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2])));
    if (d < 1e-4) return [a, a];
    const points = [];
    let last = a[0];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps, s1 = Math.sin((1 - t) * d) / Math.sin(d), s2 = Math.sin(t * d) / Math.sin(d);
      const v = [0, 1, 2].map(j => s1 * va[j] + s2 * vb[j]);
      let lon = Math.atan2(v[1], v[0]) / rad;
      const lat = Math.atan2(v[2], Math.hypot(v[0], v[1])) / rad;
      while (lon - last > 180) lon -= 360;
      while (lon - last < -180) lon += 360;
      last = lon;
      points.push([lon, lat]);
    }
    return points;
  }

  // ids: the artist's countries (map numbers); home: [lon, lat] of their hometown or country; museum: MUSEUMS entry.
  function drawMap(box, { ids, home, museum }) {
    const M = window.WORLD_MAP;
    const bw = box.clientWidth, bh = box.clientHeight;
    if (!M || !bw || !bh) return;
    const W = M.w, H = M.h, NS = 'http://www.w3.org/2000/svg';
    const pts = [];
    const homeXY = home && project(home);
    if (homeXY) pts.push(homeXY);
    for (const id of ids) {
      const c = M.land[id];
      if (c) pts.push([c[1][0], c[1][1]], [c[1][2], c[1][3]]);
    }
    let route = null, museumXY = null;
    if (museum) {
      route = (home ? greatCircle(home, museum.at) : [museum.at]).map(project);
      museumXY = route[route.length - 1];
      pts.push(...route);
    }
    if (!pts.length) pts.push([0, 0], [W, H]);

    // Fit everything in with room around it, but never zoom in so far that you can't tell where in the world
    // it is, and never wider than the whole world.
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const aspect = bw / bh;
    let w = Math.max((x1 - x0) * 1.35, W * 0.2), h = Math.max((y1 - y0) * 1.35, W * 0.2 / aspect);
    if (w / h < aspect) w = h * aspect; else h = w / aspect;
    if (w > W) { w = W; h = w / aspect; }
    const vx = (x0 + x1) / 2 - w / 2;
    const lo = Math.min(0, y0), hi = Math.max(H, y1);
    let vy = (y0 + y1) / 2 - h / 2;
    vy = h >= hi - lo ? (lo + hi) / 2 - h / 2 : Math.max(lo, Math.min(hi - h, vy));
    const u = w / bw;                                    // map units per screen pixel

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `${vx.toFixed(0)} ${vy.toFixed(0)} ${w.toFixed(0)} ${h.toFixed(0)}`);
    svg.setAttribute('aria-hidden', 'true');
    const add = (parent, tag, attrs) => {
      const e = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
      parent.append(e);
      return e;
    };
    const homeIds = new Set(ids);
    for (const tile of [-1, 0, 1]) {
      const left = tile * W;
      if (left - 600 > vx + w || left + W + 600 < vx) continue;
      const g = add(svg, 'g', { transform: `translate(${left} 0)` });
      for (const [id, [d]] of Object.entries(M.land)) add(g, 'path', { d, class: homeIds.has(id) ? 'land home' : 'land' });
    }
    if (route && home) add(svg, 'path', { class: 'route', d: 'M' + route.map(p => `${p[0].toFixed(0)} ${p[1].toFixed(0)}`).join('L') });
    if (homeXY) {
      add(svg, 'circle', { class: 'ring', cx: homeXY[0], cy: homeXY[1], r: 7 * u, 'stroke-width': 1.5 * u });
      add(svg, 'circle', { class: 'dot', cx: homeXY[0], cy: homeXY[1], r: 5 * u, 'stroke-width': 1.5 * u });
    }
    if (museumXY) {
      const [x, y] = museumXY;
      add(svg, 'rect', { class: 'museum', x: x - 5 * u, y: y - 5 * u, width: 10 * u, height: 10 * u, 'stroke-width': 1.5 * u });
      const right = (x - vx) / u < bw - 110;
      add(svg, 'text', { class: 'place', x: x + (right ? 11 : -11) * u, y: y + 4 * u, 'font-size': 12 * u, 'stroke-width': 3 * u,
                         'text-anchor': right ? 'start' : 'end' }).textContent = museum.short;
    }
    box.replaceChildren(svg);
  }

  // ---------------------------------------------------------------- the sheet

  const chevron = '<svg viewBox="0 0 18 10" aria-hidden="true"><path d="M2 8.5 9 2l7 6.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const handle = el('button', '');
  handle.id = 'detailsHandle';
  handle.type = 'button';
  handle.title = 'Swipe up for the details';
  handle.setAttribute('aria-expanded', 'false');
  handle.innerHTML = chevron + '<span>Details</span>';
  const sheet = el('section');
  sheet.id = 'details';
  sheet.setAttribute('aria-hidden', 'true');
  sheet.setAttribute('aria-label', 'About this piece');
  const grab = el('div', 'grab');
  const scroller = el('div', 'scroll');
  sheet.append(grab, scroller);
  const scrim = el('div');
  scrim.id = 'detailsScrim';
  document.body.append(handle, scrim, sheet);

  let open = false, filledFor = null, mapInfo = null, mapBox = null;
  const current = () => window.ArtShow && window.ArtShow.current();

  function section(parent, title) {
    parent.append(el('h3', '', title));
    const box = el('div');
    parent.append(box);
    return box;
  }
  function lines(box, items) {
    box.className = 'lines';
    box.replaceChildren(...items.filter(Boolean).map(t => {
      if (t instanceof Node) return t;
      return el('div', '', t);
    }));
  }
  function prose(box, paras, note) {
    box.className = 'prose';
    box.replaceChildren(...paras.map(t => el('p', '', t)), ...(note ? [el('p', 'note', note)] : []));
  }
  function link(href, text) {
    const a = el('a', '', text);
    a.href = href;
    a.target = '_blank';
    a.rel = 'noopener';
    return a;
  }

  // Everything known from the art list goes in straight away; the rest fills in as the lookups answer.
  function fill(work) {
    filledFor = work.page;
    const page = work.page, still = () => filledFor === page;
    const museum = MUSEUMS[work.source] || null;
    const digital = work.source === 'DeviantArt';
    const labels = (work.country || '').split(' / ').filter(Boolean);
    const from = labels.join(' and ');

    const eyebrow = el('div', 'eyebrow');
    const flag = el('span');
    eyebrow.append(flag, el('span', '', [labels.join(' & '), work.date].filter(Boolean).join(' · ')));
    const title = el('h2', 'title', work.title || 'Untitled');
    const byline = el('div', 'byline');
    const life = el('span', 'life');
    byline.append(el('span', '', work.artist), life);
    const facts = el('div', 'facts');

    const cols = el('div', 'cols'), colA = el('div'), colB = el('div');
    cols.append(colA, colB);
    const story = section(colA, "What it's about");
    prose(story, [], digital ? "The artist's own words about it are on its DeviantArt page (the link below)." : 'Looking it up…');
    const artistBox = section(colA, 'The artist');
    const person = el('div', 'person'), pic = el('img'), bio = el('div', 'prose');
    pic.alt = '';
    pic.hidden = true;
    pic.onerror = () => { pic.hidden = true; };
    person.append(pic, bio);
    artistBox.append(person);
    if (digital) prose(bio, [`${work.artist} is an artist from ${from || 'somewhere in the world'} who shares their work on DeviantArt.`],
                       'More about them is on their DeviantArt page.');
    else prose(bio, [], 'Looking them up…');

    mapBox = el('div', 'map');
    const key = el('div', 'key');
    const keyHome = el('span', 'k-home');
    keyHome.append(el('i'), 'Where the artist is from');
    key.append(keyHome);
    if (museum) {
      const keyMuseum = el('span', 'k-museum');
      keyMuseum.append(el('i'), `Where it is now (${museum.short})`);
      key.append(keyMuseum);
    }
    colB.append(mapBox, key);
    const came = section(colB, 'Where it came from');
    const made = work.date ? `${work.artist} made it in ${work.date}` : `Made by ${work.artist}`;
    const cameLines = digital
      ? [`${made}, and shared it online on DeviantArt.`, from && `The artist is from ${from}.`]
      : [`${made}.`, from && `The artist is from ${from}.`, museum && `Then it went to ${museum.the}, in ${museum.city}.`];
    lines(came, cameLines);
    const now = section(colB, 'Where it is now');
    const placeLine = el('div');
    const strong = el('strong', '', digital ? 'DeviantArt' : work.source);
    placeLine.append(strong, digital ? ' · online' : museum ? ` · ${museum.city}` : '');
    const status = el('div', 'now', digital ? `In ${work.artist}'s gallery on DeviantArt, for anyone to see` : 'Looking it up…');
    lines(now, [placeLine, status]);
    const more = section(colB, 'See more');
    more.className = 'links';
    more.append(link(page, digital ? 'The piece on DeviantArt' : `The piece at ${museum ? museum.the : work.source}`));
    const credit = el('div', 'credit', digital ? 'From the show\'s art list (DeviantArt). Map: Natural Earth.'
      : 'From the museum\'s own record, Wikipedia and Wikidata. Map: Natural Earth.');
    colB.append(credit);

    scroller.replaceChildren(eyebrow, title, byline, facts, cols);
    scroller.scrollTop = 0;
    layout();

    // The map and the flag, once the map and the countries have loaded.
    const places = () => labels.map(country).filter(Boolean);
    mapInfo = { ids: [], home: null, museum };
    loadMapData().then(() => {
      if (!still()) return;
      const found = places();
      if (found[0]) {
        const img = new Image();
        img.src = `https://flagcdn.com/h40/${found[0].flag}.png`;
        img.alt = '';
        img.onerror = () => img.remove();
        flag.replaceChildren(img);
      }
      mapInfo.ids = found.map(c => c.ccn3).filter(Boolean);
      mapInfo.home ??= found[0] && found[0].latlng && found[0].latlng.length ? [found[0].latlng[1], found[0].latlng[0]] : null;
      drawMap(mapBox, mapInfo);
    }).catch(() => { if (still()) mapBox.hidden = key.hidden = true; });

    if (digital) return;
    const { museum: record, artist, town } = lookUp(work);
    record.then(r => {
      if (!still()) return;
      if (!r || r === 'failed') {
        prose(story, [], `Couldn't reach ${museum ? museum.the : 'the museum'}'s records just now. Try again in a little while.`);
        status.textContent = "Couldn't check whether it's on view just now";
        return;
      }
      if (r.englishTitle && r.englishTitle !== work.title) title.textContent = `${work.title} (${r.englishTitle})`;
      life.textContent = r.life || '';
      facts.replaceChildren(...(r.facts || []).filter(Boolean).map(t => el('span', '', t)));
      prose(story, r.story || [], (r.story || []).length ? '' : "The museum hasn't written about this piece yet.");
      status.textContent = r.now;
      status.classList.toggle('on', r.onView);
      lines(now, [placeLine, status, ...(r.more || [])]);
    });
    artist.then(s => {
      if (!still()) return;
      if (s) {
        prose(bio, [short(s.extract)], '');
        if (s.thumbnail && s.thumbnail.source) { pic.src = s.thumbnail.source; pic.hidden = false; }
        const wiki = s.content_urls && s.content_urls.desktop && s.content_urls.desktop.page;
        if (wiki) more.append(link(wiki, `${work.artist} on Wikipedia`));
      } else {
        record.then(r => {
          if (!still()) return;
          const lifeText = r && r !== 'failed' && r.life ? ` (${r.life})` : '';
          prose(bio, [`${work.artist}${lifeText} is a living artist from ${from || 'somewhere in the world'}.`],
                "There isn't more written about them yet.");
        });
      }
    });
    town.then(t => {
      if (!still() || !t) return;
      lines(came, [cameLines[0], `Hometown: ${t.text}.`, from && `The artist is from ${from}.`, cameLines[2]]);
      if (t.at) {
        mapInfo.home = t.at;
        if (window.WORLD_MAP) drawMap(mapBox, mapInfo);
      }
    });
  }

  // Two columns when there's room (an iPad held sideways), one otherwise.
  function layout() {
    sheet.classList.toggle('wide', sheet.clientWidth >= 880 && innerWidth > innerHeight);
  }

  function setOpen(on) {
    if (on && !current()) return;
    if (on && filledFor !== current().page) fill(current());
    open = on;
    document.body.classList.toggle('details-open', on);
    sheet.setAttribute('aria-hidden', String(!on));
    handle.setAttribute('aria-expanded', String(on));
    if (window.ArtShow) window.ArtShow.holdClock(on);
    if (on) {
      layout();
      if (window.WORLD_MAP && mapBox && mapInfo) drawMap(mapBox, mapInfo);
    }
  }

  // ---------------------------------------------------------------- swipes and taps

  // A finger on the art moving up brings the sheet up with it; on the open sheet, moving down (from the top of
  // its text, or anywhere on the art above it) takes it down. Let go and it settles open or closed.
  let g = null, claimed = null;
  const sheetHeight = () => sheet.offsetHeight || innerHeight * 0.8;
  function follow(offset) {
    const h = sheetHeight(), o = Math.max(0, Math.min(h * 1.05, offset));
    sheet.style.transform = `translateY(${o}px)`;
    scrim.style.opacity = String(Math.max(0, 1 - o / h));
  }
  function settle(toOpen) {
    document.body.classList.remove('details-dragging');
    sheet.style.transform = '';
    scrim.style.opacity = '';
    setOpen(toOpen);
  }

  document.addEventListener('touchstart', e => {
    if (e.touches.length !== 1) { if (g && g.drag) settle(open); g = null; return; }
    const t = e.touches[0];
    g = { x: t.clientX, y: t.clientY, at: Date.now(), inSheet: sheet.contains(e.target), onHandle: handle.contains(e.target),
          top: scroller.scrollTop <= 0, axis: null, drag: null, y0: 0, vy: 0, ly: t.clientY, lt: Date.now() };
  }, { passive: true });

  document.addEventListener('touchmove', e => {
    if (!g || e.touches.length !== 1) return;
    const t = e.touches[0], dx = t.clientX - g.x, dy = t.clientY - g.y, now = Date.now();
    if (now - g.lt >= 8) { g.vy = 0.6 * ((t.clientY - g.ly) / (now - g.lt)) + 0.4 * g.vy; g.ly = t.clientY; g.lt = now; }
    // At the top of the sheet's text, a finger moving down moves the sheet, not the text.
    if (open && g.inSheet && g.top && dy > 0 && !g.axis && e.cancelable) e.preventDefault();
    if (!g.axis && Math.hypot(dx, dy) > 10) g.axis = Math.abs(dy) > Math.abs(dx) ? 'y' : 'x';
    if (g.axis === 'y' && !g.drag) {
      if (!open && dy < 0 && current()) {
        if (filledFor !== current().page) fill(current());
        layout();
        g.drag = 'up';
      } else if (open && dy > 0 && (!g.inSheet || g.top)) g.drag = 'down';
      if (g.drag) { g.y0 = t.clientY; document.body.classList.add('details-dragging'); }
    }
    if (g.drag) {
      if (e.cancelable) e.preventDefault();
      const moved = t.clientY - g.y0;
      follow(g.drag === 'up' ? sheetHeight() + moved : moved);
    }
  }, { passive: false });

  // Runs before the show's own touch handling (index.html), which leaves alone what this one took.
  window.addEventListener('touchend', e => {
    if (!g) return;
    const t = e.changedTouches[0], dx = t.clientX - g.x, dy = t.clientY - g.y;
    const tap = Math.hypot(dx, dy) < 12 && Date.now() - g.at < 500;
    const sideways = Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy);
    let mine = true;
    if (g.drag) {
      const h = sheetHeight(), moved = t.clientY - g.y0, fast = Math.abs(g.vy) > 0.35;
      if (g.drag === 'up') settle(-moved > Math.min(90, h * 0.2) ? !(fast && g.vy > 0) : fast && g.vy < 0);
      else settle(!(moved > Math.min(110, h * 0.25) ? !(fast && g.vy < 0) : fast && g.vy > 0));
    } else if (g.onHandle && tap) setOpen(true);
    else if (!open) {
      mine = !sideways && dy < -50 && Math.abs(dy) > Math.abs(dx);   // a quick flick up, too fast to follow
      if (mine) setOpen(true);
    } else if (sideways) mine = false;     // the piece changes, and the new one starts with the sheet hidden
    else if (!g.inSheet && tap) setOpen(false);
    // Anything else while it's open (reading, scrolling, tapping its text) belongs to the sheet.
    if (mine) claimed = e;
    g = null;
  }, true);
  window.addEventListener('touchcancel', () => { if (g && g.drag) settle(open); g = null; }, true);

  // A mouse or keyboard (the website on a computer): click "Details" or press the up arrow; click the art
  // above the sheet, press the down arrow or Esc to hide it.
  handle.addEventListener('click', () => setOpen(true));
  scrim.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', e => {
    if (e.key === 'ArrowUp') setOpen(true);
    else if (e.key === 'ArrowDown' || e.key === 'Escape') setOpen(false);
  });

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (open) { layout(); if (window.WORLD_MAP && mapInfo) drawMap(mapBox, mapInfo); } }, 200);
  });

  window.ArtDetails = {
    // The show calls this for every piece it puts up: the sheet starts hidden again.
    newPiece() {
      document.body.classList.add('details-ready');
      if (open) setOpen(false);
    },
    // Was this touch the sheet's (so the show shouldn't pause or change the piece for it)?
    claimed: e => e === claimed,
    isOpen: () => open,
  };
})();
