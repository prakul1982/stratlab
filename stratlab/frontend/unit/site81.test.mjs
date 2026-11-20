import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// a .ts file's extensionless imports, as the build resolves them (as unit/site79.test.mjs)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

// site81 (Release 81): unit checks of the fixes the browser specs (e2e/site81.spec.ts) prove on the pages.
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE18B-003: /plans' start-up frame is the Plans page itself: the header, the heading, the switches' places and the three cards", async () => {
  const { pageFiles, PLAN_FRAME_LABEL } = await import("../scripts/seoPages.mjs");
  const files = Object.fromEntries(pageFiles(read("index.html")));
  for (const file of ["plans/index.html", "pricing/index.html"]) {
    const html = files[file];
    assert.match(html, /<header class="lp-nav" data-boot-head>/);
    assert.match(html, /<section id="pricing" class="lp-sec lp-sec-first boot-plans" data-boot aria-busy="true">/);
    assert.match(html, /<div class="lp-head"><h1 class="serif lp-h2">Plans and prices<\/h1><span class="lp-skel lp-skel-p lp-skel-p-one" data-boot-js><\/span><\/div>/);
    assert.match(html, /<div class="lp-period" data-boot-js><span class="lp-skel lp-skel-seg"><\/span><span class="lp-skel lp-skel-cur"><\/span><\/div>/);
    assert.equal(html.match(/class="lp-card lp-price[^"]*" data-plan="(free|basic|pro)"/g).length, 3);
    assert.match(html, /data-plan="pro"><div class="stack g2"><h2 class="h2">Pro<\/h2><span class="small muted">For active traders and heavy research<\/span>/);
    assert.match(html, /<button type="button" class="btn outline" disabled>Continue with Google to see plans<\/button><a class="btn outline email-way lp-plan-email" href="\/login\?plan=basic#email">/);
    assert.match(html, /<details class="lp-more lp-phone-fold"><summary>What Basic includes<\/summary>/);
    assert.match(html, /<ul class="lp-plan-list boot-wide"><li><span aria-hidden="true">✓<\/span>Everything in Basic<\/li>/);
    // with scripts off: the page's own words and the plain list of plans, the frame's cards hidden
    assert.match(html, /<p class="boot-text">StratLab has three plans/);
    assert.match(html, /<ul class="boot-links boot-text">\n<li><b>Free<\/b>/);
    // no plain start-up column: the boot block is replaced
    assert.doesNotMatch(html, /<div class="boot boot-wait/);
    assert.equal(html.match(/src="\/signin-early\.js"/g).length, 1);
  }
  // the frame's words are the app's while the prices are on their way (pages/Login.tsx landingAction with no offer read yet)
  const { landingAction } = await import("../src/lib/offer.ts");
  for (const p of ["free", "basic", "pro"]) assert.equal(PLAN_FRAME_LABEL[p], landingAction(null, p).label);
  const css = read("index.html");
  assert.match(css, /@media \(scripting: enabled\) \{ \.boot-plans \.boot-text, \.boot-plans ul\.boot-links\.boot-text \{ display: none; \} \}/);
  assert.match(css, /@media \(scripting: none\) \{ \.boot-plans \[data-boot-js\] \{ display: none; \} \}/);
  assert.match(css, /@media \(max-width: 640px\) \{ \.boot-plans \.boot-wide \{ display: none; \} \}/);
  assert.match(css, /@media \(min-width: 641px\) \{ \.boot-plans \.lp-phone-fold \{ display: none; \} \}/);
  assert.match(css, /html\[data-email-off\] \.boot-plans \.email-way \{ display: none; \}/);
});

