import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// site85 (Release 85): unit checks of the fixes the browser specs (e2e/site85.spec.ts) prove on the pages.
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE21B-001: a saved sign-in on an app page starts in the app's frame, never the landing's header and heading", () => {
  const boot = read("public/boot.js"), html = read("index.html"), entry = read("src/lib/entry.ts");
  // only a saved sign-in downloads the frame's code (public/early.js), and the pages anyone sees the same way keep their words: its list is
  // lib/entry.ts's (site85: moved out of boot.js, so a visitor's pages weigh what they did, review-r5's budgets)
  const app = read("public/early.js");
  assert.equal(app.match(/var FOR_ALL = (\[.*\]);/)[1], entry.match(/export const PUBLIC_FOR_ALL = (\[.*\]);/)[1]);
  assert.doesNotMatch(boot, /FOR_ALL|appFrame|data-boot-shell/);
  assert.match(boot, /setAttribute\("data-saved", "1"\); var e = document\.createElement\("script"\); e\.fetchPriority = "high"; e\.src = "\/early\.js";/);
  assert.match(app, /document\.documentElement\.setAttribute\("data-for-all", "1"\); return;/);
  // the landing's frame is taken out as it is parsed, and hidden until then
  assert.match(app, /new MutationObserver\(appFrame\)/);
  assert.match(html, /html\[data-saved\]:not\(\[data-for-all\]\) #root > \.boot-head, html\[data-saved\]:not\(\[data-for-all\]\) \[data-boot-head\], html\[data-saved\]:not\(\[data-for-all\]\) \[data-boot\]:not\(\.boot-shell\) \{ display: none; \}/);
  // the frame carries data-boot, so the start-up guard's slow and failed notices see it as "the app has not drawn yet"
  assert.match(app, /shell\.setAttribute\("data-boot", ""\);/);
  // the HTML frame and the app's own first frame (components/BootFrame.tsx) are the same: top bar with four held button places, the menu's
  // panel with the logo, the page column
  const frame = read("src/components/BootFrame.tsx");
  const classes = (s) => [...s.matchAll(/class(?:Name)?=\\?"([^"\\]+)\\?"/g)].map((m) => m[1]).filter((c) => !/^logo/.test(c));
  const seg = app.match(/shell\.className = "([^"]+)";[\s\S]*?var box = ('[^']*');[\s\S]*?shell\.innerHTML = ([\s\S]*?);\n/);
  const fromBoot = [seg[1], ...classes(new Function("box", `return ${seg[3]};`)(new Function(`return ${seg[2]};`)()))];
  const fromApp = classes(frame.slice(frame.indexOf("return (")));
  assert.deepEqual(fromBoot.slice(0, fromApp.length), fromApp);
  assert.deepEqual(fromApp, ["shell boot-shell", "topbar", "icon-btn", "brand", "row tight", "icon-btn", "icon-btn", "icon-btn", "sidebar", "side-top", "side-brand", "brand", "main", "page"]);
  // and the app draws it while the sign-in is read and the data status asked
  const main = read("src/main.tsx");
  assert.equal((main.match(/return <><BootFrame><h1 className="sr-only">Opening StratLab<\/h1><Opening label="Opening StratLab" \/><\/BootFrame><Tracking \/><\/>;/g) || []).length, 2);
});

/** boot.js run with a fake page: its listeners, the reloads it asks for, the files it asks past the cache. `drawn`: the app owns the root. */
function bootPage({ drawn = false } = {}) {
  const win = {}, doc = {};
  let reloads = 0, fetched = 0;
  const store = new Map();
  const root = { querySelector: (q) => (!drawn && /data-boot/.test(q) ? {} : null), textContent: "", appendChild() {} };
  if (drawn) root.__reactContainer$x = {};
  const el = () => ({ setAttribute() {}, appendChild() {}, addEventListener() {}, className: "", style: {} });
  const location = { reload: () => { reloads += 1; }, href: "https://stratlab.studio/", pathname: "/", search: "" };
  const sandbox = {
    window: { addEventListener: (t, f) => { win[t] = f; }, location },
    document: { getElementById: () => root, createElement: el, documentElement: { dataset: {}, hasAttribute: () => false, setAttribute() {} }, addEventListener: (t, f) => { doc[t] = f; } },
    sessionStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) },
    localStorage: { getItem: () => null, length: 0 }, setTimeout: () => 0, Date, Number, String, Object, location,
    fetch: () => { fetched += 1; return Promise.resolve(); },
  };
  new Function(...Object.keys(sandbox), read("public/boot.js"))(...Object.values(sandbox));
  const fail = (src = "https://stratlab.studio/assets/pwa-Dfgue3tQ.js") => win.error({ target: { tagName: "LINK", href: src } });
  return { win, doc, fail, get reloads() { return reloads; }, get fetched() { return fetched; } };
}
const tick = () => new Promise((ok) => setImmediate(ok));

