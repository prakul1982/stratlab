/* The share-price chart on a company's public page (PUB-1). One small script, no library: the app's own chart look (a 2px line, a
 * 10% tint, a hairline grid, a crosshair) drawn from /stocks/<market>/<symbol>/prices.json, a cached
 * read-only list of daily closes (a week apart before the last year). The page holds the same figures as text, so with no script
 * the chart is simply absent. Daily closes; nothing is predicted, fitted or extended. Served as /stocks/chart.js. */
(function () {
  "use strict";
  var root = document.querySelector("[data-chart]");
  if (!root || !window.fetch) return;
  var NS = "http://www.w3.org/2000/svg", DAY = 864e5;
  var plot = root.querySelector(".plot"), tip = root.querySelector(".tip"), status = root.querySelector("[data-status]");
  var sum = root.querySelector("[data-summary]"), chg = root.querySelector("[data-change]"), note = root.querySelector("[data-change-note]");
  var seg = root.querySelector(".seg"), table = root.querySelector("[data-table]"), live = root.querySelector("[data-live]");
  var adjNote = root.querySelector("[data-adjust]");
  var cur = root.getAttribute("data-currency") || "INR", loc = cur === "INR" ? "en-IN" : "en-US";
  var money = new Intl.NumberFormat(loc, { style: "currency", currency: cur, minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var money4 = new Intl.NumberFormat(loc, { style: "currency", currency: cur, minimumFractionDigits: 4, maximumFractionDigits: 4 });
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var RANGES = { "1m": [31, "1 month"], "6m": [183, "6 months"], "1y": [366, "1 year"], "5y": [1830, "5 years"], all: [1e5, "the time since its first day of trading"] };
  var data = null, range = "1y", state = null, started = false;

  var price = function (v) { return (Math.abs(v) < 0.1 ? money4 : money).format(v); };
  var day = function (n) { return new Date(n * DAY); };
  var dlabel = function (n) { var d = day(n); return d.getUTCDate() + " " + MON[d.getUTCMonth()] + " " + d.getUTCFullYear(); };
  var el = function (name, attrs, parent) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };

  function available(r) {
    var last = data.t[data.t.length - 1];
    return r === "all" || data.t[0] <= last - RANGES[r][0] + 4;
  }
  function slice(r) {
    var t = data.t, n = t.length, from = r === "all" ? t[0] : t[n - 1] - RANGES[r][0], i = 0;
    while (i < n - 2 && t[i] < from) i++;
    return { t: t.slice(i), c: data.c.slice(i) };
  }
  function nice(lo, hi, count) {
    var span = hi - lo || Math.abs(hi) || 1, raw = span / count, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
    var step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p, out = [];
    for (var v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(8));
    return out;
  }
  function tickFormat(ticks) {
    var d = 0;
    while (d < 6 && !ticks.every(function (v) { return Math.abs(v - +v.toFixed(d)) < 1e-9; })) d++;
    return new Intl.NumberFormat(loc, { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function xticks(s, r, max) {
    var out = [], t0 = s.t[0], t1 = s.t[s.t.length - 1], d0 = day(t0);
    if (r === "1m") {
      var step = Math.max(7, Math.ceil((t1 - t0) / max / 7) * 7);
      for (var t = t1; t >= t0 + 1; t -= step) out.unshift({ t: t, text: day(t).getUTCDate() + " " + MON[day(t).getUTCMonth()] });
      return out;
    }
    var yearly = r === "5y" || (r === "all" && t1 - t0 > 900), months = Math.ceil((t1 - t0) / 30.4 / max);
    months = yearly ? Math.max(12, Math.ceil(months / 12) * 12) : ([1, 2, 3, 4, 6, 12].filter(function (m) { return m >= months; })[0] || 12);
    var d = new Date(Date.UTC(d0.getUTCFullYear(), yearly ? 0 : d0.getUTCMonth(), 1));
    for (; d.getTime() / DAY <= t1; d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + months, 1))) {
      var tt = d.getTime() / DAY, m = d.getUTCMonth();
      if (tt < t0 + 3) continue;
      out.push({ t: tt, text: yearly ? String(d.getUTCFullYear()) : (m === 0 || !out.length ? MON[m] + " " + d.getUTCFullYear() : MON[m]) });
    }
    return out;
  }

  function stats(s) {
    var n = s.c.length, hi = 0, lo = 0;
    for (var i = 1; i < n; i++) { if (s.c[i] > s.c[hi]) hi = i; if (s.c[i] < s.c[lo]) lo = i; }
    return { n: n, hi: hi, lo: lo, pct: (s.c[n - 1] / s.c[0] - 1) * 100 };
  }
  function extremes(s) {
    var k = stats(s);
    return "Highest close " + price(s.c[k.hi]) + " on " + dlabel(s.t[k.hi]) + "; lowest close " + price(s.c[k.lo]) + " on " + dlabel(s.t[k.lo]) + ".";
  }
  function words(s) {
    var n = s.c.length;
    return "The close was " + price(s.c[0]) + " on " + dlabel(s.t[0]) + " and " + price(s.c[n - 1]) + " on " + dlabel(s.t[n - 1]) + ". " + extremes(s);
  }

  /* a close as words, for a screen reader */
  function reading(s, i) { return WD[day(s.t[i]).getUTCDay()] + " " + dlabel(s.t[i]) + ": " + price(s.c[i]); }

  function draw() {
    var r = range, s = slice(r), n = s.c.length;
    if (n < 2) return;
    var W = Math.max(260, Math.round(plot.clientWidth)), H = W < 560 ? 210 : 280, padT = 10, padB = 26;
    var lo = Math.min.apply(null, s.c), hi = Math.max.apply(null, s.c), pad = (hi - lo) * 0.06 || hi * 0.02 || 1;
    var ticks = nice(lo - pad, hi + pad, W < 560 ? 4 : 5), ylo = Math.min(lo - pad, ticks[0]), yhi = Math.max(hi + pad, ticks[ticks.length - 1]);
    var nf = tickFormat(ticks), fmt = function (v) { return nf.format(v); };
    var padL = Math.max.apply(null, ticks.map(function (v) { return fmt(v).length; })) * 7 + 12, padR = 12;
    var x0 = s.t[0], x1 = s.t[n - 1];
    var sx = function (t) { return padL + (t - x0) / (x1 - x0 || 1) * (W - padL - padR); };
    var sy = function (v) { return padT + (yhi - v) / (yhi - ylo || 1) * (H - padT - padB); };
    plot.style.height = H + "px";
    var old = plot.querySelector("svg");
    if (old) plot.removeChild(old);
    // a slider over the closes: on an image a screen reader keeps the arrow keys, on a slider it hands them over and says each value (A11Y-2)
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "slider", tabindex: "0",
      "aria-valuemin": 1, "aria-valuemax": n, "aria-valuenow": n, "aria-valuetext": reading(s, n - 1),
      "aria-label": "Share price over " + RANGES[r][1] + ". " + words(s) + " Use the left and right arrow keys to read each close." });
    svg.style.touchAction = "pan-y";
    ticks.forEach(function (v) {
      el("line", { x1: padL, x2: W - padR, y1: sy(v), y2: sy(v), stroke: "var(--line)", "stroke-width": 1, "shape-rendering": "crispEdges" }, svg);
      el("text", { x: padL - 8, y: sy(v) + 4, "text-anchor": "end", fill: "var(--muted)", "font-size": 12 }, svg).textContent = fmt(v);
    });
    xticks(s, r, Math.max(2, Math.floor((W - padL) / 76))).forEach(function (k) {
      el("text", { x: sx(k.t), y: H - 7, "text-anchor": "middle", fill: "var(--muted)", "font-size": 12 }, svg).textContent = k.text;
    });
    var d = "";
    for (var i = 0; i < n; i++) d += (i ? "L" : "M") + sx(s.t[i]).toFixed(1) + "," + sy(s.c[i]).toFixed(1);
    el("path", { d: d + "L" + sx(x1).toFixed(1) + "," + (H - padB) + "L" + sx(x0).toFixed(1) + "," + (H - padB) + "Z", fill: "var(--blue)", opacity: 0.1 }, svg);
    el("path", { d: d, fill: "none", stroke: "var(--blue)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    var end = el("circle", { cx: sx(x1), cy: sy(s.c[n - 1]), r: 4, fill: "var(--blue)", stroke: "var(--card)", "stroke-width": 2 }, svg);
    var cross = el("g", { visibility: "hidden", "pointer-events": "none" }, svg);
    var vline = el("line", { y1: padT, y2: H - padB, stroke: "var(--ink)", "stroke-width": 1, opacity: 0.35 }, cross);
    var dot = el("circle", { r: 4.5, fill: "var(--blue)", stroke: "var(--card)", "stroke-width": 2 }, cross);
    plot.insertBefore(svg, tip);
    state = { at: -1 };

    function at(i) {
      i = Math.max(0, Math.min(n - 1, i));
      state.at = i;
      var x = sx(s.t[i]), y = sy(s.c[i]);
      vline.setAttribute("x1", x); vline.setAttribute("x2", x);
      dot.setAttribute("cx", x); dot.setAttribute("cy", y);
      cross.setAttribute("visibility", "visible");
      end.setAttribute("visibility", i === n - 1 ? "visible" : "hidden");
      var a = document.createElement("span"), b = document.createElement("b");
      a.textContent = WD[day(s.t[i]).getUTCDay()] + " " + dlabel(s.t[i]); b.textContent = price(s.c[i]);
      tip.textContent = "";
      tip.appendChild(a); tip.appendChild(b);
      tip.hidden = false;
      var w = tip.offsetWidth, left = Math.min(Math.max(x - w / 2, 0), W - w);
      tip.style.left = left + "px";
      tip.style.top = Math.max(0, Math.min(y - 60, H - padB - 46)) + "px";
      say(i);
    }
    function say(i) { svg.setAttribute("aria-valuenow", i + 1); svg.setAttribute("aria-valuetext", reading(s, i)); }
    function off() { cross.setAttribute("visibility", "hidden"); end.setAttribute("visibility", "visible"); tip.hidden = true; state.at = -1; say(n - 1); }
    function nearest(ev) {
      var rect = svg.getBoundingClientRect(), px = (ev.clientX - rect.left) * (W / rect.width), a = 0, b = n - 1;
      while (a < b) { var m = (a + b) >> 1; if (sx(s.t[m]) < px) a = m + 1; else b = m; }
      return a > 0 && Math.abs(sx(s.t[a - 1]) - px) <= Math.abs(sx(s.t[a]) - px) ? a - 1 : a;
    }
    svg.addEventListener("pointermove", function (ev) { at(nearest(ev)); });
    svg.addEventListener("pointerdown", function (ev) { at(nearest(ev)); });
    svg.addEventListener("pointerleave", function (ev) { if (ev.pointerType === "mouse") off(); });
    svg.addEventListener("blur", off);
    svg.addEventListener("keydown", function (ev) {
      var i = state.at < 0 ? n - 1 : state.at, k = ev.key;
      if (k === "ArrowLeft") i -= ev.shiftKey ? 10 : 1;
      else if (k === "ArrowRight") i += ev.shiftKey ? 10 : 1;
      else if (k === "Home") i = 0;
      else if (k === "End") i = n - 1;
      else if (k === "Escape") { off(); return; }
      else return;
      ev.preventDefault(); at(i);
    });
  }

  function adjustNote(s) {
    if (!adjNote) return;
    var from = s.t[0], to = s.t[s.t.length - 1], bits = [];
    (data.adj || []).forEach(function (a) {
      var t = Date.parse(a.d) / DAY;
      if (t > from && t <= to) bits.push(a.k === "demerger" ? dlabel(t) + ": a demerger. Closes aren't adjusted for it, so the line steps by the value moved to the new company."
        : "Closes before " + dlabel(t) + " are adjusted for the " + (a.t || a.k) + ": no jump, but not the prices traded then.");
    });
    adjNote.textContent = bits.join(" ");
    adjNote.hidden = !bits.length;
  }

  // what the last close moved on its day, beside the price at the top of the page: the last two closes of the series, only when the series
  // ends on the day and at the price the page shows (a page older than its series, or a price from another source, shows no move)
  function dayChange() {
    var out = document.querySelector("[data-day]"), n = data.t.length;
    if (!out || n < 2) return;
    var last = data.c[n - 1], prev = data.c[n - 2], shown = parseFloat(root.getAttribute("data-price")), at = Date.parse(root.getAttribute("data-price-at")) / DAY;
    if (!(shown > 0) || data.t[n - 1] !== at || data.t[n - 1] - data.t[n - 2] > 5 || Math.abs(last - shown) > shown * 0.005 || !(prev > 0)) return;
    var d = last - prev, pct = d / prev * 100, flat = Math.abs(pct) < 0.005, sign = flat ? "" : d > 0 ? "+" : "\u2212";
    var sym = cur === "INR" ? "\u20B9" : "$", mag = Math.abs(d);
    var amt = sym + new Intl.NumberFormat(loc, { minimumFractionDigits: 2, maximumFractionDigits: mag < 0.1 ? 4 : 2 }).format(mag);
    out.textContent = flat ? "Unchanged on the day" : sign + amt + " (" + sign + Math.abs(pct).toFixed(2) + "%)";
    out.setAttribute("data-dir", flat ? "flat" : d > 0 ? "up" : "down");
    out.setAttribute("aria-label", (flat ? "Unchanged" : d > 0 ? "Up " : "Down ") + (flat ? "" : amt + ", " + Math.abs(pct).toFixed(2) + "%") + " on the day");
    out.hidden = false;
  }

  function show() {
    var s = slice(range), k = stats(s), n = k.n, up = k.pct >= 0.05, down = k.pct <= -0.05;
    status.hidden = true;
    chg.textContent = up ? "Up " + k.pct.toFixed(1) + "%" : down ? "Down " + Math.abs(k.pct).toFixed(1) + "%" : "Unchanged";
    chg.setAttribute("data-dir", up ? "up" : down ? "down" : "flat");
    note.textContent = " over " + RANGES[range][1] + ", " + price(s.c[0]) + " to " + price(s.c[n - 1]) + ". Price change only; dividends are not included.";
    sum.textContent = extremes(s) + " Closing prices.";
    adjustNote(s);
    Array.prototype.forEach.call(seg.querySelectorAll("button"), function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-r") === range)); });
    draw();
    var rows = Math.min(n, 24), body = "";
    for (var j = 0; j < rows; j++) {
      var i = Math.round(j * (n - 1) / (rows - 1));
      body += "<tr><td>" + dlabel(s.t[i]) + "</td><td>" + price(s.c[i]) + "</td></tr>";
    }
    table.querySelector("tbody").innerHTML = body;
    table.querySelector("[data-rows]").textContent = n > rows ? rows + " of the " + n + " closes in this range, evenly spaced." : "All " + n + " closes in this range.";
  }

  function load() {
    if (started) return;
    started = true;
    status.hidden = false;
    status.textContent = "Loading prices…";
    fetch(root.getAttribute("data-src"), { headers: { Accept: "application/json" } }).then(function (r) {
      if (r.status === 404) throw new Error("none");
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    }).then(function (j) {
      if (!j || !j.t || j.t.length < 2) throw new Error("none");
      data = j;
      dayChange();
      Array.prototype.forEach.call(seg.querySelectorAll("button"), function (b) {
        var ok = available(b.getAttribute("data-r"));
        b.disabled = !ok;
        b.title = ok ? "" : "Not enough history yet";
      });
      var all = seg.querySelector('[data-r="all"]');
      if (all) all.hidden = available("1y");
      range = available("1y") ? "1y" : "all";
      root.setAttribute("data-ready", "1");
      seg.hidden = false;
      show();
    }).catch(function (err) {
      var none = err.message === "none";
      started = none;
      status.hidden = false;
      status.textContent = none ? "No price chart is available for this company yet. The figures here are unaffected." : "The price chart couldn't be loaded just now. The figures on this page are unaffected. ";
      if (none) return;
      var b = document.createElement("button");
      b.type = "button"; b.className = "btn ghost"; b.textContent = "Try again";
      b.addEventListener("click", load);
      status.appendChild(b);
    });
  }

  seg.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("button[data-r]");
    if (!b || b.disabled || !data) return;
    range = b.getAttribute("data-r");
    show();
    // the buttons say which is pressed; what the range shows is said here, once (A11Y-2)
    if (live) live.textContent = chg.textContent + note.textContent;
  });
  var timer = 0;
  window.addEventListener("resize", function () { clearTimeout(timer); timer = setTimeout(function () { if (data) draw(); }, 120); });
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (e) { if (e[0].isIntersecting) { io.disconnect(); load(); } }, { rootMargin: "300px 0px" });
    io.observe(root);
  } else load();
})();
