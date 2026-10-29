// Offline copy of the Anaesthesia Meetings Almanac. The page itself is fetched network-first so reviews arrive, with the cached copy as the fallback;
// icons, the manifest and fonts are cached on first use. Calendar files are never cached, so a tap always gets the current file.
const V = 'almanac-ec4dfc0bd2';
const CORE = ['./', './index.html', './manifest.json', './anaesthesia-meetings-icon-180-v2.png', './anaesthesia-meetings-icon-512-v2.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(V).then(c => c.addAll(CORE)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const req = e.request; if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const font = url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com';
  if (url.origin !== location.origin && !font) return;
  if (url.pathname.endsWith('.ics')) return;
  if (req.mode === 'navigate' || url.pathname.endsWith('/index.html') || url.pathname.endsWith('/')) {
    e.respondWith(fetch(req).then(r => { if (r.ok) { const copy = r.clone(); caches.open(V).then(c => { c.put('./index.html', copy.clone()); c.put('./', copy); }); } return r; }).catch(() => caches.match('./index.html')));
    return;
  }
  e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => { if (r.ok || r.type === 'opaque') { const copy = r.clone(); caches.open(V).then(c => c.put(req, copy)); } return r; })));
});
