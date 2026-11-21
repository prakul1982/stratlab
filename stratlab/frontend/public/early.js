/* site81: a saved sign-in's first reads, asked as soon as /config.js says where the server is, not once the app's ~40 files have come.
 * Loaded by public/boot.js for a saved sign-in only (a visitor's download is unchanged).
 * - LIVE18B-002: the page's own first reads with the saved token, beside boot.js's /me: /notebooks and /markets on an app page, Trade's
 *   strip on /trade (its India VIX tile asked /trade/vix at 9.5 s live). lib/api.ts takes each once, with the same token.
 * - LIVE18A-011: whether Indian data is live (/public/data-online needs no token, so an expired sign-in, the first visit of a day, asks it
 *   too): the app holds "Opening StratLab" until it answers (at most 1.5 s), and its own ask went out only behind the app's files (3.2 s on
 *   a throttled link). lib/api.ts takes it once. And the sign-in service's connection, opened now for the renewal the app makes later. */
(function () {
  var w = window, d = document;
  function go(cfg) {
    try {
      // LIVE19B-003: the app's code already running (this file came late, a cold launch) asks its own reads: asking them here too sent each twice
      if (!cfg || !cfg.API_BASE || typeof fetch !== "function" || w.__stratlabEarlyPublic || w.__stratlabApp) return;
      var pub = fetch(cfg.API_BASE + "/public/data-online", { headers: { Accept: "application/json" } });
      pub.catch(function () {});
      w.__stratlabEarlyPublic = { "/public/data-online": { at: Date.now(), got: pub } };
      if (cfg.SUPABASE_URL && d.head) {
        var l = d.createElement("link");
        l.rel = "preconnect"; l.href = new URL(String(cfg.SUPABASE_URL)).origin; l.crossOrigin = "anonymous";
        d.head.appendChild(l);
      }
      var host = new URL(String(cfg.SUPABASE_URL).replace(/\/?$/, "/")).hostname;
      var saved = JSON.parse(localStorage.getItem("sb-" + host.split(".")[0] + "-auth-token") || "null");
      var token = saved && saved.access_token, ends = Number((saved && saved.expires_at) || 0) * 1000;
      if (!token || !ends || ends < Date.now() + 60000) return;           // a token near its end: the sign-in library renews it first
      var headers = { "Content-Type": "application/json", Authorization: "Bearer " + token };
      var as = String(localStorage.getItem("stratlab.viewas.v1") || "").trim().toLowerCase();
      if (as === "free" || as === "basic" || as === "pro") headers["X-View-As"] = as;
      var path = location.pathname.replace(/(.)\/$/, "$1"), want = [];
      if (/^\/(?:mine|all|home|trade|invest|money|notebooks|new|n|import|options|paper|tour|account|settings|assistant|app|news|holdings|tax-report|alerts|research|scans|watchlist|calendar)(?:\/|$)/.test(path))
        want.push("/notebooks", "/markets");
      if (path === "/trade") want.push("/trade/vix?brief=true", "/trade/positioning?brief=true&pcr=false");
      var reads = w.__stratlabEarlyReads = w.__stratlabEarlyReads || {};
      for (var i = 0; i < want.length; i++) {
        if (reads[want[i]]) continue;
        var r = fetch(cfg.API_BASE + want[i], { headers: headers });
        r.catch(function () {});
        reads[want[i]] = { token: token, at: Date.now(), got: r };
      }
    } catch (x) { /* nothing saved to read */ }
  }
  // /config.js has usually run by now; if not, boot.js's config hook calls this when it does
  if (w.STRATLAB_CONFIG) go(w.STRATLAB_CONFIG); else w.__stratlabEarlyGo = go;
})();

