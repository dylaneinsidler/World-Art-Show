// Photographs the app's screens side by side, the way they sit on the two monitors, for each scene in
// screenshots.json (next to this file). Run by take-screenshots.ps1:
//   node screenshots.mjs <app folder> <output folder> <temp folder> <screenshots.json>
// It drives a hidden Chrome over its DevTools connection. Each screen gets a fixed 1920x1080 frame,
// which is what the monitors show (a plain headless screenshot resizes the page after it has laid out).
//
// screenshots.json:
//   { "left": "page.html", "right": "page.html" (or null for a one-screen app),
//     "wait": milliseconds to let the pages finish drawing after their fonts load,
//     "scenes": [["01-name", "?query added to both pages"], ...] }
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [appDir, outDir, tempDir, configFile] = process.argv.slice(2);
const cfg = JSON.parse(fs.readFileSync(configFile, 'utf8'));
const devtools = 9343;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const W = 1920, H = 1080, width = cfg.right ? W * 2 : W;

const chromePath = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].find(p => fs.existsSync(p));

// A page of the app ("today.html", or "screen.html?side=left"), or a web address, with the scene's query added.
function page(p, query) {
  const [file, own = ''] = p.split('?');
  const base = /^https?:/.test(file) ? file : pathToFileURL(path.join(appDir, file)).href;
  const q = [own, (query || '').replace(/^\?/, '')].filter(Boolean).join('&');
  return base + (q ? '?' + q : '');
}
function showcase(query) {
  const file = path.join(tempDir, 'screens.html');
  const frames = [cfg.left, cfg.right].filter(Boolean)
    .map((p, i) => `<iframe id="s${i}" src="${page(p, query)}"></iframe>`).join('');
  fs.writeFileSync(file, `<!doctype html><html><head><meta charset="utf-8"><style>
    html, body { margin: 0; background: #000; overflow: hidden; }
    .screens { display: flex; width: ${width}px; height: ${H}px; }
    iframe { display: block; width: ${W}px; height: ${H}px; border: 0; }
  </style></head><body><div class="screens">${frames}</div></body></html>`);
  return pathToFileURL(file).href;
}

fs.mkdirSync(tempDir, { recursive: true });
const chrome = spawn(chromePath, [
  '--headless=new', `--remote-debugging-port=${devtools}`, `--user-data-dir=${path.join(tempDir, 'chrome-profile')}`,
  '--allow-file-access-from-files', `--window-size=${width},${H}`, '--no-first-run', '--hide-scrollbars',
  '--autoplay-policy=no-user-gesture-required', 'about:blank'],
  { stdio: 'ignore' });

async function getJSON(url, method = 'GET') {
  for (let i = 0; i < 60; i++) {
    try { return await (await fetch(url, { method })).json(); } catch { await sleep(250); }
  }
  throw new Error('Chrome did not start');
}

try {
  const tab = await getJSON(`http://127.0.0.1:${devtools}/json/new?about:blank`, 'PUT');
  const ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r));
  let id = 0;
  const pending = new Map();
  ws.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  });
  const send = (method, params = {}) => new Promise(r => {
    const i = ++id;
    pending.set(i, r);
    ws.send(JSON.stringify({ id: i, method, params }));
    setTimeout(() => { if (pending.has(i)) { pending.delete(i); r({}); } }, 60000);
  });
  const run = async code => (await send('Runtime.evaluate', { expression: code, returnByValue: true })).result?.result?.value;

  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width, height: H, deviceScaleFactor: 1, mobile: false });
  fs.mkdirSync(outDir, { recursive: true });

  for (const [name, query] of cfg.scenes) {
    await send('Page.navigate', { url: showcase(query) });
    // Wait (up to 20 seconds) for every screen's page and fonts, then let it finish drawing.
    for (let i = 0; i < 80; i++) {
      await sleep(250);
      const ready = await run(`[...document.querySelectorAll('iframe')].every(f => { try {
        const d = f.contentDocument; return d && d.readyState === 'complete' && d.fonts.status === 'loaded';
      } catch { return true; } })`);
      if (ready) break;
    }
    await sleep(cfg.wait ?? 5000);
    const shot = await send('Page.captureScreenshot', { format: 'jpeg', quality: 88 });
    fs.writeFileSync(path.join(outDir, `${process.env.SCREENSHOT_PREFIX || ''}${name}.jpg`), Buffer.from(shot.result.data, 'base64'));
    console.log('saved', name);
  }
} finally {
  chrome.kill();
}
