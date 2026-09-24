const CACHE_NAME = "digital-akk-github-v2";
const BASE = new URL("./", self.location.href);

function appUrl(path) {
  return new URL(path, BASE).toString();
}

const SHELL = [
  "index.html",
  "offline.html",
  "manifest.webmanifest",
  "config.json",
  "i18n.json",
  "page-catalog.json",
  "assets/app-DWPFIQMZ.css",
  "assets/user-LAD5EIO2.js",
  "assets/akk-logo-current.jpg",
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
        .then((response) => {
          if (response.ok && url.pathname.endsWith("/")) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(appUrl("index.html"), copy));
          }
          return response;
        })
        .catch(async () => (await caches.match(appUrl("index.html"))) || caches.match(appUrl("offline.html")))
    );
    return;
  }

  const basePath = new URL("./", BASE).pathname;
  const isAppAsset =
    url.pathname.startsWith(new URL("icons/", BASE).pathname) ||
    url.pathname.startsWith(new URL("assets/", BASE).pathname) ||
    ["manifest.webmanifest", "config.json", "i18n.json", "page-catalog.json"].some(
      (name) => url.pathname === new URL(name, BASE).pathname
    );

  if (isAppAsset) {
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
