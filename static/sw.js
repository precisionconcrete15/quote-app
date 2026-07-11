// Qotixo service worker
// Deliberadamente simple: solo cachea los assets estáticos (íconos, manifest),
// y deja pasar todo lo demás directo a la red. Esto evita mostrar datos
// desactualizados en páginas dinámicas como cotizaciones, pagos o el dashboard.

const CACHE_NAME = "qotixo-static-v1";
const STATIC_ASSETS = [
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/manifest.json"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Solo servimos desde cache los archivos estáticos que ya cacheamos.
  // Todo lo demás (HTML, formularios, pagos) va siempre directo a la red.
  if (STATIC_ASSETS.some((asset) => url.pathname === asset)) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
  }
});