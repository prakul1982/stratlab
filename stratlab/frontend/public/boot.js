/* Starts before the app and watches it load. If a file the page needs fails to download (a dropped connection, a deploy
 * that replaced the old files), the page reloads once on its own; if that does not help, it says so and offers a Reload
 * button, instead of staying blank. A plain file, not part of the app bundle, so it works when the bundle does not. */
(function () {
  var KEY = "stratlab.reloaded";
  var WAIT = 60 * 1000;          // a second failure within this time shows the message instead of reloading again
  var SLOW = 10 * 1000;          // the app has not drawn anything after this long: say so, with a Reload button (round 39: Safari sat on "Opening…" for 20 s)

  function once() {
    try {
      var last = Number(sessionStorage.getItem(KEY) || 0);
      if (Date.now() - last < WAIT) return false;
      sessionStorage.setItem(KEY, String(Date.now()));
    } catch (e) { /* storage off: reload at most once per page view */
      if (window.__stratlabReloaded) return false;
      window.__stratlabReloaded = true;
    }
    return true;
  }

  var said = null;                // the notice this script put up, if any: { main, slow }

  function show(force, slow) {
    var root = document.getElementById("root");
    if (!root || (!force && !root.querySelector("[data-boot], .boot"))) return;       // once the app has drawn, its own error screen does this
    if (said && (slow || !said.slow)) return;                                        // said once is enough
    if (said && said.main.parentNode) said.main.parentNode.removeChild(said.main);    // "taking longer" gives way to "couldn't load"
    // the app has started drawing into the page: its elements are its own to change, so the notice goes above the page
    // instead (R68-004: emptying them under the app crashed it, "NotFoundError", and two error messages stacked)
    var owned = Object.keys(root).some(function (k) { return k.indexOf("__reactContainer") === 0; });
    if (owned && root.querySelector('[role="alert"]')) return;                        // the app already says what went wrong
    // a page whose words are already in the HTML (the policies, the 404): keep them readable and put the notice above them
    var keep = root.querySelector("[data-readable]");
    keep = keep && keep.hasAttribute && keep.hasAttribute("data-readable") ? keep : null;
    if (!keep && !owned) root.textContent = "";
    var main = document.createElement("main");         // the page's main landmark while it is the only thing on it
    var box = document.createElement("div");
    box.className = "boot boot-now";
    box.setAttribute("role", "alert");
    if (slow) box.setAttribute("data-slow", "1");
    main.appendChild(box);
    // the logo above the words: the card is StratLab's, not a bare browser page (RC7-001)
    var brand = document.createElement("span");
    brand.className = "boot-brand";
    var logo = document.createElement("img");
    logo.src = "/favicon.svg"; logo.alt = ""; logo.width = 24; logo.height = 24;
    logo.onerror = function () { logo.style.display = "none"; };      // no connection and no kept copy: the name alone, not a broken picture
    brand.appendChild(logo);
    var name = document.createElement("span");
    name.textContent = "StratLab";
    brand.appendChild(name);
    var h = document.createElement("h1");
    h.textContent = slow ? "Taking longer than usual" : "Couldn't load StratLab.";
    var p = document.createElement("p");
    p.textContent = slow ? "StratLab is still opening. If nothing changes, reload to try again."
      : "A file didn't download, which is usually a dropped connection. Reload to try again.";
    var b = document.createElement("button");
    b.type = "button";
    b.className = "boot-btn";
    b.textContent = "Reload";
    b.addEventListener("click", function () { location.reload(); });
    box.appendChild(brand); box.appendChild(h); box.appendChild(p); box.appendChild(b);
    said = { main: main, slow: !!slow };
    if (owned) {
      box.className += " boot-above";       // above the page, so it sits close to the top (the card's own margin, in index.html)
      main.setAttribute("role", "presentation");
      root.parentNode.insertBefore(main, root);
    } else if (keep) {
      box.className += " boot-above";
      main.setAttribute("role", "presentation");      // the page's own main stays the main landmark
      root.insertBefore(main, root.firstChild);
      if (keep.classList) keep.classList.remove("boot-wait");     // shown now, not after the fade-in delay
    } else root.appendChild(main);
  }

  /** A file failed to load: reload once, else say so. */
  function recover() {
    if (once()) location.reload(); else show();
  }

  // a saved sign-in: the page says "Opening StratLab…" while the app starts, never the visitor's marketing words for the seconds
  // a slow start takes (R29B-019); the style for it is in index.html
  try {
    for (var i = 0; i < localStorage.length; i++) {
      var k = localStorage.key(i);
      if (k && /^sb-.+-auth-token$/.test(k) && localStorage.getItem(k)) { document.documentElement.setAttribute("data-saved", "1"); break; }
    }
  } catch (e) { /* storage off */ }

  // the home address: only it shows the landing's start-up hero (LIVE13B-001)
  try {
    var path = location.pathname;
    if ((path === "/" || path === "/index.html") && !/[?&](fbclid=|utm_source=(facebook|fb|ig|instagram|meta)\b)/i.test(location.search || ""))
      document.documentElement.setAttribute("data-home", "1");
  } catch (e) {}

  // LIVE14A-014 / LIVE14B-003: the landing's hero words wait, hidden, for the faces they are drawn in (index.html), then show: once, at their
  // final size and place. The faces are the ones index.html preloads (publicFonts.mjs, seoPages.mjs heroFrame); their @font-face rules come
  // with the stylesheet, after this script, so they are looked for again as each stylesheet arrives. A browser with no font loading API, or
  // a page without those faces (once it has loaded), shows the words at once; index.html shows them after 3 s whatever happens.
  try { (function () {
    var html = document.documentElement, fonts = document.fonts;
    if (!html.hasAttribute("data-home")) return;
    function show() { html.setAttribute("data-faces", "1"); }
    if (!fonts || typeof fonts.load !== "function" || typeof Promise === "undefined") return show();
    // site78: and the eyebrow's mono face: on CI's phone the eyebrow showed on one line in the stand-in mono, then took two when IBM Plex Mono
    // came at 2.8 s, and the heading, lede, buttons and example card all moved down a line (CLS 0.018)
    var FACES = ["400 1em Fraunces", "italic 400 1em Fraunces", '400 1em "IBM Plex Sans"', '600 1em "IBM Plex Sans"', '400 1em "IBM Plex Mono"'];
    var loaded = false;
    function look() {
      if (html.hasAttribute("data-faces")) return;
      Promise.all(FACES.map(function (f) { return fonts.load(f); })).then(function (got) {
        for (var i = 0; i < got.length; i++) if (!got[i].length) { if (loaded) show(); return; }      // not here yet: the next stylesheet
        show();
      }, show);       // a face that failed to download: the stand-in, now
    }
    document.addEventListener("load", function (e) { if (e.target && e.target.tagName === "LINK") look(); }, true);
    document.addEventListener("DOMContentLoaded", look);
    window.addEventListener("load", function () { loaded = true; look(); });
    look();
  })(); } catch (e) { try { document.documentElement.setAttribute("data-faces", "1"); } catch (x) {} }

  // LIVE14B-001: a saved sign-in's account (/me) asked for the moment /config.js says where the server is, before the page's stylesheet
  // and its code have arrived: the first signed-in page of a browser asked for it only once a file of the app's code had come (lib/
  // accountEarly.ts), behind the stylesheet and ~40 other files (the page drew its heading at 7.9 s live). The app's first /me takes this
  // answer when its token is the same (lib/api.ts), as it took accountEarly's; a token near its end is left to the sign-in library.
  function earlyMe(cfg) {
    try {
      if (!cfg || !cfg.API_BASE || !cfg.SUPABASE_URL || window.__stratlabEarlyMe || typeof fetch !== "function") return;
      var host = "localhost";
      try { host = new URL(String(cfg.SUPABASE_URL).replace(/\/?$/, "/")).hostname; } catch (x) {}
      var saved = JSON.parse(localStorage.getItem("sb-" + host.split(".")[0] + "-auth-token") || "null");
      var token = saved && saved.access_token, ends = Number((saved && saved.expires_at) || 0) * 1000;
      if (!token || !ends || ends < Date.now() + 60000) return;
      var headers = { "Content-Type": "application/json", Authorization: "Bearer " + token };
      var as = String(localStorage.getItem("stratlab.viewas.v1") || "").trim().toLowerCase();
      if (as === "free" || as === "basic" || as === "pro") headers["X-View-As"] = as;
      var got = fetch(cfg.API_BASE + "/me", { headers: headers });
      got.catch(function () {});
      window.__stratlabEarlyMe = { token: token, at: Date.now(), got: got };
      // site81 (LIVE18B-002): the page's own first reads too, with the same token, beside /me: the app asked them only once its code and the
      // page's had come (Trade's India VIX tile asked /trade/vix at 9.5 s live and filled at 10.1 s). lib/api.ts takes each once, same token.
      var path = location.pathname.replace(/(.)\/$/, "$1"), want = [];
      if (/^\/(?:mine|all|home|trade|invest|money|notebooks|new|n|import|options|paper|tour|account|settings|assistant|app|news|holdings|tax-report|alerts|research|scans|watchlist|calendar)(?:\/|$)/.test(path))
        want.push("/notebooks", "/markets");
      if (path === "/trade") want.push("/trade/vix?brief=true", "/trade/positioning?brief=true&pcr=false");
      var reads = window.__stratlabEarlyReads = window.__stratlabEarlyReads || {};
      for (var i = 0; i < want.length; i++) {
        if (reads[want[i]]) continue;
        var r = fetch(cfg.API_BASE + want[i], { headers: headers });
        r.catch(function () {});
        reads[want[i]] = { token: token, at: Date.now(), got: r };
      }
    } catch (x) { /* no saved sign-in to read */ }
  }
  // site81: whether Indian data is live, for a saved sign-in, asked as /config.js runs (it needs no token, so an expired one, the first visit of
  // the day, asks it too): the app holds "Opening StratLab" until it answers (at most 1.5 s), and its own ask went out only once ~40 of the
  // app's files had come (3.2 s on a throttled link). lib/http.ts takes it once.
  function earlyPublic(cfg) {
    try {
      if (!cfg || !cfg.API_BASE || typeof fetch !== "function" || !document.documentElement.hasAttribute("data-saved")) return;
      var pub = window.__stratlabEarlyPublic = window.__stratlabEarlyPublic || {};
      if (pub["/public/data-online"]) return;
      var got = fetch(cfg.API_BASE + "/public/data-online", { headers: { Accept: "application/json" } });
      got.catch(function () {});
      pub["/public/data-online"] = { at: Date.now(), got: got };
      // and the sign-in service's connection opened now: a saved sign-in past its end is renewed there once the app's code has come (the
      // first visit of a day: 8.6-9.9 s live), and that request then doesn't wait for a new connection as well
      if (cfg.SUPABASE_URL && document.head) {
        var l = document.createElement("link");
        l.rel = "preconnect"; l.href = new URL(String(cfg.SUPABASE_URL)).origin; l.crossOrigin = "anonymous";
        document.head.appendChild(l);
      }
    } catch (x) { /* no saved sign-in to read */ }
  }
  try {
    var cfgNow = window.STRATLAB_CONFIG;
    Object.defineProperty(window, "STRATLAB_CONFIG", { configurable: true, enumerable: true,
      get: function () { return cfgNow; }, set: function (v) { cfgNow = v; earlyMe(v); earlyPublic(v); } });
  } catch (e) {}

  // the saved light or dark choice, here as well as in theme.js: if that file fails to load the page still draws in the right theme
  try { var saved = localStorage.getItem("stratlab-theme"); if (saved) document.documentElement.dataset.theme = saved; } catch (e) { /* storage off */ }

  // the browser's offer to install StratLab comes once, soon after the page loads, and the file that uses it (src/lib/pwa.ts)
  // arrives later: keep the offer here so the install button can still appear
  window.addEventListener("beforeinstallprompt", function (e) { if (e.preventDefault) e.preventDefault(); window.__stratlabInstall = e; });
  window.addEventListener("appinstalled", function () { window.__stratlabInstall = null; });

  // the host keeps every /assets/ answer for a year, a 404 too (a deploy switching over): the file that failed is asked for past the
  // browser's cache before the reload, so the reload gets the file and not the kept 404 (R43.1 smoke: "Couldn't load StratLab" stayed)
  function refetch(url) {
    if (typeof fetch !== "function") return null;                 // no way to ask past the cache: reload as before
    try { return fetch(url, { cache: "reload", credentials: "same-origin" }).then(function () {}, function () {}); }
    catch (x) { return null; }
  }
  window.__stratlabRefetch = refetch;
  window.__stratlabRecover = recover;
  window.__stratlabShowLoadError = show;

  // a lazily loaded page (Vite raises this when its file or one it needs fails to download). Cancelled so the import arrives
  // empty: the page's loader (src/lib/lazyRetry.ts) asks again, a little later, up to three times, and only then calls
  // recover (one guarded reload per minute). An import with no loader of its own fails on the empty module and the
  // start-up catch calls recover.
  window.addEventListener("vite:preloadError", function (e) {
    if (e && e.preventDefault) e.preventDefault();
    window.__stratlabLoadFailed = true;
  });
  // the app's own file failed to download as a rejected import(): Safari's "Importing a module script failed" / "Load failed"
  // never reached the two handlers above (R9P-008). Only while the page is still the start-up text: once the app has drawn,
  // a failed request is its own to report
  window.addEventListener("unhandledrejection", function (e) {
    var r = e && e.reason, m = String((r && (r.message || r.name)) || r || "");
    if (!/dynamically imported module|importing a module script|loading chunk|chunkloaderror|load failed|failed to fetch/i.test(m)) return;
    var root = document.getElementById("root");
    if (root && root.querySelector("[data-boot]")) { window.__stratlabLoadFailed = true; recover(); }
  });
  // one of the app's own scripts or stylesheets (the error does not bubble, so listen on the way down)
  window.addEventListener("error", function (e) {
    var t = e && e.target;
    if (!t || t === window || !t.tagName) return;
    var url = String(t.src || t.href || "");
    // config.js too: without it the app can send no request (R68-004: its 502 showed "StratLab ran into a problem")
    if ((/\/assets\//.test(url) || /\/config\.js(\?|$)/.test(url)) && (t.tagName === "SCRIPT" || t.tagName === "LINK")) {
      var asked = refetch(url);
      if (asked) asked.then(recover); else recover();
    }
  }, true);

  // the built stylesheet downloaded but did not apply (src/styles.css sets --css-ok on :root): the app would show as plain,
  // unstyled text, so say so with the reload button instead. Only where the page links a built stylesheet.
  window.addEventListener("load", function () {
    try {
      if (!document.querySelector('link[rel="stylesheet"][href*="/assets/"]')) return;
      if (getComputedStyle(document.documentElement).getPropertyValue("--css-ok").trim() !== "1") show(true);
    } catch (e) { /* nothing to check */ }
  });

  // the page is still the plain start-up text after a long wait
  setTimeout(function () {
    var root = document.getElementById("root");
    if (root && root.querySelector("[data-boot]")) show(false, true);
  }, SLOW);
  // still nothing at twice that: the plain "couldn't load" card in its place
  setTimeout(function () {
    var root = document.getElementById("root");
    if (root && root.querySelector("[data-boot], [data-slow]")) show();
  }, SLOW * 2);
})();
