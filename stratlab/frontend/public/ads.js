/* Ads on the pages the server draws (the company pages, later the blog): asks the visitor first, loads Google's ad script only
 * after "Allow ads", and fills each labelled box on the page (backend/app/ads.py writes the boxes, with their IDs, only when ads
 * are switched on). A plain file, not part of the app bundle, so these pages need no app code. The app's own slot
 * (src/components/AdUnit.tsx) reads and writes the same answer under the same key, so one choice covers the whole site;
 * unit/ads.test.mjs checks that the two stay in step. Nothing here runs unless the page has a box. */
(function () {
  if (window.__stratlabAds) return;                 // the script tag may be on a page twice; the boxes are filled once
  window.__stratlabAds = true;

  var KEY = "stratlab.ads";                          // {"c":"yes"|"no","at":<ms>}; the same as src/lib/ads.ts
  var DAYS = 365;                                    // asked again after a year
  var memory = null;                                 // the answer for this page view when storage is off

  function parse(raw) {
    try {
      var j = JSON.parse(raw);
      if ((j.c === "yes" || j.c === "no") && typeof j.at === "number" && Date.now() - j.at < DAYS * 864e5) return j.c;
    } catch (e) { /* not ours */ }
    return null;
  }
  function read() {
    try { var raw = localStorage.getItem(KEY); if (raw) return parse(raw); } catch (e) { /* storage off */ }
    return memory;
  }
  function write(c) {
    memory = c;
    try { localStorage.setItem(KEY, JSON.stringify({ c: c, at: Date.now() })); } catch (e) { /* storage off: this page view only */ }
  }
  // Google's own consent message (AdSense, Privacy & messaging) is on the page: it asks EEA and UK visitors, so ours steps aside
  function googleMessage() {
    try { return !!window.googlefc || !!document.querySelector('iframe[name="googlefcPresent"]'); } catch (e) { return false; }
  }

  var boxes = [];
  var loaded = false;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text) n.textContent = text;
    return n;
  }
  function drop(box) { if (box.parentNode) box.parentNode.removeChild(box); }

  function fill(box) {
    var area = box.querySelector(".ad-box");
    if (!area || area.querySelector("ins")) return;
    area.textContent = "";
    var ins = el("ins", "adsbygoogle");
    ins.style.display = "block";
    ins.setAttribute("data-ad-client", box.getAttribute("data-client"));
    ins.setAttribute("data-ad-slot", box.getAttribute("data-slot"));
    ins.setAttribute("data-ad-format", "auto");
    ins.setAttribute("data-full-width-responsive", "true");
    area.appendChild(ins);
    // an ad Google had none to fill: the box and its label go, so no empty "Advertisement" is left on the page
    try {
      new MutationObserver(function () { if (ins.getAttribute("data-ad-status") === "unfilled") drop(box); })
        .observe(ins, { attributes: true, attributeFilter: ["data-ad-status"] });
    } catch (e) { /* an old browser keeps the empty box */ }
    try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) { /* the script is blocked: the box stays empty */ }
  }

  // Google's script comes only after "Allow", and only when the first box is about to be seen (nothing below the fold loads early)
  function load() {
    if (loaded) return;
    loaded = true;
    var s = el("script");
    s.async = true;
    s.crossOrigin = "anonymous";
    s.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" + encodeURIComponent(boxes[0].getAttribute("data-client"));
    document.head.appendChild(s);
    boxes.forEach(fill);
  }
  function whenNear(go) {
    if (typeof IntersectionObserver !== "function") return go();
    var seen = false;
    var io = new IntersectionObserver(function (es) {
      if (seen || !es.some(function (e) { return e.isIntersecting; })) return;
      seen = true; io.disconnect(); go();
    }, { rootMargin: "300px 0px" });
    boxes.forEach(function (b) { io.observe(b); });
  }

  function ask(box) {
    var area = box.querySelector(".ad-box");
    if (!area) return;
    area.textContent = "";
    // the 280px held for an ad is for the ad: the question is short, and sat in the top of a mostly empty box (VR4-015). The box takes
    // its height back with "Allow", where the page below moving follows the person's own click
    area.style.minHeight = "0";
    var label = box.querySelector(".ad-label");
    if (label) label.textContent = "Ads on StratLab";        // the question is not an ad, so it is not labelled as one
    box.setAttribute("aria-label", "Ads on StratLab");
    var card = el("div", "ad-ask");
    card.setAttribute("role", "group");
    card.setAttribute("aria-label", "Ads on StratLab");
    card.appendChild(el("p", "", "StratLab shows Google ads on public pages. They use cookies to choose and measure ads. Say no and no ad is loaded. Basic and Pro have no ads."));
    var row = el("div", "ad-btns");
    var yes = el("button", "ad-yes", "Allow ads");
    var no = el("button", "ad-no", "No thanks");
    yes.type = "button"; no.type = "button";
    yes.addEventListener("click", function () { write("yes"); area.style.minHeight = ""; if (label) label.textContent = "Advertisement"; box.setAttribute("aria-label", "Advertisement"); load(); });
    no.addEventListener("click", function () { write("no"); boxes.forEach(drop); });
    row.appendChild(yes); row.appendChild(no);
    card.appendChild(row);
    area.appendChild(card);
  }

  function start() {
    boxes = Array.prototype.slice.call(document.querySelectorAll("[data-ads]"));
    if (!boxes.length) return;
    var choice = read();
    if (choice === "no") { boxes.forEach(drop); return; }
    if (choice === "yes" || googleMessage()) { whenNear(load); return; }
    ask(boxes[0]);                                   // one question per page; any other box waits for the answer
    boxes.slice(1).forEach(drop);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
