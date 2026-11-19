/* /login and /signup only (scripts/seoPages.mjs loginFrame, LIVE16B-001): the sign-in choices the page's HTML draws work before the app's
 * code has arrived. A press on Continue with Google or Email me a code is kept, with the address typed, and the app does it once it draws
 * (pages/Login.tsx, components/EmailSignIn.tsx read window.__stratlabEarly); the address box's words and focus carry over into the app's
 * own box. With email sign-in off in /config.js, the page is marked and the email way is hidden (index.html). A plain file, read only by
 * these two pages, so the landing page's download is unchanged. */
(function () {
  var w = window, d = document, c = w.STRATLAB_CONFIG || {};
  var on = c.EMAIL_SIGNIN === true || /^(on|true|1|yes)$/i.test(String(c.EMAIL_SIGNIN || "").trim());
  if (!on) d.documentElement.setAttribute("data-email-off", "1");
  var e = w.__stratlabEarly = w.__stratlabEarly || {};
  function inFrame(t, sel) { return t && t.closest ? t.closest(sel) : null; }
  d.addEventListener("click", function (ev) {
    var b = inFrame(ev.target, "[data-boot-google]");
    if (!b) return;
    ev.preventDefault();
    e.way = "google";
    b.setAttribute("aria-busy", "true");
  });
  d.addEventListener("submit", function (ev) {
    var f = inFrame(ev.target, "[data-boot-email] form");
    if (!f) return;
    ev.preventDefault();
    var box = f.querySelector("input[name=email]");
    e.email = box ? box.value : "";
    e.way = "email";
    var b = f.querySelector("button[type=submit]");
    if (b) { b.setAttribute("aria-busy", "true"); b.textContent = "Sending…"; }
  });
  d.addEventListener("input", function (ev) { if (inFrame(ev.target, "[data-boot-email]")) e.email = ev.target.value; });
  d.addEventListener("focusin", function (ev) { e.focus = !!inFrame(ev.target, "[data-boot-email] input"); });
})();
