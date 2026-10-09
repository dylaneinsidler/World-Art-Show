'use strict';
// The right screen of the desktop show: the story of the piece on the left screen, the artist, their
// country on a map, and where the piece came from. The left screen (index.html?desktop) posts what it's
// showing to launch.ps1's little web server; this page waits on the server for each change.
//
// Where the words come from:
//   Art Institute of Chicago, Minneapolis Institute of Art, SMK: each museum's own public records.
//   DeviantArt: the artist's own description and profile, looked up by launch.ps1 with the PC's DeviantArt key.
//   Artists' biographies (museum artists) and countries: Wikipedia, only when the page is clearly the same person.

const $ = id => document.getElementById(id);

const MUSEUMS = {
  'Art Institute of Chicago': { city: 'Chicago, Illinois, USA', short: 'Chicago', at: [-87.6237, 41.8796] },
  'Minneapolis Institute of Art': { city: 'Minneapolis, Minnesota, USA', short: 'Minneapolis', at: [-93.2737, 44.9586] },
  'SMK – National Gallery of Denmark': { city: 'Copenhagen, Denmark', short: 'Copenhagen', at: [12.5779, 55.6888] },
};

// ------------------------------------------------------------------ countries

const FACTS = window.COUNTRY_FACTS || {};
const COUNTRY_NAMES = new Map();
for (const [name, f] of Object.entries(FACTS)) {
  for (const n of [name, f.official, ...f.alt]) COUNTRY_NAMES.set(n.toLowerCase(), name);
}
// Names the art list uses that the country data spells differently.
const ALIASES = { "côte d'ivoire": 'Ivory Coast', 'turkey': 'Türkiye', 'czech republic': 'Czechia',
                  'macedonia': 'North Macedonia', 'swaziland': 'Eswatini', 'burma': 'Myanmar' };
// The UK's four nations: their own capital, languages and flag, on the UK's map shape.
const UK_PARTS = {
  'Scotland': { capital: ['Edinburgh'], languages: ['English', 'Scots', 'Scottish Gaelic'], flagCode: 'gb-sct', latlng: [56.5, -4.2] },
  'England': { capital: ['London'], languages: ['English'], flagCode: 'gb-eng', latlng: [52.5, -1.5] },
  'Wales': { capital: ['Cardiff'], languages: ['English', 'Welsh'], flagCode: 'gb-wls', latlng: [52.3, -3.7] },
  'Northern Ireland': { capital: ['Belfast'], languages: ['English', 'Irish'], flagCode: 'gb-nir', latlng: [54.6, -6.7] },
};

function countryFacts(label) {
  if (UK_PARTS[label]) return { ...FACTS['United Kingdom'], ...UK_PARTS[label], name: label, partOf: 'United Kingdom' };
  const lower = label.toLowerCase();
  const key = COUNTRY_NAMES.get(ALIASES[lower] ? ALIASES[lower].toLowerCase() : lower);
  if (!key) return { name: label, capital: [], languages: [], latlng: [] };
  return { ...FACTS[key], name: key, flagCode: FACTS[key].cca2.toLowerCase() };
}

function flagImg(f, height) {
  if (!f || !f.flagCode) return '';
  const img = new Image();
  img.src = `https://flagcdn.com/h${height}/${f.flagCode}.png`;
  img.alt = '';
  img.style.cssText = 'height:1em;border-radius:2px;vertical-align:-0.12em;box-shadow:0 0 0 1px rgba(128,128,128,.25)';
  img.onerror = () => img.remove();
  return img;
}

// ------------------------------------------------------------------ little helpers

async function getJSON(url, ms = 20000) {
  const stop = new AbortController();
  const timer = setTimeout(() => stop.abort(), ms);
  try {
    const r = await fetch(url, { signal: stop.signal });
    if (!r.ok) throw new Error(url + ' ' + r.status);
    return await r.json();
  } finally { clearTimeout(timer); }
}

// Museum and DeviantArt texts arrive as HTML. Keep only the words, as paragraphs (nothing from them runs).
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

function setProse(el, paras, emptyText) {
  el.replaceChildren();
  if (!paras.length) {
    const p = document.createElement('p');
    p.className = 'none';
    p.textContent = emptyText;
    el.append(p);
  }
  for (const t of paras) {
    const p = document.createElement('p');
    p.textContent = t;
    el.append(p);
  }
  restartScroll();
}