test("LIVE18B-003: while the prices come the app holds the currency switch's place and draws no note placeholder", () => {
  const login = read("src/pages/Login.tsx");
  assert.match(login, /\{loading && <span className="lp-skel lp-skel-cur" \/>\}/);
  assert.match(login, /\{p !== "free" && !loading && \(gst \|\| save != null\) && \(/);
  assert.doesNotMatch(login, /lp-skel-note/);
  const css = read("src/styles.css");
  assert.match(css, /\.lp-skel-cur \{ height: 38px; width: 146px; max-width: 100%; \}/);
  assert.match(css, /\.lp-skel-cur \{ height: 50px; width: 119px; \}/);
  assert.match(css, /\.lp-period > :first-child \{ flex-basis: 100%; \}/);
  assert.match(css, /\.lp-skel-amount \{ height: calc\(44px \* 1\.05 \+ 2px \+ 13\.5px \* 1\.5\); width: 60%; \}/);
});

test("LIVE18B-008: the options page's offline note in the server's words, from the data note it has at the start", async () => {
  const src = read("src/pages/OptionsPage.tsx");
  assert.match(src, /api<\{ offline: string \| null; rows: Underlying\[\] \} \| Underlying\[\]>\("\/options\/underlyings\?offline=list"\)/);
  assert.doesNotMatch(src, /"\/options\/recorded"/);
  assert.match(src, /\(offline \?\? \(unds === null && dataOffline \? optionsOfflineLine\(dataNote\) : null\)\)/);
  const { optionsOfflineLine: fn } = await import("../src/lib/dataBack.ts");
  // the server's offline_when wording ("… on Fri 20 Nov at 08:00 IST.")
  assert.equal(fn({ back_at: "2026-11-20T08:00:00+05:30" }),
    "Option quotes come from the live feed, which is offline until the daily data login completes. Indian market data comes back with the daily data login, on Fri 20 Nov at 08:00 IST.");
  assert.equal(fn(null), "Option quotes come from the live feed, which is offline until the daily data login completes.");
});

test("LIVE18B-009: the scan page draws every ready-made scan at once", async () => {
  const { SCAN_LIST } = await import("../src/lib/scanList.ts");
  assert.equal(SCAN_LIST.length, 8);
  assert.deepEqual(SCAN_LIST.map((s) => s.id), ["st_s2", "high52", "golden_cross", "rsi_bounce", "volume_surge", "bb_squeeze", "near_low52", "pullback"]);
  assert.ok(SCAN_LIST.every((s) => s.text && s.rules.length));
  assert.match(read("src/pages/ResearchScans.tsx"), /const scans = \[\.\.\.\(sets\?\.scans\?\.length \? sets\.scans : FIRST_SCANS\), CUSTOM_SCAN\];/);
});

test("LIVE18B-010: while the app or the page is opening it counts as a call out, so the analytics question waits", () => {
  const src = read("src/main.tsx");
  assert.match(src, /function HoldAsk\(\) \{\n  useEffect\(\(\) => \{ callStarted\(\); return callEnded; \}, \[\]\);/);
  // every "Opening…" the app's shell draws is this one (the spinner and the hold)
  assert.match(src, /import \{ LoadFailed, LoadGuard, Opening as OpeningSpinner, PageBoundary \} from "\.\/components\/LoadGuard";/);
  assert.match(src, /function Opening\(p: \{ label\?: string \}\) \{\n  return <><OpeningSpinner \{\.\.\.p\} \/><HoldAsk \/><\/>;/);
  assert.match(read("src/components/Tracking.tsx"), /if \(callsInFlight\(\) > 0\) return;/);
});

test("LIVE18B-002 / LIVE18A-011: a saved sign-in's early reads, from a file of their own the visitor never downloads", () => {
  const boot = read("public/boot.js");
  assert.match(boot, /document\.documentElement\.setAttribute\("data-saved", "1"\); document\.head\.appendChild\(document\.createElement\("script"\)\)\.src = "\/early\.js"; break; \}/);
  assert.match(boot, /earlyMe\(v\); if \(window\.__stratlabEarlyGo\) window\.__stratlabEarlyGo\(v\);/);
  const src = read("public/early.js");
  const run = (path, token = { access_token: "tok", expires_at: Math.floor(Date.now() / 1000) + 3600 }, cfgFirst = true) => {
    const calls = [];
    const store = new Map([["sb-demo-auth-token", JSON.stringify(token)]]);
    const cfg = { API_BASE: "https://api.example", SUPABASE_URL: "https://demo.supabase.co" };
    const win = cfgFirst ? { STRATLAB_CONFIG: cfg } : {};
    const doc = { head: { appendChild: (l) => calls.push(["link", l.rel, l.href]) }, createElement: () => ({}) };
    new Function("window", "document", "localStorage", "fetch", "location", src)(win, doc, { getItem: (k) => store.get(k) ?? null },
      (url) => { calls.push(["fetch", url.replace("https://api.example", "")]); return Promise.resolve({}); }, { pathname: path });
    if (!cfgFirst) win.__stratlabEarlyGo(cfg);                    // /config.js ran after: boot.js's hook calls it
    return { calls, win };
  };
  const trade = run("/trade");
  assert.deepEqual(trade.calls.filter((c) => c[0] === "fetch").map((c) => c[1]),
    ["/public/data-online", "/notebooks", "/markets", "/trade/vix?brief=true", "/trade/positioning?brief=true&pcr=false"]);
  assert.deepEqual(Object.keys(trade.win.__stratlabEarlyReads), ["/notebooks", "/markets", "/trade/vix?brief=true", "/trade/positioning?brief=true&pcr=false"]);
  assert.ok(trade.win.__stratlabEarlyPublic["/public/data-online"]);
  assert.deepEqual(trade.calls.find((c) => c[0] === "link"), ["link", "preconnect", "https://demo.supabase.co"]);
  assert.deepEqual(run("/trade", undefined, false).calls.filter((c) => c[0] === "fetch").length, 5);
  // a sign-in past its end (the first visit of a day): no read with its token, the data status still
  assert.deepEqual(run("/mine", { access_token: "old", expires_at: Math.floor(Date.now() / 1000) - 3600 }).calls.filter((c) => c[0] === "fetch").map((c) => c[1]), ["/public/data-online"]);
  // a public page asks nothing of the account's
  assert.deepEqual(run("/library").calls.filter((c) => c[0] === "fetch").map((c) => c[1]), ["/public/data-online"]);
  // the app takes them once, with the same token
  const api = read("src/lib/api.ts");
  assert.match(api, /const e = path === "\/me" \? w\.__stratlabEarlyMe : w\.__stratlabEarlyReads\?\.\[path\];/);
  assert.match(api, /export function bootPublic<T>\(path: string\): Promise<T> \| null \{/);
  assert.match(read("src/lib/app.tsx"), /\(bootPublic<\{ data_online: boolean; data_note\?: DataNote \}>\("\/public\/data-online"\) \?\? publicGet</);
  assert.doesNotMatch(read("src/lib/http.ts"), /__stratlabEarlyPublic/);                // the visitor's code is unchanged
});

test("LIVE18B-004: the tax report's switch on its own row takes the card's width on a phone", () => {
  assert.match(read("src/styles.css"), /\.tax-controls > \.k-card-head:has\(> \.k-sec\) > \.k-card-actions \{ margin-right: -76px; max-width: none; \}/);
});

test("LIVE18B-007: Pro's AI builds line names its cap, not 'unlimited' beside it", () => {
  const src = read("src/components/IdeaComposer.tsx");
  assert.match(src, /u\.ai_builds_per_day \? `Up to \$\{u\.ai_builds_per_day\} AI builds a day` : "Unlimited AI builds"/);
  assert.doesNotMatch(src, /Unlimited AI builds\$\{/);
});

test("LIVE18B-012: the menu shows the open page's item, scrolling only its own box", () => {
  const src = read("src/components/Shell.tsx");
  // updated on purpose (Release 81 CI): the reveal looks again when the menu's box changes size for a few seconds, and stops once
  // anything else moves the menu
  assert.match(src, /const cur = box\.querySelector<HTMLElement>\('\[aria-current="page"\]'\);\n      if \(cur\) revealIn\(box, cur\);/);
  assert.match(src, /const onScroll = \(\) => \{ if \(Math\.abs\(box\.scrollTop - mine\) > 1\) moved = true; \};/);
  assert.match(src, /const stopSize = watchSize\(box, again\);/);
  const body = src.match(/export function revealIn[\s\S]*?\n}/)[0]
    .replace("export function revealIn(box: HTMLElement, item: HTMLElement, room = 24): void", "function revealIn(box, item, room = 24)");
  const revealIn = new Function(`${body}; return revealIn;`)();
  const box = { scrollTop: 0, scrollHeight: 1200, clientHeight: 500, getBoundingClientRect: () => ({ top: 100, bottom: 600 }) };
  revealIn(box, { getBoundingClientRect: () => ({ top: 820, bottom: 860, height: 40 }) });
  assert.equal(box.scrollTop, 284);                                // its bottom 24px above the box's
  const shown = { ...box, scrollTop: 50 };
  revealIn(shown, { getBoundingClientRect: () => ({ top: 300, bottom: 340, height: 40 }) });
  assert.equal(shown.scrollTop, 50);                               // already in view: not moved
});

test("LIVE18B-014: the closing auction says closed once", async () => {
  const { PHASE_TEXT } = await import("../src/lib/closingAuction.ts");
  assert.match(PHASE_TEXT.preopen, /closed/i);                    // said once, here (R2A-006)
  const page = read("src/pages/trade/ClosingAuctionPage.tsx");
  assert.match(page, /v\.phase === "preopen" \? "Before the open" : v\.phase === "holiday" \? "Not a trading day"/);
  assert.doesNotMatch(page, /"Market closed"|Closed, next/);
  assert.match(page, /data-testid="cas-next">Next auction window:/);
  assert.match(page, /data-testid="cas-next">Next auction window:/);
});

test("LIVE18A-020: 'What moved' lists the most points added, then the most taken", async () => {
  const { moverRows } = await import("../src/lib/pulseMood.ts");
  const rows = moverRows({ index: "S&P 500", of: 100, note: "", adding: [],
    taking: [{ symbol: "AMD", change_pct: -7.7, points: -6.9 }, { symbol: "MSFT", change_pct: -2, points: -9.1 }, { symbol: "GOOGL", change_pct: -3.5, points: -13.4 }] });
  assert.deepEqual(rows.map((r) => r.symbol), ["GOOGL", "MSFT", "AMD"]);
});

test("LIVE18A-021: an offline Indian market in the markets list says when it opens", () => {
  const src = read("src/components/SideMenus.tsx");
  assert.match(src, /return \{ st, text: `\$\{h\.open \? "Open" : `Opens in \$\{inWords\(left\)\}`\} · data offline` \};/);
});
