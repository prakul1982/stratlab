// The REVIEW lane (Wed 4 Nov): Instinct's UI items (the tour's address, dialogs over every layer, Market Watch's corner panel
// clear of the page's buttons) and the review rounds' fixes. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("/tour is the app's address for the tour: routed, sent to the app by the site and the offline worker, named for a visitor", async () => {
  const { isAppPath, describePath } = await import("../src/lib/deepLinks.ts");
  assert.ok(isAppPath("/tour"));
  assert.equal(describePath("/tour").what, "the tour");
  assert.match(read("src/main.tsx"), /<Route path="\/tour" element=\{<TourRoute \/>\} \/>/);
  assert.match(read("src/main.tsx"), /nav\("\/", \{ replace: true \}\)[\s\S]{0,200}openTour/);
  const v = JSON.parse(read("vercel.json"));
  const app = v.rewrites.find((r) => r.destination === "/index.html");
  assert.ok(new RegExp(`^${app.source}$`).test("/tour"));
  // the app's pages: never kept stale, and not for search engines
  const pages = v.headers.filter((x) => x.source.includes("|help|"));
  assert.equal(pages.length, 2);
  for (const h of pages)
    assert.ok(new RegExp(`^${h.source}$`).test("/tour"), h.source.slice(0, 30));
  assert.match(read("public/sw.js"), /\|tour\|/);
});

test("Instinct #11: a dialog is drawn at the end of the page and above Market Watch's panel and the cookie question", () => {
  const d = read("src/components/kit/Dialog.tsx");
  assert.match(d, /return createPortal\(\s*<div className="modal-back"/);
  assert.match(d, /<\/div>,\s*document\.body,\s*\);/);
  const css = read("src/styles.css");
  const z = (sel) => Number(css.match(new RegExp(`\\n${sel.replace(".", "\\.")} \\{[^}]*z-index: (\\d+)`))[1]);
  const mw = Number(read("src/components/watch/watch.css").match(/\.mw \{[^}]*z-index: (\d+)/)[1]);
  assert.ok(z(".modal-back") > mw && z(".modal-back") > z(".consent") && z(".modal-back") < z(".toast"));
});

test("Instinct #11: a docked panel floating on a laptop is at most half the window high, and the page's end clears it", async () => {
  const { drawnHeight, cornerCover, DEFAULT_LAYOUT, MIN_H } = await import("../src/lib/watchLayout.ts");
  const open = { ...DEFAULT_LAYOUT, open: true };
  assert.equal(drawnHeight(open, 1280, 720), 360);
  assert.equal(drawnHeight(open, 1280, 560), MIN_H);
  assert.equal(drawnHeight(open, 1700, 720), 560);                                // docked: the window's height, as before
  assert.equal(drawnHeight({ ...open, mode: "float", x: 10, y: 10 }, 1280, 720), 560);   // floated on purpose: the person's own height
  assert.equal(cornerCover(open, 1280, 720), 376);
  assert.equal(cornerCover({ ...open, open: false }, 1280, 720), 0);
  assert.equal(cornerCover(open, 1700, 720), 0);
  assert.equal(cornerCover(open, 390, 800), 0);                                   // a phone's sheet
  assert.equal(cornerCover({ ...open, mode: "float", x: 10, y: 10 }, 1280, 720), 0);   // moved off the corner
  assert.match(read("src/components/watch/launcher.css"), /body\.mw-cover \.shell > \.main \{ padding-bottom: calc\(var\(--mw-cover, 0px\) \+ 24px\); \}/);
});