test("LIVE21A-003: a file stopped by a navigation, or asked after the app drew, never reloads the page over the reader's click", async () => {
  // the start-up's own file failing while the page is still the start-up frame: asked past the cache, then one reload (as before)
  let p = bootPage();
  p.fail("https://stratlab.studio/assets/index-abc.js");
  await tick(); await tick();
  assert.equal(p.fetched, 1); assert.equal(p.reloads, 1);
  // the page being left (Safari stops its loads and calls each failed): nothing
  p = bootPage();
  p.win.beforeunload();
  p.fail(); await tick(); await tick();
  assert.equal(p.reloads, 0); assert.equal(p.fetched, 0);
  p = bootPage();
  p.win.pagehide({});
  p.win.unhandledrejection({ reason: new TypeError("Load failed") });
  assert.equal(p.reloads, 0);
  // back from the page cache: here again, and a real failure reloads
  p.win.pageshow({});
  p.win.unhandledrejection({ reason: new TypeError("Load failed") });
  assert.equal(p.reloads, 1);
  // a press on a link to another page, before either event (a phone's Safari)
  p = bootPage();
  const a = { hasAttribute: () => false, target: "", href: "https://stratlab.studio/themes" };
  p.doc.click({ defaultPrevented: false, target: { closest: () => a } });
  p.fail(); await tick(); await tick();
  assert.equal(p.reloads, 0);
  // ...but a place on this page (#faq) is not leaving
  p = bootPage();
  p.doc.click({ defaultPrevented: false, target: { closest: () => ({ ...a, href: "https://stratlab.studio/#faq" }) } });
  p.fail("https://stratlab.studio/assets/index-abc.js"); await tick(); await tick();
  assert.equal(p.reloads, 1);
  // the app has drawn: a late file (the install helper, a page's code) is the app's own to retry or do without
  p = bootPage({ drawn: true });
  p.fail(); await tick(); await tick();
  assert.equal(p.reloads, 0); assert.equal(p.fetched, 0);
});

test("LIVE21B-012: the tax report's sales are five columns, the long name wraps to two lines, and the check covers exactly the reviewer's case", () => {
  const tax = read("src/pages/TaxReportPage.tsx");
  const sales = tax.slice(tax.indexOf("const saleCols"), tax.indexOf("const lotCols"));
  assert.deepEqual([...sales.matchAll(/\{ key: "(\w+)"/g)].map((m) => m[1]), ["stock", "gain", "term", "sold", "sale"]);
  assert.match(sales, /\{ key: "stock", header: "Stock", rowHeader: true, wrap: true,/);
  assert.match(sales, /<span className="tax-name" title=\{name\(r\.key\)\}><b>\{name\(r\.key\)\}<\/b><\/span>/);
  assert.match(sales, /\{salesMore\.on && <span className="k-sub-line">bought \{dateOnly\(r\.bought\)\}<\/span>\}/);
  assert.match(sales, /<span className="k-sub-line">cost \{inr\(r\.cost\)\}<\/span>/);
  assert.match(read("src/styles.css"), /\.tax-name \{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; max-width: 16ch; white-space: normal; \}/);
  const align = read("e2e/site83-align.spec.ts");
  assert.match(align, /for \(const w of \[1000, 1280, 1600\]\) \{\n      await page\.setViewportSize\(\{ width: w, height: 900 \}\);\n      for \(const on of \[false, true\]\)/);
  assert.match(align, /PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN - GROWTH/);
  assert.match(read("e2e/ui-lint-world.ts"), /const fund = "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN - GROWTH";/);
});

test("LIVE21B-003: /mine lists the watchlist in its own order, and Coming up has as many rows as the watchlist shows", () => {
  const mine = read("src/pages/MineHome.tsx");
  // (changed on purpose, site86 SCROLL, owner 21 Nov: every stock, not the first six, scrolling inside the card)
  assert.match(mine, /return parts\.flat\(\)\.sort\(\(a, b\) => at\(a\) - at\(b\)\); \}\), \[\]\);/);
  assert.doesNotMatch(mine, /Math\.abs\(b\.q\.change_pct \?\? 0\) - Math\.abs\(a\.q\.change_pct \?\? 0\)/);
  // (replaced on purpose, site86: the cards are the same height and the longer list scrolls; no row count is shared between them)
  assert.doesNotMatch(mine, /comingShown|setWatchRows/);
  assert.match(mine, /coming: <ComingCard rows=\{coming\} \/>, watch: <WatchCard \/>,/);
});

test("owner, 20 Nov: the phone's billing choice reads \"Yearly\", the saving on each yearly card", () => {
  for (const f of ["src/pages/PlansPage.tsx", "src/pages/Login.tsx"]) assert.match(read(f), /\{ value: "year", label: YEARLY_LABEL, short: YEARLY_SHORT \}/, f);
  assert.match(read("src/lib/offer.ts"), /export const YEARLY_SHORT = "Yearly";/);
});

test("owner, 20 Nov: an IPO in BSE's list only says it is BSE's, never \"No NSE page yet\" with its lot and bids blank (Mahanadi Coalfields)", async () => {
  const page = read("src/pages/IposPage.tsx");
  assert.match(page, /export const bseOnly = \(r\?: Pick<IpoRow, "exchanges">\): boolean => !!r\?\.exchanges\?\.length && !r\.exchanges\.includes\("NSE"\);/);
  assert.match(page, /if \(tab === "upcoming"\) return "Not announced yet";\n  if \(bseOnly\(r\)\) return BSE_ONLY;/);
  assert.match(page, /bseOnly\(r\) \? BSE_ONLY : r\.page === false/);
  assert.match(page, /export const BSE_ONLY = "Listed on BSE: not published yet";/);
  // the lot BSE's list gives is kept on a row only BSE lists (backend/app/ipo.py)
  assert.match(read("../backend/app/ipo.py"), /"exchanges": \["BSE"\]/);
});