/* LIVE21B-001: a saved sign-in on an app page sees the app's own frame, never the landing's. The page's HTML is the home page's (vercel.json):
 * its first frame was the landing's header with "Sign in" and the landing's heading, for ~2.9 s live. index.html hides them for a saved
 * sign-in (boot.js marks it); here they are taken out as the parser adds them and the app's frame is drawn instead, from the app's
 * stylesheet: the menu's panel and the phone's top bar with the logo, "Opening StratLab…" where the app's "Opening the page" comes next. The
 * same frame as components/BootFrame.tsx (unit/site85 keeps them equal). In this file, which only a saved sign-in downloads, so a visitor's
 * pages weigh what they did (review-r5's budgets). The pages anyone sees the same way (lib/entry.ts PUBLIC_FOR_ALL) keep their own words. */
(function () {
  var FOR_ALL = [/^\/(about|terms|privacy|refunds|contact)\/?$/, /^\/verdict\/[^/]+\/?$/, /^\/library\/[^/]+\/?$/];
  try {
    if (FOR_ALL.some(function (re) { return re.test(location.pathname); })) { document.documentElement.setAttribute("data-for-all", "1"); return; }
  } catch (e) { return; }
  function appFrame() {
    var root = document.getElementById("root");
    if (!root || Object.keys(root).some(function (k) { return k.indexOf("__reactContainer") === 0; })) return;      // the app draws now
    var logo = null, shell = null;
    for (var n = root.firstElementChild; n;) {
      var next = n.nextElementSibling;
      if (n.hasAttribute("data-boot-shell")) shell = n;
      else if (!n.querySelector(".boot-now")) { if (!logo) logo = n.querySelector(".logo"); root.removeChild(n); }
      n = next;
    }
    if (!shell) {
      shell = document.createElement("div");
      shell.className = "shell boot-shell";
      shell.setAttribute("data-boot-shell", "");
      shell.setAttribute("data-boot", "");          // the start-up guard (boot.js) reads it as the start-up frame
      var box = '<span class="icon-btn" aria-hidden="true"></span>';
      // the app's Shell: the menu's panel, the phone's top bar (its buttons' places held), the page column with one heading
      shell.innerHTML = '<header class="topbar" aria-hidden="true">' + box + '<span class="brand" data-boot-logo></span><span class="row tight">' + box + box + box + '</span></header>'
        + '<aside class="sidebar" aria-hidden="true"><div class="side-top"><div class="side-brand"><span class="brand" data-boot-logo></span></div></div></aside>'
        + '<main class="main" id="main"><div class="page"><h1 class="sr-only">Opening StratLab</h1><div class="k-loading" role="status"><span class="spinner"></span>Opening StratLab…</div></div></main>';
      root.insertBefore(shell, root.firstChild);
    }
    var slots = shell.querySelectorAll("[data-boot-logo]:empty");
    for (var i = 0; i < slots.length; i++) {
      if (logo) {
        var c = logo.cloneNode(true); c.className = "logo logo-40";
        var m = c.querySelector("svg"); if (m) { m.setAttribute("width", "16"); m.setAttribute("height", "40"); }
        // each copy's gradients named its own: the first copy's (the phone's top bar) is not drawn on a laptop, and a fill naming it was empty
        var ids = c.querySelectorAll("[id]");
        for (var j = 0; j < ids.length; j++) {
          var was = ids[j].id, now = was + "-" + i;
          ids[j].id = now;
          var refs = c.querySelectorAll('[fill="url(#' + was + ')"]');
          for (var q = 0; q < refs.length; q++) refs[q].setAttribute("fill", "url(#" + now + ")");
        }
        slots[i].appendChild(c);
      }
      else if (document.readyState !== "loading") slots[i].innerHTML = '<span class="logo logo-40"><img src="/favicon.svg" alt="" width="28" height="28"><span class="logo-word"><b>Strat</b>Lab</span></span>';
    }
  }
  try {
    appFrame();
    if (document.readyState === "loading") {
      var parsed = new MutationObserver(appFrame);
      parsed.observe(document.documentElement, { childList: true, subtree: true });
      // the whole page parsed (before the app's code runs): once more, and the observer goes
      document.addEventListener("readystatechange", function () { if (document.readyState === "loading") return; parsed.disconnect(); appFrame(); });
    }
  } catch (e) { /* no observer: index.html keeps the landing's frame hidden */ }
})();
