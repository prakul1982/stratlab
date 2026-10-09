// A visitor's review of the live site (round 5): the pages a crawler and a first-time visitor see. Config that leaks no notes,
// one address and one description per page, structured data from the real FAQ, real 404s only for addresses nothing is at,
// the policies' lists matching the code (AI providers, storage), and the boot guard that replaces a blank page.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const root = new URL("../", import.meta.url);
const read = (p) => fs.readFileSync(new URL(p, root), "utf8");
const backend = (p) => fs.readFileSync(new URL(`../../backend/${p}`, import.meta.url), "utf8");
const seo = await import("../src/content/seo.ts");
const { FAQ, faqText } = await import("../src/content/faq.ts");
const { seoFor } = await import("../src/lib/seo.ts").catch(() => ({}));
const links = await import("../src/lib/deepLinks.ts");
const entry = await import("../src/lib/entry.ts");
const { signInProblem } = await import("../src/lib/signinError.ts");
const { pageFiles, homeJsonLd } = await import("../scripts/seoPages.mjs");
const vercel = JSON.parse(read("vercel.json"));

test("config.js is public as it is served: no developer notes, and it still sets what the app reads", () => {
  const src = read("public/config.js");
  assert.doesNotMatch(src, /(^|\s)\/\/|\/\*/m, "a comment in config.js reaches every visitor");
  assert.doesNotMatch(src, /Razorpay|Add BUSINESS_ADDRESS|if you want/i);
  const win = {};
  vm.runInNewContext(src, { window: win });
  for (const k of ["API_BASE", "SUPABASE_URL", "SUPABASE_ANON_KEY", "BUSINESS_NAME", "CONTACT_EMAIL", "BILLING_EMAIL", "PRIVACY_EMAIL"]) assert.ok(win.STRATLAB_CONFIG[k], k);
  assert.ok(!("BUSINESS_ADDRESS" in win.STRATLAB_CONFIG) && !("BUSINESS_GSTIN" in win.STRATLAB_CONFIG), "the owner's details are not invented");
});

