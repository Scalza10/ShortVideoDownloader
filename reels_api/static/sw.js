// Minimal service worker: no caching, no fetch handler.
// Exists only so older Android Chrome versions treat the page as installable.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
