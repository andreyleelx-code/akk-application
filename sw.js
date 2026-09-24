const CACHE_NAME = "digital-akk-github-v1";
const BASE = new URL("./", self.location.href);

function appUrl(path) {
  return new URL(path, BASE).toString();
}

const SHELL = [
  "offline.html",
  "manifest.webmanifest",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/maskable-512.png"
].map(appUrl);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key.startsWith("digital-akk-") && key !== CACHE_NAME)
            .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request, { cache: "no-store" })
        .catch(() => caches.match(appUrl("offline.html")))
    );
    return;
  }

  if (url.pathname.startsWith(new URL("icons/", BASE).pathname) ||
      url.pathname.startsWith(new URL("assets/", BASE).pathname) ||
      url.pathname === new URL("manifest.webmanifest", BASE).pathname ||
      url.pathname === new URL("config.json", BASE).pathname ||
      url.pathname === new URL("i18n.json", BASE).pathname) {
    event.respondWith(
      fetch(request, { cache: "no-store" })
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
  }
});
