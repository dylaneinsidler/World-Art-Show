// close.js: the same in every one of Dylan's apps. Load it first on each page.
// - DylanClose.isControl(el): is this a button, link, slider or anything else meant to be clicked? A click there does
//   its own job and never closes the app; only a click on empty space closes (in the apps that close that way).
// - Inside Dylan's Morning or Night Screens (or the App Tester) the app sits in a frame, where it can't close itself:
//   closing then asks the Screens to close instead, and a click on empty space, Esc or the arrow keys go to the Screens.
window.DylanClose = (() => {
  const inFrame = window.parent !== window;
  const CONTROLS = 'a[href], button, input, select, textarea, label, summary, option, video, audio, iframe, ' +
    '[role="button"], [role="link"], [role="slider"], [role="tab"], [contenteditable="true"], [onclick], [data-click]';
  function isControl(el) {
    for (; el && el.nodeType === 1 && el !== document.body && el !== document.documentElement; el = el.parentElement) {
      if (el.matches(CONTROLS)) return true;
      const c = getComputedStyle(el).cursor;
      if (c === 'pointer' || c === 'grab' || c === 'grabbing' || c === 'move' || c === 'text' || c.endsWith('resize')) return true;
    }
    return false;
  }
  // Both screens appear together: the launcher notes when it opened them (opened.js); each page stays black until
  // a moment just after that (about how long Chrome takes to start both), or until it's ready if that's later,
  // then fades in. Only right after opening; never stuck (at most 8 seconds).
  const opened = window.DYLAN_OPENED;
  if (!inFrame && opened && Date.now() - opened < 15000) {
    const root = document.documentElement, st = document.createElement('style');
    st.textContent = 'html.dylan-wait { background: #000 !important; } html.dylan-wait body { opacity: 0 !important; } body { transition: opacity .3s ease; }';
    (document.head || root).appendChild(st);
    root.classList.add('dylan-wait');
    const show = () => root.classList.remove('dylan-wait');
    const ready = new Promise(r => {
      const go = () => (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => setTimeout(r, 150));
      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
    });
    const together = new Promise(r => setTimeout(r, Math.max(0, opened + 2200 - Date.now())));
    Promise.all([ready, together]).then(show);
    setTimeout(show, Math.max(0, opened + 8000 - Date.now()));
  }
  const tell = msg => { try { window.parent.postMessage({ dylanScreens: msg }, '*'); } catch (e) { /* no parent */ } };
  const realClose = window.close.bind(window);
  function close() { if (inFrame) tell('close'); else realClose(); }
  if (inFrame) {
    window.close = close;   // every app's X and Esc now close the Screens around it
    // An empty spot clicked closes the Screens (as clicking them always did); controls work as usual.
    document.addEventListener('click', e => { if (!e.defaultPrevented && !isControl(e.target)) close(); });
    document.addEventListener('keydown', e => {
      if (['ArrowLeft', 'ArrowRight', ' '].includes(e.key) && !isControl(e.target)) tell('key:' + e.key);
      else if (e.key === 'Escape' && !e.defaultPrevented) close();   // Esc closes the Screens, whatever the app
    });
    let moved = 0;   // the Screens' buttons come back when the mouse moves, over the app too
    document.addEventListener('mousemove', () => { if (Date.now() - moved > 500) { moved = Date.now(); tell('move'); } });
  }
  // For the apps that close on any click: wire it up with this, so controls are left alone.
  function onEmptyClick(fn = close) {
    if (inFrame) return;   // the frame case is handled above
    document.addEventListener('click', e => { if (!e.defaultPrevented && !isControl(e.target)) fn(e); });
  }
  return { isControl, close, onEmptyClick, inFrame };
})();
