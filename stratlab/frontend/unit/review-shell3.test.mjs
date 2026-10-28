// Review 3 of the app shell: the service worker that was never registered, a plain "Sign out" that signed out every device, a
// service worker that kept public pages as the app, signed-in visitors shown "Sign in", and the smaller fixes beside them.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import vm from "node:vm";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const mem = new Map();
const store = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
globalThis.localStorage = store;
const setNavigator = (v) => Object.defineProperty(globalThis, "navigator", { configurable: true, value: v });
const flush = () => new Promise((ok) => setTimeout(ok, 0));

/** A page the way pwa.ts sees it: `readyState`, the events it was given, and a service worker that records register(). */
function page({ readyState, withReg = false }) {
  const listeners = {}, registered = [], timers = [];
  const win = {
    STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "https://abc.supabase.co", SUPABASE_ANON_KEY: "k" },
    addEventListener: (t, f, o) => { (listeners[t] ??= []).push({ f, o }); },
    setTimeout: (f) => { timers.push(f); return 1; },
    requestIdleCallback: (f) => f(),
  };
  globalThis.window = win;
  globalThis.document = { readyState };
  setNavigator({ userAgent: "x", serviceWorker: { register: async (u) => { registered.push(u); }, getRegistration: async () => (withReg ? {} : undefined), ready: new Promise(() => {}) } });
  return { win, listeners, registered, timers };
}

test("the service worker is registered when the page has already loaded, else on load (it was never registered)", async () => {
  const { registerPwa } = await import("../src/lib/pwa.ts");
  let p = page({ readyState: "complete" });
  registerPwa();
  assert.deepEqual(p.registered, ["/sw.js"], "load has fired already: no waiting for it");
  assert.equal((p.listeners.load ?? []).length, 0);

  p = page({ readyState: "loading" });
  registerPwa();
  assert.deepEqual(p.registered, []);
  assert.equal(p.listeners.load.length, 1);
  assert.deepEqual(p.listeners.load[0].o, { once: true });
  p.listeners.load[0].f();
  assert.deepEqual(p.registered, ["/sw.js"]);

  p = page({ readyState: "complete" });             // a visitor's page: after a pause and when idle
  registerPwa({ later: true });
  assert.deepEqual(p.registered, []);
  assert.equal(p.timers.length, 1);
  p.timers[0]();
  assert.deepEqual(p.registered, ["/sw.js"]);
});

test("the install offer that came before pwa.ts did is kept, and the button hears about it", async () => {
  const { registerPwa, canInstall, onInstallChange, install } = await import("../src/lib/pwa.ts");
  const p = page({ readyState: "complete" });
  assert.equal(canInstall(), false);
  let heard = 0;
  onInstallChange(() => { heard += 1; });
  let prompted = 0;
  p.win.__stratlabInstall = { prompt: async () => { prompted += 1; }, userChoice: Promise.resolve({ outcome: "accepted" }) };   // public/boot.js kept it
  registerPwa();
  assert.equal(canInstall(), true);
  assert.equal(heard, 1);
  assert.equal(await install(), true);
  assert.equal(prompted, 1);
  assert.equal(canInstall(), false);
  assert.equal(p.win.__stratlabInstall, null);
  // an offer that arrives later still works
  const late = { preventDefault() {}, prompt: async () => {}, userChoice: Promise.resolve({ outcome: "dismissed" }) };
  p.listeners.beforeinstallprompt[0].f(late);
  assert.equal(canInstall(), true);
  p.listeners.appinstalled[0].f();
  assert.equal(canInstall(), false);
  const boot = read("public/boot.js");
  assert.match(boot, /addEventListener\("beforeinstallprompt", function \(e\) \{ if \(e\.preventDefault\) e\.preventDefault\(\); window\.__stratlabInstall = e; \}\)/);
  assert.match(boot, /addEventListener\("appinstalled", function \(\) \{ window\.__stratlabInstall = null; \}\)/);
});

