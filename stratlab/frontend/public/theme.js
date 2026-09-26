// Applies the saved light/dark choice before the page paints (a file, not inline, so the CSP can forbid inline scripts).
try { var t = localStorage.getItem("stratlab-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* storage off */ }
