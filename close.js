// close.js: the same in every one of Dylan's apps. Load it first on each page.
// - DylanClose.isControl(el): is this a button, link, slider or anything else meant to be clicked? A click there does
//   its own job and never closes the app; only a click on empty space closes (in the apps that close that way).
// - Inside Dylan's Morning or Night Screens (or the App Tester) the app sits in a frame, where it can't close itself:
//   closing then asks the Screens to close instead, and a click on empty space or the arrow keys go to the Screens.
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
  const tell = msg => { try { window.parent.postMessage({ dylanScreens: msg }, '*'); } catch (e) { /* no parent */ } };
  const realClose = window.close.bind(window);
  function close() { if (inFrame) tell('close'); else realClose(); }
  if (inFrame) {
    window.close = close;   // every app's X and Esc now close the Screens around it
    // An empty spot clicked closes the Screens (as clicking them always did); controls work as usual.
    document.addEventListener('click', e => { if (!e.defaultPrevented && !isControl(e.target)) close(); });
    document.addEventListener('keydown', e => {
      if (['ArrowLeft', 'ArrowRight', ' '].includes(e.key) && !isControl(e.target)) tell('key:' + e.key);
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
