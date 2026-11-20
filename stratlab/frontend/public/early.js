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
      if (!cfg || !cfg.API_BASE || typeof fetch !== "function" || w.__stratlabEarlyPublic) return;
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
