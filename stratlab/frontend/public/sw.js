/* StratLab service worker: phone notifications, and the app shell when offline. Your data is never cached. */
const SHELL = "stratlab-shell-v3";
// the small files every page needs before it can start: the last good copy is kept, so one that fails to download (an error page
// where the script should be) is replaced by it instead of leaving the app without its settings
const STATIC = ["/config.js", "/theme.js", "/boot.js"];

// each file on its own: one that fails to download (a 502 on the icon) no longer leaves the whole shell uncached (R6O-006)
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => Promise.all(["/", "/favicon.svg", "/icon-192.png", ...STATIC]
    .map((f) => c.add(f).catch(() => undefined)))).catch(() => undefined));
  self.skipWaiting();
});

// what a page load gets when the network fails and no copy of the app is kept: a plain offline page, never nothing (a
// navigation answered with nothing showed Safari's "Returned response is null" error page, R6O-006). It has a Reload button
// that works without scripts (a form that asks for the same address again), and tries again by itself after 30 seconds
// (R8B-011: an iPhone on a 503 saw "StratLab can't be reached" with no way to retry).
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function offlinePage(path) {
  const to = esc(path || "/");
  return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    + '<meta http-equiv="refresh" content="30"><meta name="color-scheme" content="light dark">'
    + '<title>StratLab: offline</title></head><body style="font-family:system-ui,sans-serif;margin:0;padding:48px 16px;text-align:center">'
    + '<main><h1 style="font-size:22px">StratLab can\'t be reached</h1><p>Check the connection, then reload. This page also tries again by itself in 30 seconds.</p>'
    + '<form method="get" action="' + to + '"><button type="submit" data-testid="offline-reload" style="font:inherit;padding:10px 20px;border-radius:8px;'
    + 'border:1px solid currentColor;background:none;color:inherit;cursor:pointer">Reload</button></form></main></body></html>';
}
function offline(path) {
  try { return new Response(offlinePage(path), { status: 503, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } }); }
  catch { return Response.error(); }
}
const shellOr = (fallback) => caches.match("/").then((hit) => hit || fallback()).catch(() => fallback());

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

// pages: always the network first (so updates show at once); the cached shell when offline, and when the server answers with an
// error (a failed page load would otherwise leave plain error text; the shell starts the app at the address that was asked for)
const good = (res, type) => res.ok && (res.headers.get("content-type") || "").includes(type);
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === self.location.origin && STATIC.includes(url.pathname)) {
    // network first, the last good copy when it fails or isn't JavaScript
    e.respondWith(fetch(req).then((res) => {
      if (good(res, "javascript")) { const copy = res.clone(); caches.open(SHELL).then((c) => c.put(url.pathname, copy)).catch(() => undefined); return res; }
      return caches.match(url.pathname).then((hit) => hit || res);
    }).catch(() => caches.match(url.pathname).then((hit) => hit || Response.error())));
    return;
  }
  if (req.mode !== "navigate") return;
  if (url.pathname.startsWith("/v/")) return;          // shared-verdict previews come from the server, not the app
  e.respondWith(fetch(req).then((res) => {
    if (good(res, "text/html")) {
      const copy = res.clone();
      caches.open(SHELL).then((c) => c.put("/", copy)).catch(() => undefined);
      return res;
    }
    // a server error with no copy of the app kept: the offline page with its Reload, not the host's bare error page
    if (res.status >= 500) return shellOr(() => offline(url.pathname + url.search));
    return res;
  }).catch(() => shellOr(() => offline(url.pathname + url.search))));
});

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "StratLab", {
    body: d.body || "", icon: "/icon-192.png", badge: "/icon-192.png", tag: d.tag || undefined, data: { url: d.url || "/paper" },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/paper";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
