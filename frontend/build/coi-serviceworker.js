/*!
 * COI (Cross-Origin Isolation) service worker for NXT1's WebContainer
 * preview. Without this, `window.crossOriginIsolated` is false and
 * @webcontainer/api refuses to boot.
 *
 * Strategy (the canonical "coi-serviceworker" pattern used by
 * StackBlitz / Vite playgrounds / chef.convex.dev):
 *
 *   1. On install + activate, claim all clients so we start intercepting
 *      requests on the very first load (after a one-time reload prompt).
 *   2. On every fetch we make to ourselves, decorate the response with the
 *      two headers browsers need to flip `crossOriginIsolated = true`:
 *           Cross-Origin-Opener-Policy:   same-origin
 *           Cross-Origin-Embedder-Policy: require-corp
 *      For external resources we additionally inject Cross-Origin-Resource-
 *      Policy: cross-origin so they remain loadable under COEP=require-corp.
 *
 * Activation guard
 * ----------------
 * Only the WebContainer preview surface (`/p/webcontainer/*` and the
 * builder page that hosts it) needs isolation. We register the SW only
 * from those routes (see registerWebContainerSw() in src/lib/webcontainer/index.js)
 * to avoid imposing COEP on the rest of the app — it can otherwise break
 * 3rd-party images / analytics / OAuth redirects.
 */
/* eslint-disable no-restricted-globals */

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  if (event.data && event.data === "deregister") {
    self.registration.unregister().then(() => self.clients.matchAll())
      .then((clients) => clients.forEach((c) => c.navigate(c.url)));
  }
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  // Don't try to intercept range requests for media — breaks video/audio.
  if (req.cache === "only-if-cached" && req.mode !== "same-origin") return;

  event.respondWith(
    fetch(req)
      .then((response) => {
        if (response.status === 0) return response;

        const newHeaders = new Headers(response.headers);
        newHeaders.set("Cross-Origin-Embedder-Policy", "require-corp");
        newHeaders.set("Cross-Origin-Opener-Policy", "same-origin");
        // Keep cross-origin resources loadable under COEP.
        if (req.mode === "no-cors" || new URL(req.url).origin !== self.location.origin) {
          newHeaders.set("Cross-Origin-Resource-Policy", "cross-origin");
        }
        return new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: newHeaders,
        });
      })
      .catch((e) => {
        if (req.destination !== "" || req.destination === "document") {
          // eslint-disable-next-line no-console
          console.error("[coi-sw] fetch failed", e);
        }
        throw e;
      }),
  );
});