/** A vercel.json "source" as the whole-path pattern it means (a group in parentheses, as path-to-regexp reads it). */
const sourceRe = (source) => new RegExp("^" + source.replace(/\(\?:/g, "(?:") + "$");

test("only the app's own addresses go to index.html; anything else is a real 404, and /config.js is a plain file", () => {
  const rule = vercel.rewrites.find((r) => r.destination === "/index.html");
  const re = sourceRe(rule.source);
  // "/" is index.html itself, and /library and each StratLab strategy's /library/<id> are files of their own (the build writes
  // them), so they aren't sent to index.html: an unknown strategy's address is a real 404 (R7V-008; until then this list
  // expected /library/<id> to be rewritten, which made /library/seed-nope a 200 with the home page's tags)
  const mine = [...links.APP_ROUTES.map((r) => r.replace(/:[A-Za-z]+/g, "x").replace(/\/\*$/, "/x")), "/terms", "/privacy", "/refunds", "/contact", "/verdict/abc", "/faq", "/about", "/help"];
  for (const p of mine.filter((x) => x !== "/" && x !== "/library")) assert.ok(re.test(p), `${p} would be a 404`);
  for (const p of ["/nope", "/nowhere-at-all", "/config.js", "/boot.js", "/assets/x.js", "/favicon.ico", "/wp-admin", "/stocks", "/.env", "/termsx", "/research2", "/library/seed-nope"]) assert.ok(!re.test(p), `${p} is the app's`);
  // the forwarded addresses come first, so /stocks/… and the sitemaps still reach the API
  assert.equal(vercel.rewrites.at(-1), rule, "the app's rewrite is the last one");
  // /stocks itself is the API's list of public company pages (R5V-013), forwarded like /stocks/…, not sent home
  assert.ok(!(vercel.redirects ?? []).some((r) => r.source.startsWith("/stocks")), "/stocks is a page of its own");
  assert.ok(vercel.rewrites.some((r) => r.source === "/stocks/:path*"));
});

test("/config.js and the boot files have a sane cache header, and the app's own pages say noindex", () => {
  const header = (path, key) => vercel.headers.filter((h) => sourceRe(h.source).test(path)).flatMap((h) => h.headers).filter((h) => h.key === key).map((h) => h.value);
  const cfg = header("/config.js", "Cache-Control");
  assert.equal(cfg.length, 1);
  assert.match(cfg[0], /max-age=300/);
  assert.match(cfg[0], /stale-while-revalidate/);
  assert.doesNotMatch(cfg[0], /immutable|no-store/);
  assert.equal(header("/boot.js", "Cache-Control").length, 1);
  for (const p of ["/holdings", "/research/IN/TCS", "/n/abc/e/2", "/login", "/verdict/abc", "/account"]) assert.deepEqual(header(p, "X-Robots-Tag"), ["noindex, follow"], p);
  for (const p of ["/", "/pricing", "/faq", "/library", "/library/seed-x", "/terms", "/privacy", "/contact", "/stocks/in/TCS", "/config.js"]) assert.deepEqual(header(p, "X-Robots-Tag"), [], p);
});

test("every public page has its own title, description and one canonical address; the table matches the sitemap's", () => {
  assert.equal(new Set(seo.PAGES.map((p) => p.path)).size, seo.PAGES.length);
  assert.equal(new Set(seo.PAGES.map((p) => p.description)).size, seo.PAGES.length, "two pages share a description");
  assert.equal(new Set(seo.PAGES.map((p) => p.title)).size, seo.PAGES.length, "two pages share a title");
  for (const p of seo.PAGES) {
    assert.ok(p.description.length >= 40 && p.description.length <= 260, `${p.path}: ${p.description.length} characters`);
    assert.match(p.title, /StratLab/);
    assert.doesNotMatch(p.title + p.description, /\bhonest|Kite|Yahoo|Screener/i, p.path);
  }
  assert.equal(seo.pageMeta("/pricing/").title, "Plans · StratLab");
  assert.equal(seo.absolute("/"), "https://stratlab.studio/");
  assert.equal(seo.absolute("/terms"), "https://stratlab.studio/terms");
  // the backend lists the same indexable pages with the same last-changed days
  const py = backend("app/site_pages.py");
  const theirs = [...py.matchAll(/\("(\/[a-z/]*)", "(\d{4}-\d{2}-\d{2})"\)/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(theirs, seo.sitemapPages().map((p) => [p.path, p.updated]));
  // an alias names the page it repeats, and the sign-in addresses stay out of search
  for (const p of seo.PAGES.filter((x) => !x.index)) assert.ok(["/about", "/help", "/login", "/signup"].includes(p.path), p.path);
  // changed on purpose in R10V-005: a page kept out of search results names no canonical address (/help named /faq, /about named /)
  assert.equal(seo.pageMeta("/help").canonical, undefined);
  assert.equal(seo.pageMeta("/about").canonical, undefined);
  for (const p of seo.PAGES.filter((x) => !x.index)) assert.equal(p.canonical, undefined, p.path);
});

test("the tags for each kind of page: its own, noindex for a sign-in gate, a missing page and a shared verdict", () => {
  const home = seoFor("/");
  assert.deepEqual([home.index, home.canonical], [true, "https://stratlab.studio/"]);
  assert.equal(seoFor("/terms").description, seo.pageMeta("/terms").description);
  const gate = seoFor("/research/IN/NOPESYMBOL", "gate");
  assert.equal(gate.index, false);
  assert.equal(gate.canonical, null);              // changed on purpose in R10V-005: noindex, so no canonical
  assert.doesNotMatch(gate.description, /NOPESYMBOL/);
  assert.equal(seoFor("/nope", "notfound").index, false);
  assert.equal(seoFor("/verdict/abc", "verdict").index, false);
  assert.equal(seoFor("/login").index, false);
  assert.equal(seoFor("/help").canonical, null);
  const own = new Set(["/", "/pricing", "/faq", "/library", "/terms", "/privacy", "/refunds", "/contact"].map((p) => seoFor(p).description));
  assert.equal(own.size, 8);
});

test("each page's own HTML is written at build time, with structured data on the home page built from the real FAQ", () => {
  const template = read("index.html");
  const files = Object.fromEntries(pageFiles(template));
  assert.deepEqual(Object.keys(files).sort(), ["404.html", "about/index.html", "contact/index.html", "faq/index.html", "help/index.html", "index.html", "library/index.html",
    "login/index.html", "pricing/index.html", "privacy/index.html", "refunds/index.html", "signup/index.html", "terms/index.html"]);
  for (const [file, html] of Object.entries(files)) {
    for (const re of [/<title>/g, /<meta name="description"/g, /<meta name="robots"/g]) assert.equal((html.match(re) ?? []).length, 1, `${file} ${re}`);
    // changed on purpose in R8V-008: the 404 page names no canonical address (it named the home page); every other one names one,
    // and in R10V-005 so does every page kept out of search results (/about, /help, /login, /signup said "do not index" and named a canonical)
    const kept = /name="robots" content="noindex/.test(html);
    assert.equal((html.match(/<link rel="canonical"/g) ?? []).length, file === "404.html" || kept ? 0 : 1, `${file} canonical`);
    assert.doesNotMatch(html, /<!--jsonld-->/);
  }
  const terms = files["terms/index.html"];
  assert.match(terms, /<title>Terms · StratLab<\/title>/);
  assert.match(terms, /<link rel="canonical" href="https:\/\/stratlab\.studio\/terms">/);
  assert.match(terms, /content="index, follow"/);
  assert.doesNotMatch(terms, /ld\+json/);
  assert.match(files["404.html"], /content="noindex, follow"/);
  assert.match(files["login/index.html"], /content="noindex, follow"/);
  assert.doesNotMatch(files["help/index.html"], /rel="canonical"/);     // changed on purpose in R10V-005: noindex, so no canonical
  assert.doesNotMatch(files["about/index.html"], /rel="canonical"/);
  const ld = JSON.parse(files["index.html"].match(/<script type="application\/ld\+json">(.*?)<\/script>/s)[1]);
  assert.deepEqual(ld.map((x) => x["@type"]), ["Organization", "WebSite", "FAQPage"]);
  assert.deepEqual(ld[2].mainEntity.map((q) => q.name), FAQ.map((f) => f.q));
  assert.deepEqual(ld[2].mainEntity.map((q) => q.acceptedAnswer.text), FAQ.map(faqText));
  assert.ok(!homeJsonLd().slice(40, -9).includes("<"), "no tag can open or close inside the markup");
});

test("the plain page in index.html: a noscript message, a start-up fallback with the page's words, and the boot guard first", () => {
  const html = read("index.html");
  assert.match(html, /<noscript>[\s\S]*needs JavaScript[\s\S]*<\/noscript>/);
  assert.match(html, /<div id="root">\s*<main>\s*<div class="boot[^"]*" data-boot>[\s\S]*Facts, not tips/);   // in a main landmark (R8O-009)
  assert.ok(html.indexOf('src="/boot.js"') < html.indexOf('src="/config.js"') && html.indexOf('src="/config.js"') < html.indexOf('src="/src/entry.tsx"'));
  assert.match(html, /<link rel="canonical" href="https:\/\/stratlab\.studio\/">/);
});

test("boot guard: a failed file reloads once, a second failure says so instead of staying blank", () => {
  const src = read("public/boot.js");
  const make = () => {
    const listeners = {};
    const store = new Map();
    const root = { children: [], textContent: "x", querySelector: (s) => (/boot/.test(s) ? root.boot : null), appendChild(c) { root.children.push(c); } };
    root.boot = {};
    const el = (tag) => ({ tag, children: [], appendChild(c) { this.children.push(c); }, setAttribute() {}, addEventListener() {} });
    const ctx = { reloads: 0, timers: [] };
    const win = { addEventListener: (t, f) => { listeners[t] = f; } };
    const location = { reload: () => { ctx.reloads++; } };
    const document = { getElementById: () => root, createElement: el };
    let now = 1e12;
    const sandbox = { window: win, document, location, setTimeout: (f, ms) => ctx.timers.push([f, ms]), Date: { now: () => now },
      sessionStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) } };
    vm.runInNewContext(src, sandbox);
    return { listeners, ctx, root, win, tick: (ms) => { now += ms; } };
  };
  const a = make();
  a.listeners["vite:preloadError"]({ preventDefault() {} });
  assert.equal(a.ctx.reloads, 1);
  a.listeners["vite:preloadError"]({ preventDefault() {} });
  assert.equal(a.ctx.reloads, 1, "no reload loop");
  assert.equal(a.root.children.length, 1, "the message is drawn");
  const b = make();
  b.listeners.error({ target: { tagName: "SCRIPT", src: "https://x/assets/index-abc.js" } });
  assert.equal(b.ctx.reloads, 1, "one of the app's own scripts failing");
  const c = make();
  c.listeners.error({ target: { tagName: "SCRIPT", src: "https://ads.example/x.js" } });
  assert.equal(c.ctx.reloads, 0, "another site's script is not the app's");
  assert.equal(typeof c.win.__stratlabRecover, "function");
  assert.ok(c.ctx.timers.some(([, ms]) => ms >= 10000), "a long wait with only the start-up text shows the message");
});

test("the public half never imports the account code (the sign-in library comes only with the app)", () => {
  const visitor = ["visitor/VisitorApp.tsx", "visitor/visitorMain.tsx", "pages/Login.tsx", "pages/Gate.tsx", "pages/LegalPage.tsx", "pages/PublicVerdict.tsx", "pages/PublicLibrary.tsx",
    "components/PublicFrame.tsx", "components/SkipLink.tsx", "components/LoadGuard.tsx", "components/LibraryBits.tsx", "components/LegalLinks.tsx", "lib/signin.ts",
    "lib/currency.ts", "lib/http.ts", "lib/config.ts", "lib/entry.ts", "lib/seo.ts", "lib/title.ts", "lib/deepLinks.ts", "lib/analytics.ts", "entry.tsx", "components/ui.tsx"];
  for (const f of visitor) {
    const src = read(`src/${f}`);
    const imports = [...src.matchAll(/^import[^;]*?from\s+"([^"]+)"/gms)].map((m) => m[1]);
    for (const i of imports) assert.doesNotMatch(i, /(^|\/)lib\/(api|app)$|^\.\/(api|app)$|\/kit$|CompanySearch|CompanyCombobox|\/main$/, `${f} imports ${i}`);
  }
  assert.match(read("src/lib/signin.ts"), /await import\("\.\/api"\)/, "the sign-in library loads when someone signs in");
});

test("service worker: a config.js or theme.js that fails, and a page the server can't send, are replaced by the last good copy", async () => {
  const src = read("public/sw.js");
  const store = new Map();
  const handlers = {};
  const ok = (body, type, status = 200) => ({ ok: status < 300, status, body, headers: { get: () => type }, clone() { return this; } });
  let next = () => Promise.reject(new Error("offline"));
  const caches = {
    open: async () => ({ put: async (k, v) => { store.set(k, v); }, addAll: async () => undefined }),
    match: async (k) => store.get(k),
    keys: async () => [], delete: async () => true,
  };
  const self = { addEventListener: (t, f) => { handlers[t] = f; }, location: { origin: "https://stratlab.studio" }, skipWaiting() {}, clients: { claim() {} } };
  vm.runInNewContext(src, { self, caches, fetch: () => next(), URL, Response: { error: () => "error" }, Promise });
  const ask = async (url, mode = "no-cors") => {
    let answer;
    handlers.fetch({ request: { method: "GET", url, mode }, respondWith: (p) => { answer = p; } });
    return answer === undefined ? undefined : await answer;
  };
  next = () => Promise.resolve(ok("window.A=1", "application/javascript"));
  assert.equal((await ask("https://stratlab.studio/config.js")).body, "window.A=1");
  next = () => Promise.resolve(ok("upstream request failed", "text/plain", 502));
  assert.equal((await ask("https://stratlab.studio/config.js")).body, "window.A=1", "the last good config.js, not the error text");
  next = () => Promise.reject(new Error("offline"));
  assert.equal((await ask("https://stratlab.studio/config.js")).body, "window.A=1");
  assert.equal(await ask("https://stratlab.studio/assets/x.js"), undefined, "other files are left to the browser");
  next = () => Promise.resolve(ok("<html>app</html>", "text/html; charset=utf-8"));
  assert.equal((await ask("https://stratlab.studio/alerts", "navigate")).body, "<html>app</html>");
  next = () => Promise.resolve(ok("upstream request failed", "text/plain", 502));
  assert.equal((await ask("https://stratlab.studio/pricing", "navigate")).body, "<html>app</html>", "a 502 for a page starts the app instead of showing plain text");
  next = () => Promise.resolve(ok("nope", "text/html", 404));
  assert.equal((await ask("https://stratlab.studio/nope", "navigate")).status, 404, "a real 404 stays a 404");
  assert.match(read("public/boot.js"), /localStorage\.getItem\("stratlab-theme"\)/, "boot.js applies the saved theme itself when theme.js fails");
});

test("the visitor routes: /faq, /library and a strategy, a made-up market, a gate and not found", () => {
  const kind = (p) => links.visitorView(p).kind;
  assert.deepEqual(links.visitorView("/faq"), { kind: "landing", section: "faq", panel: undefined });
  assert.equal(links.visitorView("/login").panel, "login");
  assert.equal(links.visitorView("/signup").panel, "signup");
  assert.equal(links.visitorView("/about").section, "about");
  assert.equal(kind("/terms"), "legal");
  assert.equal(kind("/library"), "library");
  assert.deepEqual(links.visitorView("/library/seed-ema-20-50-nifty50"), { kind: "libraryEntry", id: "seed-ema-20-50-nifty50" });
  assert.deepEqual(links.visitorView("/verdict/abc"), { kind: "verdict", token: "abc" });
  assert.equal(kind("/research/IN/RELIANCE"), "gate");
  assert.equal(kind("/research/XX/TCS"), "notfound", "no market called XX: not a page to sign in for");
  assert.equal(kind("/holdings"), "gate");
  assert.equal(kind("/nope"), "notfound");
  assert.equal(entry.isPublicForAll("/library/abc"), true);
  assert.equal(entry.isPublicForAll("/library"), false, "signed in, /library is the app's own page");
  assert.equal(entry.isPublicForAll("/terms"), true);
});

test("which half a page load needs: the whole app only with a saved sign-in or one arriving from Google", () => {
  const url = "https://demo.supabase.co";
  const store = (o) => ({ getItem: (k) => o[k] ?? null });
  assert.equal(entry.sessionKeyFor(url), "sb-demo-auth-token");
  assert.equal(entry.wantsAccount({ supabaseUrl: url, storage: store({}) }), false);
  assert.equal(entry.wantsAccount({ supabaseUrl: url, storage: store({ "sb-demo-auth-token": "{}" }) }), true);
  assert.equal(entry.wantsAccount({ supabaseUrl: url, hash: "#access_token=abc&refresh_token=d", storage: store({}) }), true);
  assert.equal(entry.wantsAccount({ supabaseUrl: url, hash: "#error=access_denied&error_description=x", storage: store({}) }), false, "a refused sign-in is for the landing page to explain");
  assert.equal(entry.wantsAccount({ supabaseUrl: url, storage: { getItem() { throw new Error("blocked"); } } }), true);
});

test("a refused or failed Google sign-in is said in words (R5V-015)", () => {
  assert.equal(signInProblem("", ""), null);
  assert.equal(signInProblem("?ref=abc", "#pricing"), null);
  assert.match(signInProblem("?error=access_denied&error_description=User+denied", ""), /not signed in.*cancelled/);
  assert.match(signInProblem("", "#error=access_denied&error_code=x"), /Continue with Google to try again/);
  assert.match(signInProblem("", "#error=server_error&error_description=Unable+to+exchange+external+code"), /couldn't finish on our side/);
  assert.doesNotMatch(signInProblem("", "#error=server_error&error_description=Unable+to+exchange+external+code"), /Supabase|Client ID|Secret/);
  assert.match(signInProblem("?error=other&error_description=Something+odd+happened.", ""), /^Sign-in didn't finish: Something odd happened\./);
});

test("the FAQ says what the backend does: invite rewards, and that options are paper traded, not backtested", () => {
  const py = backend("app/invite_rewards.py");
  const n = (name) => Number(py.match(new RegExp(`^${name}\\s*=\\s*(?:timedelta\\(days=)?(\\d+)`, "m"))[1]);
  const invites = faqText(FAQ.find((f) => f.q === "How do invite rewards work?"));
  assert.match(invites, new RegExp(`first ${n("ACTIVE_DAYS") - 1 + 0 || 3} different days|3 different days`));
  assert.equal(n("ACTIVE_DAYS"), 3);
  assert.match(invites, new RegExp(`in their first ${n("WINDOW")} days`));
  assert.match(invites, new RegExp(`for your first ${n("USE_CAP")} friends in any 12 months`));
  assert.match(invites, new RegExp(`for your first ${n("PAY_CAP")} paying friends in 12 months`));
  assert.match(invites, new RegExp(`within ${n("PAY_WITHIN")} days of joining`));
  const extraDays = Math.floor(n("MONTH_DAYS") * n("INVITE_EXTRA_PCT") / 100 + 0.5);
  assert.match(invites, new RegExp(`${extraDays} days free, up to ${n("EXTRA_CAP")} times in 12 months`));
  assert.doesNotMatch(invites, /25%|about a week/, "one way of saying it");
  const options = FAQ.find((f) => /options/i.test(f.q));
  assert.equal(options.q, "Can I backtest options?");
  assert.match(faqText(options), /^No\. /);
  assert.match(faqText(options), /paper trade options/);
  for (const [q, a] of FAQ.map((f) => [f.q, faqText(f)])) assert.doesNotMatch(q + a, /\bhonest/i);
});

test("the landing page: one tagline, sample labels, no old pricing variant, no verdict-as-a-call, no advice wording", () => {
  const login = read("src/pages/Login.tsx");
  const all = login + read("src/content/faq.ts") + read("src/content/seo.ts");
  assert.ok((all.match(/honest/gi) ?? []).length <= 1, "'honest' is a claim, not a fact: at most once");
  assert.doesNotMatch(login, /Likely a real edge/);
  assert.doesNotMatch(login, /Find out before your money does|Test your trading idea before/);
  assert.doesNotMatch(login + read("src/lib/offer.ts"), /Choose a plan after you sign in|dashed/);
  assert.doesNotMatch(login, /Ideas to test on|Buy NVDA when|Test an idea on NVDA/);
  assert.match(login, /rule template to test/i);
  assert.match(login, /not a suggestion/);
  assert.ok((login.match(/<span className="lp-sample">/g) ?? []).length >= 1, "the hero demo says it is a sample");
  assert.ok((login.match(/\{ILLUSTRATION\}/g) ?? []).length >= 2, "the Trade and Money pictures say they are made-up figures");
  assert.doesNotMatch(login, /aria-pressed/, "tabs use aria-selected");
  assert.match(login, /role="tab"/);
  assert.match(login, /tabIndex=\{k === i \? 0 : -1\}/);
  assert.doesNotMatch(login, /Start free|Sign up free/);
  assert.equal(seo.TAGLINE, "Test it, research it, track it.");
  assert.match(read("index.html"), /<title>StratLab: test it, research it, track it<\/title>/);
});

test("the Privacy page lists every AI provider the code can use, says what the browser keeps before sign-in, and no longer says 'such as'", () => {
  const page = read("src/pages/LegalPage.tsx");
  const catalog = backend("app/ai_catalog.py");
  const names = [...catalog.matchAll(/^\s+Provider\("([a-z0-9]+)", "([^"]+)"/gm)].map((m) => m[2]);
  assert.ok(names.length >= 12, `${names.length} providers read`);
  const privacy = page.slice(page.indexOf("function Privacy"), page.indexOf("function Refunds"));
  for (const name of names.map((n) => n.replace(/ \(.*\)$/, ""))) assert.ok(privacy.includes(name), `${name} is in the catalog but not in the policy`);
  assert.match(privacy, new RegExp(`any of these ${({ 13: "thirteen" })[names.length] ?? names.length}`));
  assert.doesNotMatch(privacy, /such as Groq/);
  assert.match(privacy, /ph_/);
  assert.match(privacy, /Before you sign in/);
  assert.match(privacy, /Do Not Track or Global Privacy Control/);
  assert.match(privacy, /random ID made in your browser, not to any account/);
  assert.doesNotMatch(privacy, /linked to your account's internal ID, never your email or name, and without/);
  assert.match(page, /<main id="main"/, "the policies sit in a main landmark");
});

test("Do Not Track and Global Privacy Control both switch analytics off", async () => {
  const { doNotTrack } = await import("../src/lib/analytics.ts");
  const set = (nav, win = {}) => { Object.defineProperty(globalThis, "navigator", { value: nav, configurable: true }); globalThis.window = win; };
  set({ doNotTrack: "1" });
  assert.equal(doNotTrack(), true);
  set({ doNotTrack: "yes" });
  assert.equal(doNotTrack(), true);
  set({ doNotTrack: "unspecified", globalPrivacyControl: true });
  assert.equal(doNotTrack(), true);
  set({}, { doNotTrack: "1" });
  assert.equal(doNotTrack(), true);
  set({ doNotTrack: "0" });
  assert.equal(doNotTrack(), false);
  set({});
  assert.equal(doNotTrack(), false);
  const src = read("src/lib/analytics.ts");
  assert.match(src, /if \(!cfg \|\| doNotTrack\(\)\) return Promise\.resolve\(null\)/, "the library isn't even downloaded");
  assert.match(src, /respect_dnt: true/);
});

test("the sample pages don't carry what the review found: the reload message, one h1 per landing, a fact for the verdict", () => {
  const guard = read("src/components/LoadGuard.tsx");
  assert.match(guard, /Couldn't load/);
  assert.match(guard, /Reload/);
  const css = read("src/styles.css");
  assert.match(css, /\.lp-demo-stack > \.lp-demo-body \{ grid-area: 1 \/ 1; \}/, "the three examples overlap, so the hero doesn't change height");
  assert.doesNotMatch(css.split("\n").find((l, i, all) => /@keyframes lp-in/.test(l) && all.slice(0, i).some((x) => /round 5/.test(x))), /opacity/, "the demo card is never dim");
  assert.doesNotMatch(css, /\.lp-hero \.lp-demo \{ display: none; \}/, "the demo shows on a phone");
  assert.match(css, /\.lp-menu > summary \{ min-height: 40px/);
});