test("turning on notifications never waits for ever on the service worker", async () => {
  const { serviceWorkerReady } = await import("../src/lib/pwa.ts");
  // no registration yet: it is registered first, then the wait ends when the worker is active
  const reg = { pushManager: {} };
  const calls = [];
  setNavigator({ serviceWorker: { getRegistration: async () => undefined, register: async (u) => { calls.push(u); }, ready: Promise.resolve(reg) } });
  assert.equal(await serviceWorkerReady(1000), reg);
  assert.deepEqual(calls, ["/sw.js"]);
  // a registration that is already there is not registered again
  calls.length = 0;
  setNavigator({ serviceWorker: { getRegistration: async () => reg, register: async (u) => { calls.push(u); }, ready: Promise.resolve(reg) } });
  assert.equal(await serviceWorkerReady(1000), reg);
  assert.deepEqual(calls, []);
  // a worker that never becomes active: a clear error after the wait
  setNavigator({ serviceWorker: { getRegistration: async () => reg, register: async () => {}, ready: new Promise(() => {}) } });
  const t = Date.now();
  await assert.rejects(serviceWorkerReady(30), /didn't start in time\. Reload the page and try again/);
  assert.ok(Date.now() - t < 2000);
  // a registration the browser refuses
  setNavigator({ serviceWorker: { getRegistration: async () => undefined, register: async () => { throw new Error("SecurityError"); }, ready: new Promise(() => {}) } });
  await assert.rejects(serviceWorkerReady(1000), /couldn't start in this browser/);
  assert.match(read("src/lib/pwa.ts"), /try \{ reg = await serviceWorkerReady\(\); \} catch \(e\) \{ return \(e as Error\)\.message; \}/);
  assert.doesNotMatch(read("src/lib/pwa.ts"), /await navigator\.serviceWorker\.ready/);
});

test("'Sign out' leaves this device only, and signs out even when the sign-in service doesn't answer", async () => {
  globalThis.window = { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "https://abc.supabase.co", SUPABASE_ANON_KEY: "k" } };
  setNavigator({ userAgent: "x" });
  const { signOutHere } = await import("../src/lib/signout.ts");
  const key = "sb-abc-auth-token";
  const run = async (answer) => {
    mem.set(key, "{}"); mem.set("stratlab.viewas.v1", "pro");
    const seen = []; let reloads = 0;
    await signOutHere({ signOut: async (o) => { seen.push(o); return answer(); } }, () => { reloads += 1; });
    return { seen, reloads };
  };
  let r = await run(() => ({ error: null }));
  assert.deepEqual(r.seen, [{ scope: "local" }]);
  assert.equal(r.reloads, 0);
  assert.equal(mem.has(key), true, "the library removes its own session on success");
  r = await run(() => ({ error: new Error("Failed to fetch") }));
  assert.deepEqual(r.seen, [{ scope: "local" }]);
  assert.equal(r.reloads, 1);
  assert.equal(mem.has(key), false, "the saved session is removed so the reload comes up signed out");
  assert.equal(mem.has("stratlab.viewas.v1"), false);
  r = await run(() => { throw new Error("boom"); });
  assert.equal(r.reloads, 1);
  assert.equal(mem.has(key), false);
  // the three plain sign-outs use it, none leaves the default (global) scope, and only 'Sign out everywhere' is global
  for (const f of ["src/components/SideMenus.tsx", "src/pages/AccountPage.tsx", "src/lib/app.tsx"]) assert.match(read(f), /signOutHere\(supabase\.auth\)/, f);
  const all = ["src/components/SideMenus.tsx", "src/pages/AccountPage.tsx", "src/lib/app.tsx"].map(read).join("\n");
  assert.doesNotMatch(all, /signOut\(\)/);
  assert.equal([...all.matchAll(/scope: "global"/g)].length, 1);
  assert.match(read("src/pages/AccountPage.tsx"), /const \{ error \} = await supabase\.auth\.signOut\(\{ scope: "global" \}\); if \(error\) throw error;/);
});

function worker() {
  const handlers = {}, kept = [], deleted = [];
  let keys = [];
  const ok = (type, status = 200) => ({ ok: status < 300, status, headers: { get: () => type }, clone() { return this; } });
  const caches = {
    open: async (name) => ({ put: async (k) => { kept.push([name, k]); }, add: async () => undefined }),
    match: async () => undefined, keys: async () => keys, delete: async (k) => { deleted.push(k); return true; },
  };
  const self = { addEventListener: (t, f) => { handlers[t] = f; }, location: { origin: "https://stratlab.studio" }, skipWaiting() {}, clients: { claim() {} } };
  let next = () => Promise.resolve(ok("text/html; charset=utf-8"));
  vm.runInNewContext(read("public/sw.js"), { self, caches, fetch: () => next(), URL, Response: { error: () => "error" }, Promise, String });
  const visit = async (path) => {
    kept.length = 0;
    let a; handlers.fetch({ request: { method: "GET", url: "https://stratlab.studio" + path, mode: "navigate" }, respondWith: (p) => { a = p; } });
    if (a !== undefined) await a;
    await flush();
    return kept.filter(([, k]) => k === "/").length;
  };
  const activate = async (existing) => { keys = existing; let w; handlers.activate({ waitUntil: (p) => { w = p; } }); await w; return deleted; };
  return { visit, activate, setNext: (f) => { next = f; }, ok };
}

test("the service worker keeps only the app's own pages as the app shell, and drops a shell kept by the old version", async () => {
  const w = worker();
  for (const path of ["/", "/mine", "/holdings", "/research/IN/TCS", "/n/abc/e/2", "/account", "/trade/signals", "/admin/system", "/paper/s1"]) {
    assert.equal(await w.visit(path), 1, `${path} is the app: kept`);
  }
  for (const path of ["/stocks/in/TCS", "/stocks", "/c/abc", "/v/abc", "/unsubscribe", "/email/confirm", "/news-link/12/3", "/blog", "/blog/briefs", "/blog/india-market-brief-2026-10-27", "/library", "/library/seed-x", "/terms", "/privacy", "/refunds",
    "/contact", "/pricing", "/faq", "/about", "/help", "/login", "/signup", "/plans", "/verdict/abc", "/mineral", "/newsletter", "/nothing"]) {
    assert.equal(await w.visit(path), 0, `${path} is a page of its own: never kept as the app`);
  }
  assert.match(read("public/sw.js"), /const SHELL = "stratlab-shell-v4";/);
  assert.deepEqual(await w.activate(["stratlab-shell-v3", "stratlab-shell-v4", "stratlab-shell-v2"]), ["stratlab-shell-v3", "stratlab-shell-v2"]);
  w.setNext(() => Promise.resolve(w.ok("text/html", 500)));
  assert.equal(await w.visit("/mine"), 0, "a server error page is not kept either");
});

test("a signed-in visitor of a shared library page sees 'Open StratLab', not a sign-in", async () => {
  globalThis.window = { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "https://abc.supabase.co", SUPABASE_ANON_KEY: "k" } };
  const { signedInHere } = await import("../src/lib/signin.ts");
  mem.delete("sb-abc-auth-token");
  assert.equal(signedInHere(), false);
  mem.set("sb-abc-auth-token", "{}");
  assert.equal(signedInHere(), true);
  const frame = read("src/components/PublicFrame.tsx");
  assert.match(frame, /\{action \?\? \(signedInHere\(\) \? <OpenApp \/> : <a className="btn outline sm" href="\/" onPointerEnter=\{warmSignIn\} onFocus=\{warmSignIn\} onTouchStart=\{warmSignIn\} onClick=\{\(e\) => \{ e\.preventDefault\(\); void signIn\(\); \}\}>Sign in<\/a>\)\}/);
  assert.match(frame, /<a className=\{className\} href="\/">Open StratLab<\/a>/);            // a whole page load: the app starts, not the visitor's landing page
  const lib = read("src/pages/PublicLibrary.tsx");
  // (PUB-1: the header's button is the small one, like the landing page's, the card's the full-size one)
  assert.match(lib, /signedInHere\(\) \? <OpenApp className=\{small \? "btn sm" : "btn"\} \/> : <button type="button" className=\{small \? "btn sm" : "btn"\} onClick=\{\(\) => void signIn\("\/library"\)\}/);
  assert.equal([...lib.matchAll(/<GoogleCopy label="Continue with Google" small \/>/g)].length, 2);
  assert.equal([...lib.matchAll(/<GoogleCopy/g)].length, 3);                                   // the two headers and the "Test it yourself" card all go through it
});

