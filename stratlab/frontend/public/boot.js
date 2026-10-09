/* Starts before the app and watches it load. If a file the page needs fails to download (a dropped connection, a deploy
 * that replaced the old files), the page reloads once on its own; if that does not help, it says so and offers a Reload
 * button, instead of staying blank. A plain file, not part of the app bundle, so it works when the bundle does not. */
(function () {
  var KEY = "stratlab.reloaded";
  var WAIT = 60 * 1000;          // a second failure within this time shows the message instead of reloading again
  var SLOW = 20 * 1000;          // the app has not drawn anything after this long

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

  function show() {
    var root = document.getElementById("root");
    if (!root || !root.querySelector("[data-boot], .boot")) return;       // once the app has drawn, its own error screen does this
    root.textContent = "";
    var main = document.createElement("main");         // the page's main landmark while it is the only thing on it
    var box = document.createElement("div");
    box.className = "boot boot-now";
    box.setAttribute("role", "alert");
    main.appendChild(box);
    var h = document.createElement("h1");
    h.textContent = "Couldn't load StratLab.";
    var p = document.createElement("p");
    p.textContent = "A file didn't download, which is usually a dropped connection. Reload to try again.";
    var b = document.createElement("button");
    b.type = "button";
    b.className = "boot-btn";
    b.textContent = "Reload";
    b.addEventListener("click", function () { location.reload(); });
    box.appendChild(h); box.appendChild(p); box.appendChild(b);
    root.appendChild(main);
  }

  /** A file failed to load: reload once, else say so. */
  function recover() {
    if (once()) location.reload(); else show();
  }

  // the saved light or dark choice, here as well as in theme.js: if that file fails to load the page still draws in the right theme
  try { var saved = localStorage.getItem("stratlab-theme"); if (saved) document.documentElement.dataset.theme = saved; } catch (e) { /* storage off */ }

  window.__stratlabRecover = recover;
  window.__stratlabShowLoadError = show;

  // a lazily loaded page (Vite raises this when its file or one it needs fails to download)
  window.addEventListener("vite:preloadError", function (e) {
    if (e && e.preventDefault) e.preventDefault();
    // the page's code then arrives empty and the app fails on it: that failure is this download's, not the page's own
    window.__stratlabLoadFailed = true;
    recover();
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
    if (/\/assets\//.test(url) && (t.tagName === "SCRIPT" || t.tagName === "LINK")) recover();
  }, true);

  // the page is still the plain start-up text after a long wait
  setTimeout(function () {
    var root = document.getElementById("root");
    if (root && root.querySelector("[data-boot]")) show();
  }, SLOW);
})();
