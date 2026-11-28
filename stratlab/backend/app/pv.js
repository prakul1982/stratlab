/* One pageview for a page the server draws (company, theme, blog, directory and status pages), sent to PostHog through the site's own
 * address (/ingest, which vercel.json and the Caddyfile forward to PostHog), with no analytics library (conv101, T1). The page's script tag
 * carries the public project key (data-k) and what kind of page it is (data-kind).
 *
 * The same rules as the app's analytics (frontend src/lib/analyticsGate.ts, which unit/pv.test.mjs keeps in step): nothing is sent when the
 * browser asks not to be tracked (Do Not Track or Global Privacy Control), for an automated or headless browser, or on a device marked as
 * StratLab's own (localStorage stratlab.internal, set by opening any page with ?internal=1; ?internal=0 clears it). The address is sent
 * without its query or hash, another site's referrer as its origin only, and the visitor is the same random anonymous ID the app's
 * analytics keeps (the ph_<key>_posthog entry the Privacy page names), so a visit that goes on into the app is one visitor. */
(function () {
  "use strict";
  var me = document.currentScript;
  if (!me || window.__stratlabPv) return;
  window.__stratlabPv = true;
  var key = me.getAttribute("data-k") || "";
  var kind = me.getAttribute("data-kind") || "site";
  var INTERNAL = "stratlab.internal";

  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function put(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* storage off */ } }

  // ?internal=1 / ?internal=0: this device is (no longer) StratLab's own, said on the page for a few seconds
  var sw = /[?&]internal=([01])(?:&|$)/.exec(location.search);
  if (sw) {
    put(INTERNAL, sw[1] === "1" ? "1" : null);
    var note = document.createElement("div");
    note.setAttribute("role", "status");
    note.setAttribute("data-internal-note", sw[1]);
    note.textContent = sw[1] === "1" ? "This device is now left out of StratLab's analytics." : "This device is counted in StratLab's analytics again.";
    note.style.cssText = "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:9999;background:#1D1B17;color:#F5F1E8;padding:10px 16px;border-radius:10px;font:14px/1.4 system-ui,sans-serif;max-width:calc(100vw - 32px)";
    (document.body || document.documentElement).appendChild(note);
    setTimeout(function () { if (note.parentNode) note.parentNode.removeChild(note); }, 6000);
  }

  var n = navigator, ua = n.userAgent || "";
  var dnt = [n.doNotTrack, n.msDoNotTrack, window.doNotTrack].some(function (v) { return v === "1" || v === "yes"; }) || n.globalPrivacyControl === true;
  var AUTOMATED = /HeadlessChrome|PhantomJS|Puppeteer|Playwright|Selenium|Cypress|Lighthouse|PTST|GTmetrix|PageSpeed|bot[\/;)-]|crawler|spider|slurp|facebookexternalhit/i;
  var robot = n.webdriver === true || AUTOMATED.test(ua) ||
    !!(n.userAgentData && n.userAgentData.brands && n.userAgentData.brands.some(function (b) { return /headless/i.test(b.brand); }));
  if (!key || !/^phc_\w+$/.test(key) || dnt || robot || get(INTERNAL) === "1" || !window.fetch) return;

  function hex(len) {
    var a = new Uint8Array(Math.ceil(len / 2)), s = "";
    (window.crypto || window.msCrypto).getRandomValues(a);
    for (var i = 0; i < a.length; i++) s += ("0" + a[i].toString(16)).slice(-2);
    return s.slice(0, len);
  }
  // a UUIDv7, as PostHog's own library makes its IDs (sessions are read from the time inside them)
  function uuid7() {
    var t = ("000000000000" + Date.now().toString(16)).slice(-12), r = hex(19);
    return t.slice(0, 8) + "-" + t.slice(8, 12) + "-7" + r.slice(0, 3) + "-" + ((parseInt(r.charAt(3), 16) & 3) | 8).toString(16) + r.slice(4, 7) + "-" + r.slice(7, 19);
  }

  // the app's analytics entry: the same anonymous ID and session (30 minutes idle ends one), made here when it isn't there yet
  var store = "ph_" + key + "_posthog", now = Date.now(), ph = {};
  try { ph = JSON.parse(get(store) || "{}") || {}; } catch (e) { ph = {}; }
  if (typeof ph.distinct_id !== "string" || !ph.distinct_id) { ph.distinct_id = uuid7(); ph.$device_id = ph.distinct_id; ph.$user_state = "anonymous"; }
  var ses = Array.isArray(ph.$sesid) ? ph.$sesid : null;
  if (!ses || typeof ses[0] !== "number" || now - ses[0] > 30 * 60000 || now - (ses[2] || 0) > 24 * 3600000) ses = [now, uuid7(), now];
  ses[0] = now;
  ph.$sesid = ses;
  put(store, JSON.stringify(ph));

  var ref = document.referrer || "", refOut = "$direct", refHost = "$direct";
  try {
    if (ref) {
      var u = new URL(ref);
      refOut = u.origin === location.origin ? u.origin + u.pathname : u.origin;
      refHost = u.host;
    }
  } catch (e) { /* not an address */ }
  var os = /Android/.test(ua) ? "Android" : /iPhone|iPad|iPod/.test(ua) ? "iOS" : /Windows/.test(ua) ? "Windows" : /CrOS/.test(ua) ? "Chrome OS"
    : /Mac OS X/.test(ua) ? "Mac OS X" : /Linux/.test(ua) ? "Linux" : "Other";
  var browser = /Edg\//.test(ua) ? "Microsoft Edge" : /OPR\/|Opera/.test(ua) ? "Opera" : /SamsungBrowser/.test(ua) ? "Samsung Internet"
    : /CriOS/.test(ua) ? "Chrome iOS" : /FxiOS|Firefox/.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome"
    : /Safari\//.test(ua) ? (/Mobile/.test(ua) ? "Mobile Safari" : "Safari") : "Other";
  var device = /iPad|Tablet/.test(ua) ? "Tablet" : /Mobi|Android|iPhone|iPod/.test(ua) ? "Mobile" : "Desktop";
  var props = {
    $current_url: location.origin + location.pathname, $pathname: location.pathname, $host: location.host,
    $referrer: refOut, $referring_domain: refHost, $session_id: ses[1], $device_id: ph.$device_id || ph.distinct_id,
    $os: os, $browser: browser, $device_type: device, $screen_width: screen.width, $screen_height: screen.height,
    $lib: "stratlab-pv", $process_person_profile: false, page_kind: kind
  };
  // where an ad or a post sent the visit: the campaign's own plain words only
  var q = new URLSearchParams(location.search);
  ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"].forEach(function (k) {
    var v = q.get(k);
    if (v && /^[\w.+-]{1,60}$/.test(v) && v.indexOf("@") < 0) props[k] = v;
  });
  var body = JSON.stringify({ api_key: key, event: "$pageview", distinct_id: ph.distinct_id, uuid: uuid7(), timestamp: new Date(now).toISOString(), properties: props });
  try {
    fetch("/ingest/i/v0/e/", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" }, body: body, credentials: "omit" })
      .catch(function () { /* blocked or offline: nothing else to do */ });
  } catch (e) { /* an old browser */ }
})();
