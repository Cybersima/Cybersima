/* CyberSym SecureTrade phone shell. Live quotes always come from the PC. */
const SHELL = "cybersym-securetrade-shell-v1";
const PRECACHE = [
  "/",
  "/login",
  "/static/app.css",
  "/static/app.js",
  "/manifest.json",
  "/brand/logo",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== SHELL).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }
  if (url.pathname.startsWith("/api/") || url.pathname === "/ws" || url.pathname.startsWith("/ws")) {
    return;
  }
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response && response.ok && url.protocol.startsWith("http")) {
          const copy = response.clone();
          caches.open(SHELL).then((cache) => cache.put(request, copy)).catch(() => {});
        }
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match("/login")))
  );
});
