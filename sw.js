const CACHE = 'agrino-v1';
const STATIC = ['/', '/index.html', '/style.css', '/app.js'];

self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)));
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(caches.keys().then(keys =>
        Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ));
    self.clients.claim();
});

self.addEventListener('fetch', e => {
    // Always fetch API calls live — never cache sensor data
    if (e.request.url.includes('/latest') ||
        e.request.url.includes('/view-log') ||
        e.request.url.includes('/download-log')) {
        return;
    }
    e.respondWith(
        caches.match(e.request).then(cached => cached || fetch(e.request))
    );
});