test("Instinct (2 Nov): the execution model as the engine has it, in Help and on the test's result", async () => {
  const { HELP, testFills } = await import("../src/lib/help.ts");
  const { HELP_TOPICS } = await import("../src/lib/helpTopics.ts");
  assert.equal(HELP.fills, testFills());
  assert.match(testFills(), /fills at the next candle's open, 0\.05% worse for slippage \(buys that much higher, sells that much lower\)/);
  assert.match(testFills(0.1, true), /0\.1% worse[\s\S]*gapped past it[\s\S]*the stop counts[\s\S]*square-off/);
  assert.match(testFills(0), /no slippage/);
  const t = HELP_TOPICS.find((x) => x.key === "fills");
  assert.equal(t.group, "Rules, costs and risk");
  // the engine says the same: next open for a backtest, the stop at the open on a gap, sells lower
  const core = read("../backend/app/engine/core.py");
  assert.match(core, /self\.next_open = True/);
  assert.match(core, /px = min\(b\["o"\], self\.sl\) if long else max\(b\["o"\], self\.sl\)/);
  assert.match(core, /fill = px \* \(1 - self\.r\.slippage \/ 100 \* d\)/);
  const exp = read("src/pages/ExperimentPage.tsx");
  assert.match(exp, /data-testid="trades-fills">\{testFills\(e\.strategy\.risk\.slippage, intraday\)\}/);
  assert.doesNotMatch(exp, /a rule's order fills at the candle's close/);
  // paper trading and the SIP test say their own (true) rules: the closed candle's close, the day's close
  assert.match(read("src/lib/paperText.ts"), /Orders fill at the close of the candle your rules act on/);
  assert.match(read("../backend/app/sip_test.py"), /Each instalment is invested at that day's close/);
});

// ---------- the classes, swept (owner, 4 Nov: "all fixes should fix things globally, not for a specific set of examples") ----------
import { readdirSync, statSync } from "node:fs";
const walk = (d) => readdirSync(new URL(`../${d}`, import.meta.url)).flatMap((n) => {
  const p = `${d}/${n}`;
  return statSync(new URL(`../${p}`, import.meta.url)).isDirectory() ? walk(p) : /\.(tsx?|css)$/.test(n) ? [p] : [];
});
const SRC = walk("src");

test("Instinct #11 as a class: every dialog is the kit's (drawn at the end of the page), and nothing that floats is above it but the toast and the tour", () => {
  // the dimmed page is drawn only by the kit's Dialog (portalled) and the search palette (the Shell's own, outside every container)
  assert.deepEqual(SRC.filter((f) => /className="modal-back/.test(read(f))).sort(), ["src/components/SearchPalette.tsx", "src/components/kit/Dialog.tsx"]);
  // a modal of its own (aria-modal true) is only one of the known full-window layers, never a page's own dialog box
  const own = SRC.filter((f) => /aria-modal"?[=:]\s*("true"|true|\{true\})/.test(read(f))).sort();
  assert.deepEqual(own, ["src/components/SearchPalette.tsx", "src/components/Shell.tsx", "src/components/kit/Coachmark.tsx", "src/components/kit/Dialog.tsx",
    "src/components/watch/PublicBoard.tsx", "src/components/watch/WatchPanel.tsx"]);
  // every fixed layer's z-index in every stylesheet is under the dialog's, except the toast and the tour's note (70)
  const css = SRC.filter((f) => f.endsWith(".css")).map((f) => [f, read(f)]);
  const dialogZ = Number(read("src/styles.css").match(/\.modal-back \{[^}]*z-index: (\d+)/)[1]);
  for (const [f, text] of css) for (const m of text.matchAll(/([^{}\n]+)\{[^}]*position: fixed;[^}]*z-index: (\d+)/g)) {
    const sel = m[1].trim(), z = Number(m[2]);
    // the skip link shows only while it has focus, which a dialog keeps inside itself
    if (/\.modal-back|\.toast|\.k-coach\b|\.skip-link/.test(sel)) continue;
    assert.ok(z < dialogZ, `${f}: ${sel} (z ${z}) would sit over a dialog (z ${dialogZ})`);
  }
});

test("Fill rules as a class: only paper trading and chart replay say an order fills at a candle's close; a backtest says next open", () => {
  const CLOSE = /fills? at (the|that|a) (candle's )?close|filled at the close|fill at the last close|fills? at the close of the candle/i;
  const says = SRC.filter((f) => !f.endsWith(".css") && CLOSE.test(read(f).replace(/A time exit fills at the candle's close/g, ""))).sort();
  assert.deepEqual(says, ["src/components/OrderList.tsx", "src/lib/paperText.ts", "src/lib/replay.ts", "src/pages/trade/ReplayPage.tsx"]);
});

test("Table sweep as a rule: no page lays figures out as label/value pairs (k-rows) but the Account page's plan block (the owner's own layout, VR6/VR7)", () => {
  assert.deepEqual(SRC.filter((f) => f.endsWith(".tsx") && /className=(\{`|")k-rows/.test(read(f))).sort(), ["src/pages/AccountPage.tsx"]);
});

test("/tour as a class: every app address is sent to the app by the site, kept fresh and out of search engines (the public ones aside)", async () => {
  const { APP_ROUTES } = await import("../src/lib/deepLinks.ts");
  const v = JSON.parse(read("vercel.json"));
  const rw = new RegExp(`^${v.rewrites.find((r) => r.destination === "/index.html").source}$`);
  const [fresh, noindex] = v.headers.filter((x) => x.source.includes("|help|")).map((h) => new RegExp(`^${h.source}$`));
  // public: the landing page and its sections, the library (served by its own page), and the plans/help a visitor reads
  // (R15: and the ad landing, /start, which names "/" as its canonical address)
  const PUBLIC = new Set(["/", "/library", "/plans", "/pricing", "/faq", "/start"]);
  for (const r of APP_ROUTES) {
    const p = r.replace(/:[a-z]+/gi, "x").replace(/\/\*$/, "/x");
    if (r === "/" || r === "/library") continue;
    assert.ok(rw.test(p), `${r}: not sent to the app`);
    assert.ok(fresh.test(p), `${r}: could be served stale`);
    if (!PUBLIC.has(r)) assert.ok(noindex.test(p), `${r}: open to search engines`);
  }
});

test("Instinct #3 as a class: every file the app saves goes through the one save helper (one address a click, kept a minute, an empty file an error)", () => {
  // the only blob address made outside lib/share.ts is the invoice, opened in a tab rather than saved
  assert.deepEqual(SRC.filter((f) => /URL\.createObjectURL/.test(read(f))).sort(), ["src/components/InvoicesCard.tsx", "src/lib/share.ts"]);
  for (const f of ["src/pages/DeepDive.tsx", "src/pages/NewsPage.tsx", "src/pages/NotebookPage.tsx", "src/pages/ExperimentPage.tsx", "src/pages/OptionsPage.tsx",
    "src/charts/price/PriceChart.tsx", "src/components/shareImage.ts", "src/pages/admin/AuditPanel.tsx", "src/pages/admin/InvoiceAdminPanel.tsx", "src/pages/admin/SystemSection.tsx"])
    assert.match(read(f), /import \{[^}]*\bdownload(Csv)?\b[^}]*\} from "[./]+lib\/(share|csvDownload)"/, f);      // downloadCsv: the CSV builder in front of the same save (EXPORT)
  // ...and that builder saves through share's one download (kept out of share itself, which the landing page loads)
  assert.match(read("src/lib/csvDownload.ts"), /import \{ download \} from "\.\/share";/);
});

test("LIVE1B-085: a page's later cards start once the first screen's calls are back, not after the whole fixed pause", async () => {
  const { afterPaint, QUIET_MS } = await import("../src/lib/defer.ts");
  const { callStarted, callEnded, callsInFlight } = await import("../src/lib/inflight.ts");
  const ran = [];
  callStarted(); callStarted();                                    // the first screen's two calls are out
  const t0 = Date.now();
  afterPaint(() => ran.push(Date.now() - t0), 2000);                 // no requestAnimationFrame in node: it starts at once
  await new Promise((r) => setTimeout(r, 150));
  assert.deepEqual(ran, []);                                         // still waiting: a call is out
  callEnded(); callEnded();
  assert.equal(callsInFlight(), 0);
  await new Promise((r) => setTimeout(r, QUIET_MS + 80));
  assert.equal(ran.length, 1);
  assert.ok(ran[0] < 600, `ran after ${ran[0]} ms`);                 // well before the 2 s cap
  // every call is counted: api() goes through the counter
  assert.match(read("src/lib/api.ts"), /callStarted\(\);\n  return send<T>\(path, opts\)\.finally\(callEnded\);/);
});