function setFacts(el, items) {
  el.replaceChildren(...items.filter(Boolean).map(t => Object.assign(document.createElement('span'), { textContent: t })));
}

function bornYear(text) {
  const m = /born[^0-9]{0,20}(\d{4})/i.exec(text || '') || /\b(1[89]\d\d|20[0-2]\d)\s*[–-]/.exec(text || '');
  return m ? +m[1] : null;
}

function longDate(iso) {
  const d = new Date(iso);
  return isNaN(d) ? '' : d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}

function displayPath(url) {
  let path = url.replace(/^https?:\/\/(www\.)?/, '').replace(/[?#].*$/, '');
  try { path = decodeURIComponent(path); } catch { /* keep as is */ }
  return path;
}

// ------------------------------------------------------------------ each source's details

// Every source comes back in the same shape:
//   { story: [paragraphs], life, facts: [..], tags: [..], origin: [lines], artist: { paragraphs, pic } | null }
async function detailsFrom(work) {
  const id = work.page.split('/').filter(Boolean).pop();
  if (work.source === 'Art Institute of Chicago') {
    const d = (await getJSON(`https://api.artic.edu/api/v1/artworks/${id}?fields=artist_display,medium_display,` +
      'dimensions,credit_line,description,short_description,classification_title,style_titles,subject_titles,' +
      'is_on_view,gallery_title,main_reference_number')).data;
    const lines = (d.artist_display || '').split('\n');
    return {
      story: paragraphs(d.description, true).concat(d.description ? [] : paragraphs(d.short_description)),
      life: lines.slice(1).join(', '),
      facts: [d.medium_display, d.dimensions],
      tags: [...(d.style_titles || []), ...(d.subject_titles || [])].slice(0, 8),
      origin: [d.is_on_view ? `On view now${d.gallery_title ? ', ' + d.gallery_title : ''}.` : 'In the collection (not on view right now).',
               d.credit_line && `${d.credit_line}.`, d.main_reference_number && `Object number ${d.main_reference_number}.`],
      born: bornYear(d.artist_display),
    };
  }
  if (work.source === 'Minneapolis Institute of Art') {
    const d = await getJSON(`https://search.artsmia.org/id/${id}`);
    return {
      story: paragraphs(d.text),
      life: d.life_date,
      facts: [d.medium, d.dimension],
      tags: [d.classification, d.department].filter(Boolean),
      origin: [d.room && d.room !== 'Not on View' ? `On view now, gallery ${d.room.replace(/^G/, '')}.` : 'In the collection (not on view right now).',
               d.creditline && `${d.creditline}.`, d.accession_number && `Object number ${d.accession_number}.`],
      born: bornYear(d.life_date),
    };
  }
  if (work.source.startsWith('SMK')) {
    const d = (await getJSON(`https://api.smk.dk/api/v1/art/?object_number=${encodeURIComponent(id)}&lang=en`)).items[0];
    const maker = (d.production || [])[0] || {};
    const born = maker.creator_date_of_birth ? +maker.creator_date_of_birth.slice(0, 4) : null;
    const english = (d.titles || []).find(t => /engelsk|english/i.test(t.language || ''));
    const nationality = { dansk: 'Danish', svensk: 'Swedish', norsk: 'Norwegian', tysk: 'German', fransk: 'French',
      amerikansk: 'American', britisk: 'British', engelsk: 'English', islandsk: 'Icelandic', 'færøsk': 'Faroese',
      finsk: 'Finnish', hollandsk: 'Dutch', italiensk: 'Italian', spansk: 'Spanish', polsk: 'Polish' }[(maker.creator_nationality || '').toLowerCase()];
    return {
      story: [...(d.labels || []).map(l => l.text), ...(d.content_description || []), ...(d.notes || [])].flatMap(t => paragraphs(t, /<\w/.test(t))),
      life: [nationality, born && `born ${born}`].filter(Boolean).join(', '),
      facts: [(d.object_names || []).map(o => o.name).join(', '), smkSize(d.dimensions)],
      tags: d.techniques || [],
      englishTitle: english && english.title,
      origin: [d.on_display ? 'On view now.' : 'In the collection (not on view right now).',
               d.acquisition_date_precision && `Joined the collection in ${d.acquisition_date_precision}.`,
               ...(d.credit_line || []).map(c => `${c}.`), `Object number ${d.object_number}.`],
      born,
    };
  }
  if (work.source === 'DeviantArt') {
    const d = await getJSON('/api/deviantart?page=' + encodeURIComponent(work.page), 30000);
    if (d.error) throw new Error(d.error);
    const a = d.artist || {};
    const about = [
      a.realName && a.realName !== a.username ? `${a.realName}, known on DeviantArt as ${a.username}.` : `Known on DeviantArt as ${a.username}.`,
      [a.level, a.specialty].filter(Boolean).join(' · '),
      a.tagline && `“${a.tagline}”`,
      ...paragraphs(a.bio, true),
      a.website && `Website: ${displayPath(a.website)}`,
    ].filter(Boolean);
    return {
      story: paragraphs(d.description, true),
      life: a.specialty || '',
      facts: [d.created && `Posted ${longDate(d.created)}`, d.resolution && `${d.resolution.replace('x', ' × ')} px`],
      tags: (d.tags || []).slice(0, 10),
      origin: [`Shared online on DeviantArt by ${a.username || work.artist}${d.created ? ', ' + longDate(d.created) : ''}.`,
               d.views != null && `${d.views.toLocaleString()} views and ${(d.favourites || 0).toLocaleString()} favourites so far.`,
               'Chosen for the show from the pieces DeviantArt\'s staff pick each day, and the artists behind them.'],
      artist: { paragraphs: about, pic: a.usericon },
    };
  }
  return { story: [], facts: [], tags: [], origin: [] };
}

// SMK gives sizes in Danish ("højde", "bredde"), in millimetres: the first height and width, in cm.
function smkSize(dims) {
  if (!dims) return '';
  const pick = type => dims.find(x => x.type === type);
  const h = pick('højde'), w = pick('bredde');
  if (!h || !w) return '';
  const cm = x => +(x.unit === 'millimeter' ? x.value / 10 : x.value).toFixed(1);
  return `${cm(h)} × ${cm(w)} cm`;
}

// ------------------------------------------------------------------ Wikipedia

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

// ------------------------------------------------------------------ the map

let worldShapes = null;
function loadWorld() {
  worldShapes ??= getJSON('https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-50m.json', 30000)
    .then(t => topojson.feature(t, t.objects.countries).features)
    .catch(e => { worldShapes = null; throw e; });
  return worldShapes;
}

async function drawMap(countries, museum, token) {
  const box = $('map');
  let features;
  try { features = await loadWorld(); } catch { box.replaceChildren(); return; }
  if (token !== renderToken || !window.d3) return;

  const w = box.clientWidth, h = box.clientHeight;
  const ids = new Set(countries.map(c => c.ccn3).filter(Boolean));
  const homes = features.filter(f => ids.has(String(f.id)));
  const dots = countries.filter(c => c.latlng && c.latlng.length).map(c => [c.latlng[1], c.latlng[0]]);
  const points = [...dots, ...(museum ? [museum.at] : [])];

  // Turn the globe so the countries and the museum sit in the middle (no route cut in half at the edge),
  // then fit them in, but never zoom in so far that you can't tell where in the world it is.
  const focus = { type: 'FeatureCollection', features: [...homes, ...points.map(p => ({ type: 'Feature', geometry: { type: 'Point', coordinates: p } }))] };
  const middle = points.length > 1 ? d3.geoInterpolate(points[0], points[points.length - 1])(0.5) : (points[0] || [0, 20]);
  const projection = d3.geoNaturalEarth1().rotate([-middle[0], 0]);
  projection.fitExtent([[w * .12, h * .14], [w * .88, h * .86]], focus);
  const most = w * 0.9;
  if (projection.scale() > most) {
    projection.scale(most).translate([w / 2, h / 2]);
    const c = projection(d3.geoCentroid(focus));
    projection.translate([w - c[0], h - c[1]]);
  }
  const path = d3.geoPath(projection);

  const svg = d3.create('svg').attr('viewBox', `0 0 ${w} ${h}`);
  svg.append('g').selectAll('path').data(features).join('path')
    .attr('class', f => ids.has(String(f.id)) ? 'land home' : 'land').attr('d', path);
  if (museum && dots.length) {
    svg.append('path').attr('class', 'route')
      .attr('d', path({ type: 'LineString', coordinates: [dots[0], museum.at] }));
  }
  for (const p of dots) {
    const [x, y] = projection(p);
    svg.append('circle').attr('class', 'ring').attr('cx', x).attr('cy', y).attr('r', 7);
    svg.append('circle').attr('class', 'dot').attr('cx', x).attr('cy', y).attr('r', 5);
  }
  if (museum) {
    const [x, y] = projection(museum.at);
    svg.append('rect').attr('class', 'museum').attr('x', x - 5).attr('y', y - 5).attr('width', 10).attr('height', 10);
    const right = x < w - 130;
    svg.append('text').attr('class', 'label').attr('x', right ? x + 11 : x - 11).attr('y', y + 4)
      .attr('text-anchor', right ? 'start' : 'end').text(museum.short);
  }
  box.replaceChildren(svg.node());
}

// ------------------------------------------------------------------ filling the screen

let renderToken = 0;

async function render(work) {
  const token = ++renderToken;
  const main = $('main');
  main.classList.add('loading');
  await new Promise(r => setTimeout(r, 450));            // let the old one fade out
  if (token !== renderToken) return;

  const labels = work.country.split(' / ');
  const countries = labels.map(countryFacts);
  const museum = MUSEUMS[work.source] || null;

  // What's known straight away, from the art list.
  $('flag').replaceChildren(flagImg(countries[0], 40));
  $('eyebrow').textContent = [labels.join(' & '), work.date].filter(Boolean).join(' · ');
  $('title').textContent = work.title || 'Untitled';
  $('artist').textContent = work.artist;
  $('life').textContent = '';
  setFacts($('facts'), []);
  document.querySelectorAll('.tags').forEach(t => t.remove());
  $('story').replaceChildren();
  $('artistText').replaceChildren();
  $('artistPic').hidden = true;
  $('link').textContent = displayPath(work.page);
  showCountry(countries, labels, token);
  showOrigin(work, museum, null);
  $('map').replaceChildren();
  drawMap(countries, museum, token);

  main.classList.remove('empty', 'loading');
  $('waiting').classList.add('gone');

  // The details: the piece's record at its source, then the artist.
  let d = null;
  try { d = await detailsFrom(work); } catch (e) { console.warn('details', e); }
  if (token !== renderToken) return;
  d ??= { story: [], facts: [], tags: [], origin: [] };

  if (d.englishTitle && d.englishTitle !== work.title) $('title').textContent = `${work.title} (${d.englishTitle})`;
  $('life').textContent = d.life || '';
  setFacts($('facts'), d.facts || []);
  if ((d.tags || []).length) {
    const tags = document.createElement('div');
    tags.className = 'tags';
    for (const t of d.tags) tags.append(Object.assign(document.createElement('span'), { textContent: t }));
    $('facts').after(tags);
  }
  setProse($('story'), d.story || [], work.source === 'DeviantArt'
    ? "The artist didn't write anything about this piece."
    : "The museum hasn't written about this piece yet.");
  showOrigin(work, museum, d.origin);

  if (d.artist) {
    showArtist(d.artist.paragraphs, d.artist.pic);
  } else {
    const s = await wikiArtist(work.artist, d.born);
    if (token !== renderToken) return;
    if (s) showArtist(paragraphs(s.extract).concat([`From Wikipedia: ${s.title}`]), s.thumbnail && s.thumbnail.source);
    else showArtist([`${work.artist}${d.life ? ' (' + d.life + ')' : ''} is a living artist from ${labels.join(' and ')}.`,
                     `${work.source} has this piece in its collection. There isn't more written about the artist yet.`]);
  }
}

function showArtist(paras, pic) {
  setProse($('artistText'), paras, '');
  const img = $('artistPic');
  img.hidden = !pic;
  if (pic) { img.src = pic; img.onerror = () => { img.hidden = true; }; }
}

async function showCountry(countries, labels, token) {
  const main = countries[0];
  $('countryFlag').replaceChildren(flagImg(main, 80));
  $('countryName').textContent = labels.length > 1 ? labels.join(' & ') : main.name;
  const facts = [
    ['Capital', main.capital.join(', ')],
    ['Region', [main.subregion || main.region, main.partOf && `part of the ${main.partOf}`].filter(Boolean).join(', ')],
    ['Languages', main.languages.slice(0, 4).join(', ')],
  ];
  if (labels.length > 1) facts.push(['Also', labels.slice(1).join(', ')]);
  $('countryFacts').replaceChildren(...facts.filter(f => f[1]).flatMap(([k, v]) => [
    Object.assign(document.createElement('dt'), { textContent: k }),
    Object.assign(document.createElement('dd'), { textContent: v }),
  ]));
  $('countryText').replaceChildren();
  const s = await wikiSummary(main.name === labels[0] ? main.name : labels[0]);
  if (token !== renderToken) return;
  setProse($('countryText'), s && s.type === 'standard' ? paragraphs(s.extract) : [], '');
}

function showOrigin(work, museum, lines) {
  const box = $('origin');
  box.replaceChildren();
  const head = document.createElement('div');
  const strong = document.createElement('strong');
  strong.textContent = work.source;
  head.append(strong, museum ? ` · ${museum.city}` : '');
  box.append(head);
  for (const line of (lines || []).filter(Boolean)) box.append(Object.assign(document.createElement('div'), { textContent: line }));
}

// ------------------------------------------------------------------ long text scrolls itself

// Text that doesn't fit drifts upward while the piece is up: it waits a few seconds, then scrolls to the
// end in time for the next piece. The clock stops while the show is paused.
let scrollClock = 0, lastFrame = performance.now();
function restartScroll() { scrollClock = 0; document.querySelectorAll('.scroller').forEach(s => { s.scrollTop = 0; }); }
function scrollFrame(t) {
  const dt = t - lastFrame;
  lastFrame = t;
  if (!now || !now.paused) scrollClock += dt;
  const total = ((now && now.seconds) || 60) * 1000;
  const progress = Math.min(1, Math.max(0, (scrollClock - 7000) / (total - 17000)));
  for (const s of document.querySelectorAll('.scroller')) {
    const extra = s.scrollHeight - s.clientHeight;
    s.classList.toggle('overflowing', extra > 4);
    if (extra > 4) s.scrollTop = extra * progress;
  }
  // The bar along the bottom and the time until the next piece.
  if (now) {
    const left = now.nextAt ? Math.max(0, now.nextAt - Date.now()) : null;
    $('progress').style.width = left == null ? (now.paused ? $('progress').style.width : '0') : `${100 * (1 - left / total)}%`;
    $('countdown').textContent = now.paused ? 'Paused' : left == null ? '' :
      `Next piece in ${Math.floor(left / 60000)}:${String(Math.ceil(left / 1000) % 60).padStart(2, '0')}`;
  }
  requestAnimationFrame(scrollFrame);
}
requestAnimationFrame(scrollFrame);

// ------------------------------------------------------------------ talking to the left screen

let now = null, theme = 'dark';

function send(key, value) {
  fetch('/api/state?key=' + key, { method: 'POST', body: JSON.stringify(value) }).catch(() => {});
}
function command(what) { send('command', { n: Date.now(), do: what }); }

function applyTheme(t) {
  theme = t === 'light' ? 'light' : 'dark';
  document.body.classList.toggle('light', theme === 'light');
  $('theme').textContent = theme === 'light' ? '☾  Dark' : '☀  Light';
}

async function listen() {
  let v = -1;
  for (;;) {
    try {
      const r = await (await fetch('/api/state?v=' + v, { cache: 'no-store' })).json();
      v = r.v;
      applyTheme(r.state.theme);
      if (r.state.now) {
        const changed = !now || now.work.page !== r.state.now.work.page;
        now = r.state.now;
        $('pause').classList.toggle('on', !!now.paused);
        $('pause').textContent = now.paused ? '▶ Play' : '❚❚';
        $('back').disabled = !now.canGoBack;
        if (changed) render(now.work);
      }
    } catch {
      await new Promise(r => setTimeout(r, 2000));   // the server is starting or closing
    }
  }
}

$('back').addEventListener('click', () => command('back'));
$('next').addEventListener('click', () => command('next'));
$('pause').addEventListener('click', () => command('pause'));
$('theme').addEventListener('click', () => send('theme', theme === 'light' ? 'dark' : 'light'));
$('close').addEventListener('click', () => window.close());
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowRight') command('next');
  else if (e.key === 'ArrowLeft') command('back');
  else if (e.key === ' ') { e.preventDefault(); command('pause'); }
  else if (e.key === 'Escape') window.close();
});

applyTheme('dark');
listen();
