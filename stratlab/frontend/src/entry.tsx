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
import { isPublicForAll, publicReads, wantsAccount } from "./lib/entry";
import { holdStartup } from "./lib/held";

/* The one entry point. It reads /config.js (once more, if the first try failed), then loads only the half of the site this
 * page load needs: the full app for someone signed in (or just back from Google), and the much smaller public half for
 * everyone else (the landing page, the policies, a shared verdict, StratLab's library). The first page's code is asked
 * for at the same time as the half itself. If the config can't be read the page says so, with a Reload button, instead of
 * staying blank (public/boot.js also reloads once when a file fails to download). Nothing here imports the app's code
 * directly, so a visitor doesn't download any of it. */

/** The first public page's code, by address (the same files VisitorApp loads, asked for early). */
const publicPage = (p: string) =>
  /^\/(terms|privacy|refunds|contact)\/?$/.test(p) ? import("./pages/LegalPage")
    : /^\/verdict\//.test(p) ? import("./pages/PublicVerdict")
    : /^\/library(\/|$)/.test(p) ? import("./pages/PublicLibrary")
    : /^\/(pricing|plans|upgrade|help|faq|features|login|signup|about)?\/?$/.test(p) ? import("./pages/Login")
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

async function start() {
  const root = document.getElementById("root");
  if (!root) return;
  const path = location.pathname;
  if (!(await readConfig()) && !isPublicForAll(path)) { window.__stratlabShowLoadError?.(); return; }
  const account = !isPublicForAll(path) && wantsAccount({ supabaseUrl: window.STRATLAB_CONFIG?.SUPABASE_URL, search: location.search, hash: location.hash, storage: localStorage });
  const [{ captureRef }, { startErrorReports }] = await Promise.all([import("./lib/share"), import("./lib/sentry")]);
  holdStartup(root);                  // the page's own words, drawn again until its code is here (R10V-006)
  captureRef();                       // a friend's invite link: kept until sign-in
  startErrorReports({ lazy: !account });   // a visitor's page downloads the error reporter only if something breaks
  if (account) {
    const app = await import("./main");
    app.startApp(root);
  } else {
    // the page's questions to the server first (lib/http is in the start-up file already), then its code, alongside the half itself
    const reads = publicReads(path);
    if (reads.length) import("./lib/http").then((m) => reads.forEach((r) => m.prefetchPublic(r))).catch(() => undefined);
    const early = publicPage(path).catch(() => undefined);
    const visitor = await import("./visitor/visitorMain");
    visitor.startVisitor(root);
    void early;
  }
  if (import.meta.env.PROD) import("./lib/pwa").then((m) => m.registerPwa({ later: !account })).catch(() => undefined);
}

/* A failed download of the app's own chunk on the first load (a dropped connection; seen once on Safari as an "Unhandled Promise
 * Rejection ... import(./main-...js)", R9P-008) used to leave the plain start-up text and nothing else. The start-up script
 * (public/boot.js) then reloads once on its own, and if that does not help it shows the Reload card. */
start().catch(() => { if (window.__stratlabRecover) window.__stratlabRecover(); else window.__stratlabShowLoadError?.(); });
