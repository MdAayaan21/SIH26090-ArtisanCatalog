/**
 * Minimal app-shell service worker: caches the static assets that make up
 * the capture UI so the app itself opens even with zero connectivity.
 * Data (drafts, media) is handled separately by IndexedDB, not by this cache.
 */
const CACHE_NAME = "kaarigar-shell-v1";
const APP_SHELL = [
  "./index.html",
  "./styles.css",
  "./app.js",
  "./db.js",
  "./compress.js",
  "./sync-daemon.js",
  "./manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Only cache-first for our own static shell; API calls always go to network
  // so drafts sync correctly and never serve stale pipeline results.
  if (APP_SHELL.some((path) => url.pathname.endsWith(path.replace("./", "")))) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
  }
});
