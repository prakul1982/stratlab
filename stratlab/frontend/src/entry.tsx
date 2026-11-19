import "@fontsource/montserrat/300.css";
import "@fontsource/montserrat/800.css";
import "@fontsource/fraunces/400.css";
import "@fontsource/fraunces/600.css";
import "@fontsource/fraunces/400-italic.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles.css";
import "./styles-invest.css";
import { isAdVisit, isPublicForAll, publicReads, wantsAccount } from "./lib/entry";
import { holdStartup } from "./lib/held";

/* The one entry point. It reads /config.js (once more, if the first try failed), then loads only the half of the site this
 * page load needs: the full app for someone signed in (or just back from Google), and the much smaller public half for
 * everyone else (the landing page, the policies, a shared verdict, StratLab's library). The first page's code is asked
 * for at the same time as the half itself. If the config can't be read the page says so, with a Reload button, instead of
 * staying blank (public/boot.js also reloads once when a file fails to download). Nothing here imports the app's code
 * directly, so a visitor doesn't download any of it. */

/** The first public page's code, by address (the same files VisitorApp loads, asked for early). */
const publicPage = (p: string) =>
  /^\/start\/?$/.test(p) || (p === "/" && isAdVisit(location.search)) ? import("./pages/AdLanding")
    : /^\/(about|terms|privacy|refunds|contact)\/?$/.test(p) ? import("./pages/LegalPage")
    : /^\/verdict\//.test(p) ? import("./pages/PublicVerdict")
    : /^\/library(\/|$)/.test(p) ? import("./pages/PublicLibrary")
    : /^\/(pricing|plans|upgrade|help|faq|features|login|signup)?\/?$/.test(p) ? import("./pages/Login")
    : import("./pages/Gate");

/** Try /config.js once. A failed download (an error page where the file should be) leaves the config unset. */
function loadConfig(attempt: number): Promise<void> {
  return new Promise<void>((done) => {
    const s = document.createElement("script");
    s.src = `/config.js?retry=${attempt}-${Date.now()}`;
    s.onload = () => done();
    s.onerror = () => done();
    document.head.appendChild(s);
    window.setTimeout(done, 8000);
  });
}

/** /config.js is a plain script in the page's head. If it didn't run (a failed download, about one load in ten was an
 * error page), try again, twice, a little later each time. Without it the app can't tell who is signed in, so it never
 * guesses "signed out": the page says it couldn't load and offers Reload. */
async function readConfig(): Promise<boolean> {
  for (const wait of [0, 500, 1500]) {
    if (window.STRATLAB_CONFIG) return true;
    if (wait) await new Promise((ok) => window.setTimeout(ok, wait));
    await loadConfig(wait);
  }
  return !!window.STRATLAB_CONFIG;
}

/** LIVE14A-014 / LIVE14B-003: the home page's hero words wait, hidden, for their own faces (public/boot.js sets data-faces; index.html, at
 * most 3 s), and the app's hero, drawn over them, waits as long (at most 1.5 s more): drawn in a stand-in with its faces a moment behind,
 * its words re-wrapped and the example card beside them moved (CLS 0.07). Another page, or the faces already here: at once. */
function heroFaces(): Promise<void> {
  const html = document.documentElement;
  if (!html.hasAttribute("data-home") || html.hasAttribute("data-faces")) return Promise.resolve();
  return new Promise((ok) => {
    const done = () => { seen.disconnect(); ok(); };
    const seen = new MutationObserver(() => { if (html.hasAttribute("data-faces")) done(); });
    seen.observe(html, { attributes: true, attributeFilter: ["data-faces"] });
    window.setTimeout(done, 1500);
  });
}

async function start() {
  const root = document.getElementById("root");
  if (!root) return;
  const path = location.pathname;
  if (!(await readConfig()) && !isPublicForAll(path)) { window.__stratlabShowLoadError?.(); return; }
  const account = !isPublicForAll(path) && wantsAccount({ supabaseUrl: window.STRATLAB_CONFIG?.SUPABASE_URL, search: location.search, hash: location.hash, storage: localStorage });
  if (!account) holdStartup(root);    // the page's own words, drawn again until its code is here (R10V-006); not for a saved sign-in (R29B-019)
  const appCode = account ? import("./main") : null;      // the app's code downloads beside the small helpers below, not after them
  appCode?.catch(() => undefined);
  // LIVE11B-004: whether Indian data is offline, asked now beside the app's code and the sign-in check, so the first page frame carries the line
  // LIVE13B-004: and the account itself (/me), with the saved sign-in's token, not after the app's ~90 files (lib/accountEarly.ts)
  if (account) import("./lib/accountEarly").then((m) => m.startAccountReads()).catch(() => undefined);
  // LIVE12A-013: a visitor's page questions, its page code and the visitor half are asked for now, beside the two small helpers below,
  // not after them: the landing's chunks waited a round trip for the helpers first (LCP 3.7 s desktop, 3.2 s phone)
  if (!account) {
    const reads = publicReads(path);
    if (reads.length) import("./lib/http").then((m) => reads.forEach((r) => m.prefetchPublic(r))).catch(() => undefined);
  }
  const early = account ? null : publicPage(path).catch(() => undefined);
  // R71: a visitor's page draws once its fonts are here (asked for now, beside its code; at most 1.5 s), not in the fallback fonts
  // and then again in its own: the swap moved /library's chips and cards sideways (0.106) whenever its list arrived first
  const fonts = account ? null : Promise.race([new Promise((ok) => window.setTimeout(ok, 1500)),
    Promise.all(["300 1em Montserrat", "800 1em Montserrat", "1em Fraunces", "600 1em Fraunces", "1em IBM Plex Sans", "500 1em IBM Plex Sans", "600 1em IBM Plex Sans"]
      .map((f) => document.fonts.load(f)))]).then(heroFaces).catch(() => undefined);
  const visitorCode = account ? null : import("./visitor/visitorMain");
  visitorCode?.catch(() => undefined);
  const [{ captureRef }, { startErrorReports }] = await Promise.all([import("./lib/share"), import("./lib/sentry")]);
  captureRef();                       // a friend's invite link: kept until sign-in
  startErrorReports({ lazy: !account });   // a visitor's page downloads the error reporter only if something breaks
  if (account) {
    const app = await appCode!;
    app.startApp(root);
  } else {
    const visitor = await visitorCode!;
    await fonts;
    visitor.startVisitor(root);
    void early;
  }
  // Release 71: a visitor's page downloads the install and offline helper only after it has loaded (it registered later anyway, and
  // an install offer that comes first is kept by the start-up script), so the landing's first download stays under its budget
  const pwa = () => import("./lib/pwa").then((m) => m.registerPwa({ later: !account })).catch(() => undefined);
  if (import.meta.env.PROD) {
    if (account) pwa();
    else if (document.readyState === "complete") window.setTimeout(pwa, 4000);
    else window.addEventListener("load", () => window.setTimeout(pwa, 4000), { once: true });
  }
}

/* A failed download of the app's own chunk on the first load (a dropped connection; seen once on Safari as an "Unhandled Promise
 * Rejection ... import(./main-...js)", R9P-008) used to leave the plain start-up text and nothing else. The start-up script
 * (public/boot.js) then reloads once on its own, and if that does not help it shows the Reload card. */
start().catch(() => { if (window.__stratlabRecover) window.__stratlabRecover(); else window.__stratlabShowLoadError?.(); });
