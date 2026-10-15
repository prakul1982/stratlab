// Applies the saved light/dark choice before the page paints (a file, not inline, so the CSP can forbid inline scripts).
try { var t = localStorage.getItem("stratlab-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* storage off */ }
// the browser's own bar follows an explicit choice (the media variants in index.html follow the system one)
try { if (t === "light" || t === "dark") document.querySelectorAll('meta[name="theme-color"]').forEach(function (m) { m.setAttribute("content", t === "dark" ? "#141311" : "#F5F1E8"); }); } catch (e) { /* no meta */ }