test("the search palette stops its work when it is closed", () => {
  const src = read("src/components/SearchPalette.tsx");
  assert.match(src, /const cancelled = useRef\(false\);/);
  assert.match(src, /useEffect\(\(\) => \{ cancelled\.current = false; return \(\) => \{ cancelled\.current = true; \}; \}, \[\]\);/);
  assert.match(src, /const close = \(\) => \{ cancelled\.current = true; onClose\(\); \};/);
  assert.match(src, /onEscape: close/);
  assert.match(src, /if \(e\.target === e\.currentTarget\) close\(\);/);
  assert.match(src, /const go = \(to: string, state\?: unknown\) => \{ if \(cancelled\.current\) return; onClose\(\);/);
  // every await in buildAndRun, runIntent and doIt is followed by a check before the next step, api call or go()
  const body = (name) => { const a = src.indexOf(`const ${name} = async`); return src.slice(a, src.indexOf("\n  };", a)); };
  for (const name of ["buildAndRun", "runIntent", "doIt"]) {
    const lines = body(name).split("\n");
    lines.forEach((ln, i) => {
      if (!/\bawait\b/.test(ln) || /^\s*(\/\/|\*)/.test(ln)) return;
      const rest = lines.slice(i + 1, i + 5).join("\n") + ln;           // go() checks too, so an await that goes straight to it is covered
      assert.match(rest, /cancelled\.current|\bgo\(/, `${name}: no check after "${ln.trim().slice(0, 60)}"`);
    });
  }
});

test("vercel.json: config.js, boot.js and theme.js are never served stale", () => {
  const v = JSON.parse(read("vercel.json"));
  const rule = (src) => v.headers.find((h) => h.source === src).headers.find((h) => h.key === "Cache-Control").value;
  assert.equal(rule("/config.js"), "public, max-age=60, must-revalidate");
  assert.equal(rule("/(boot|theme).js"), "public, max-age=300, must-revalidate");
});

test("the start-up script's 'a file failed' flag is cleared once the page has drawn, so a later crash isn't taken for a download", () => {
  const guard = read("src/components/LoadGuard.tsx");
  // (a .tsx file can't be loaded by this runner: the source is checked)
  assert.match(guard, /componentDidMount\(\) \{ if \(!this\.state\.failed && typeof window !== "undefined"\) window\.__stratlabLoadFailed = false; \}/);
  assert.match(guard, /!!window\.__stratlabLoadFailed/);           // a draw that threw still reads the flag: the empty module's error has a message of its own
  assert.match(read("public/boot.js"), /window\.__stratlabLoadFailed = true;\s*recover\(\);/);
});

test("moved addresses keep the query and hash; the space switch is buttons, not a radio group without arrow keys", () => {
  const main = read("src/main.tsx");
  assert.match(main, /function Redirect\(\{ to \}: \{ to: string \}\) \{\s*const \{ search, hash \} = useLocation\(\);\s*return <Navigate to=\{\{ pathname: to, search, hash \}\} replace \/>;/);
  for (const from of ["/all", "/login", "/signup", "/pricing", "/upgrade", "/faq", "/scans", "/research/scans", "/watchlist"]) {
    assert.match(main, new RegExp(`path="${from}" element=\\{<Redirect to="[^"]+" />\\}`), from);
  }
  assert.doesNotMatch(main, /<Navigate to="/);
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /<div className="space-switch" role="group" aria-label="Space">/);
  assert.match(shell, /<button key=\{v\} type="button" aria-pressed=\{space === v\}/);
  assert.doesNotMatch(shell.slice(shell.indexOf("function SpaceSwitch")), /role="radio/);
  assert.match(read("src/styles.css"), /\.space-switch button\[aria-pressed="true"\]/);
});
