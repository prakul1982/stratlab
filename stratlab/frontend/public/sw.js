/* StratLab service worker: phone notifications, and the app shell when offline. Your data is never cached. */
const SHELL = "stratlab-shell-v4";          // v4: a v3 shell may be a public page that was kept as the app (v3 kept every HTML page)
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
// (R8B-011: an iPhone on a 503 saw "StratLab can't be reached" with no way to retry). The retry is a timer, not a
// <meta refresh>: a delayed refresh takes control of the page from the reader (axe: meta-refresh, R13S-013).
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function offlinePage(path) {
  const to = esc(path || "/");
  // in StratLab's own paper, ink and card, light and dark (RC7-001: it was a bare white page, plain text in the device's default font)
  const css = ':root{--p:#F5F1E8;--c:#FFFDF8;--i:#1D1B17;--m:#5C574D;--l:#E2DAC8;--o:#F5F1E8;color-scheme:light}'
    + '@media (prefers-color-scheme:dark){:root{--p:#141311;--c:#1F1D1A;--i:#EFE9DC;--m:#B3AC9C;--l:#34312A;--o:#141311;color-scheme:dark}}'
    + 'body{margin:0;background:var(--p);color:var(--i);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}'
    + 'main{box-sizing:border-box;max-width:min(480px,calc(100% - 32px));margin:16vh auto 0;padding:24px;background:var(--c);border:1px solid var(--l);border-radius:14px;display:flex;flex-direction:column;gap:12px}'
    + '.b{display:flex;align-items:center;gap:10px;font-weight:600;color:var(--m)}.b img{width:24px;height:24px}'
    + 'h1{font:600 26px/1.2 Georgia,serif;margin:0}p{margin:0;color:var(--m)}form{margin:0}'
    + 'button{font:600 15px system-ui,sans-serif;min-height:44px;padding:0 24px;border:0;border-radius:10px;background:var(--i);color:var(--o);cursor:pointer}'
    + 'button:focus-visible{outline:2px solid var(--i);outline-offset:3px}';
  return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    + '<meta name="color-scheme" content="light dark">'
    + '<title>StratLab: offline</title><style>' + css + '</style></head><body>'
    + '<main><span class="b"><img src="/favicon.svg" alt="" width="24" height="24">StratLab</span>'
    + '<h1>StratLab can\'t be reached</h1><p>Check the connection, then reload. This page also tries again by itself in 30 seconds.</p>'
    + '<form method="get" action="' + to + '"><button type="submit" data-testid="offline-reload">Reload</button></form></main>'
    + '<script>setTimeout(function(){location.reload()},30000)</script></body></html>';
}
function offline(path) {
  try { return new Response(offlinePage(path), { status: 503, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } }); }
  catch { return Response.error(); }
}
// The addresses that are the app itself (vercel.json sends them all to index.html): only a page load at one of these is kept as the
// app shell. Everything else that answers with HTML is its own page and must never stand in for the app when offline: the server's
// pages (/stocks, /c, /v, /unsubscribe, /email, /news-link), the pages built ahead of time (the policies, /pricing, /faq, /about,
// /help, /login, /signup, /plans, /library and each /library/<id>) and a shared /verdict.
const APP_PATH = /^\/(?:mine|all|features|trade|invest|money|notebooks|new|n|import|options|paper|upgrade|account|settings|assistant|app|invite|admin|news|holdings|tax-report|alerts|research|scans|watchlist|dev|calendar)(?:\/|$)/;
const isAppPath = (path) => path === "/" || APP_PATH.test(path);
const shellOr = (fallback) => caches.match("/").then((hit) => hit || fallback()).catch(() => fallback());

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

// pages: always the network first (so updates show at once); the cached shell when offline, and when the server answers with an
// error (a failed page load would otherwise leave plain error text; the shell starts the app at the address that was asked for)
const good = (res, type) => res.ok && (res.headers.get("content-type") || "").includes(type);

// The files every page needs before it starts (config.js, theme.js, boot.js): the network first (for at most STATIC_WAIT ms), the
// last good copy when it fails, is slow or isn't JavaScript. With no copy kept either: one plain network request (what the page
// would have made without this worker), and only then an ordinary 503 answer. Never Response.error(): Safari reports it as
// "Response served by service worker is an error" and the page stayed on "Opening…" (round 39).
const STATIC_WAIT = 8000;
const within = (p, ms) => Promise.race([p, new Promise((_, no) => setTimeout(() => no(new Error("slow")), ms))]);
function unavailable() {
  try { return new Response("", { status: 503, headers: { "content-type": "text/javascript; charset=utf-8", "cache-control": "no-store" } }); }
  catch { return Response.error(); }
}
function staticFile(req, path) {
  return within(fetch(req), STATIC_WAIT).then((res) => {
    if (good(res, "javascript")) { const copy = res.clone(); caches.open(SHELL).then((c) => c.put(path, copy)).catch(() => undefined); return res; }
    return caches.match(path).then((hit) => hit || res);
  }).catch(() => caches.match(path).catch(() => undefined)
    .then((hit) => hit || fetch(req.url, { cache: "no-store" }).catch(() => unavailable())));
}
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === self.location.origin && STATIC.includes(url.pathname)) {
    e.respondWith(staticFile(req, url.pathname));
    return;
  }
  // the logo the start-up and offline cards carry (RC7-001): the copy kept at install, so it shows with no connection
  if (url.origin === self.location.origin && url.pathname === "/favicon.svg") {
    e.respondWith(caches.match("/favicon.svg").then((hit) => hit || fetch(req)).catch(() => Response.error()));
    return;
  }
  if (req.mode !== "navigate") return;
  if (url.pathname.startsWith("/v/")) return;          // shared-verdict previews come from the server, not the app
  e.respondWith(fetch(req).then((res) => {
    if (good(res, "text/html")) {
      if (isAppPath(url.pathname)) {
        const copy = res.clone();
        caches.open(SHELL).then((c) => c.put("/", copy)).catch(() => undefined);
      }
      return res;
    }
    // a server error on an app address: the app shell (it starts the app at that address). Any other page is the server's own, and
    // its error page (the self-refreshing "being prepared" 503) is shown as it is; the offline page is only for a failed fetch
    if (res.status >= 500 && isAppPath(url.pathname)) return shellOr(() => offline(url.pathname + url.search));
    return res;
  }).catch(() => (isAppPath(url.pathname) ? shellOr(() => offline(url.pathname + url.search)) : offline(url.pathname + url.search))));
});

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "StratLab", {
    body: d.body || "", icon: "/icon-192.png", badge: "/icon-192.png", tag: d.tag || undefined, data: { url: d.url || "/paper" },
  }));
});

// A push can carry any url; only a path on this site is opened, anything else opens the home page.
function sameSitePath(u) {
  if (typeof u !== "string" || u[0] !== "/" || u[1] === "/" || u[1] === "\\" || /[\u0000-\u001f]/.test(u)) return "/";
  try { return new URL(u, self.location.origin).origin === self.location.origin ? u : "/"; } catch (e) { return "/"; }
}

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = sameSitePath((e.notification.data && e.notification.data.url) || "/paper");
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
