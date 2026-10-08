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
import { isPublicForAll, wantsAccount } from "./lib/entry";

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

/** /config.js is a plain script in the page's head. If it didn't run (a failed download), try it once more. */
async function readConfig(): Promise<boolean> {
  if (window.STRATLAB_CONFIG) return true;
  await new Promise<void>((done) => {
    const s = document.createElement("script");
    s.src = `/config.js?retry=${Date.now()}`;
    s.onload = () => done();
    s.onerror = () => done();
    document.head.appendChild(s);
    window.setTimeout(done, 8000);
  });
  return !!window.STRATLAB_CONFIG;
}

async function start() {
  const root = document.getElementById("root");
  if (!root) return;
  const path = location.pathname;
  if (!(await readConfig()) && !isPublicForAll(path)) { window.__stratlabShowLoadError?.(); return; }
  const account = !isPublicForAll(path) && wantsAccount({ supabaseUrl: window.STRATLAB_CONFIG?.SUPABASE_URL, search: location.search, hash: location.hash, storage: localStorage });
  const [{ captureRef }, { startErrorReports }] = await Promise.all([import("./lib/share"), import("./lib/sentry")]);
  captureRef();                       // a friend's invite link: kept until sign-in
  startErrorReports();
  if (account) {
    const app = await import("./main");
    app.startApp(root);
  } else {
    const early = publicPage(path).catch(() => undefined);       // started now, alongside the half itself
    const visitor = await import("./visitor/visitorMain");
    visitor.startVisitor(root);
    void early;
  }
  if (import.meta.env.PROD) import("./lib/pwa").then((m) => m.registerPwa()).catch(() => undefined);
}

void start();
