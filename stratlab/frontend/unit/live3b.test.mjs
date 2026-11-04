// LIVE3 (live review of production, Wed 4 Nov), the FIXB lane: sign-in, phone overlays, layout shift, result pages,
// tables. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";

// extensionless imports inside the app's modules resolve to their .ts files
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const { hasSignInCode, withoutSignInCode, wantsAccount } = await import("../src/lib/entry.ts");
const { signInProblem, UNFINISHED_SIGNIN } = await import("../src/lib/signinError.ts");

test("a sign-in code is taken out of every address, whatever page it came back to, keeping the rest (LIVE3-009)", () => {
  for (const path of ["/", "/mine", "/research/IN/HAL", "/account", "/holdings"]) {
    const href = `https://stratlab.studio${path}?code=abc-123&state=x&ref=friend#plans`;
    assert.equal(hasSignInCode(new URL(href).search), true);
    assert.equal(withoutSignInCode(href), `${path}?ref=friend#plans`);
    assert.equal(withoutSignInCode(`https://stratlab.studio${path}?code=abc`), path);
    // the app still loads for it (the library tries the code first)
    assert.equal(wantsAccount({ search: "?code=abc", hash: "", storage: null }), true);
  }
  assert.equal(hasSignInCode("?ref=x"), false);
});

test("an unfinished sign-in is said in words on the landing page and on every sign-in wall, and cleared on retry (LIVE3-009)", () => {
  assert.equal(signInProblem("", "", true), UNFINISHED_SIGNIN);
  assert.equal(signInProblem("", "", false), null);
  // a Google error in the address still says its own thing
  assert.match(signInProblem("?error=access_denied", "", true), /cancelled/);
  assert.match(UNFINISHED_SIGNIN, /Continue with Google to try again/);
  const app = read("src/lib/app.tsx");
  assert.match(app, /if \(hasSignInCode\(location\.search\)\) history\.replaceState\(history\.state, "", withoutSignInCode\(location\.href\)\)/);
  assert.match(app, /if \(!data\.session\) noteSignInUnfinished\(\)/);
  assert.match(read("src/pages/Login.tsx"), /signInProblem\(location\.search, location\.hash, signInUnfinished\(\)\)/);
  assert.match(read("src/pages/Gate.tsx"), /unfinished \? "That sign-in didn't finish"/);
  // starting sign-in again or signing in clears it (clearSignInEnded is called by both)
  assert.match(read("src/lib/signin.ts"), /clearSignInEnded = \(\): void => \{ try \{ sessionStorage\.removeItem\(ENDED\); sessionStorage\.removeItem\(UNFINISHED\);/);
});

test("the phone's slim consent bar asks the same question in one sentence, naming only what is on (LIVE3-010)", async () => {
  const A = await import("../src/lib/ads.ts");
  const w = A.consentWords(A.adsConfig({}));
  assert.equal(w.short, "Analytics: with your OK, StratLab uses Meta's ad measurement and Microsoft Clarity, which set cookies.");
  assert.doesNotMatch(A.consentWords(A.adsConfig({}, { META_PIXEL_ID: "" })).short, /Meta/);
  const css = read("src/styles.css");
  assert.match(css, /\.consent-title, \.consent-long \{ display: none; \}/);
  assert.match(css, /\.consent-short, \.consent-more \{ display: none; \}/);
});

test("the tour's hold on the phone menu survives the move to Home and a listener that starts late (LIVE3-014)", async () => {
  const events = [];
  globalThis.window = { dispatchEvent: (e) => events.push(e.detail.open) };
  globalThis.CustomEvent = class { constructor(type, o) { this.type = type; this.detail = o.detail; } };
  const T = await import("../src/lib/tourMenu.ts");
  assert.equal(T.tourMenuHeld(), false);
  T.holdTourMenu(true);
  assert.equal(T.tourMenuHeld(), true);
  T.holdTourMenu(false);
  assert.deepEqual(events, [true, false]);
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /useEffect\(\(\) => \{ if \(!tourMenuHeld\(\)\) setOpen\(false\); \}, \[loc\.pathname\]\);/);
  assert.match(shell, /if \(tourMenuHeld\(\)\) \{ setTourMenu\(true\); setOpen\(true\); \}/);
  delete globalThis.window; delete globalThis.CustomEvent;
});

test("Pulse's opening line is two short sentences, the same whatever the AI read says (LIVE3-016)", async () => {
  const { pulseLede } = await import("../src/lib/researchFormat.ts");
  for (const line of [pulseLede(null), pulseLede("4 Nov"), pulseLede("4 Nov", true)]) {
    assert.equal(line.split(". ").length, 2, line);
    assert.ok(line.length < 140, line);
  }
  // a signed figure isn't read "Up +0.63%" as well
  assert.match(read("src/components/kit/Stat.tsx"), /!\(dir !== "flat" && \/\^\\s\*\[\+\\u2212-\]\/\.test\(textOf\(children\)\)\)/);
});

test("loading placeholders hold the page still: the library is wide from its first frame, page lists hold the screen (LIVE3-012)", () => {
  const css = read("src/styles.css");
  assert.doesNotMatch(css, /:has\(\.lib-cards\)/, "the width doesn't wait for the cards");
  assert.match(css, /\.pub:has\(\.pub-main\.lib\) \{ --pub-w: 1144px; \}/);
  assert.match(css, /\.k-skel-box\.k-skel-page \{ min-height: 100vh; \}/);
  assert.match(css, /transition: transform \.2s ease, width \.2s ease, height \.2s ease;/);
  assert.match(read("src/pages/PublicLibrary.tsx"), /<PublicFrame className="lib"/);
  for (const f of ["src/pages/PublicLibrary.tsx", "src/pages/LibraryPage.tsx"]) assert.match(read(f), /<Skeleton label="Opening the library" page \/>/);
  assert.match(read("src/pages/Screens.tsx"), /!meta \? \(showFilters \? <div className="screens-filters-wait">/);
  assert.match(read("src/components/kit/PageHeader.tsx"), /asOfPending && <span className="k-meta-wait" aria-hidden="true">/);
});

test("one rule for both 'Coming up' cards: holidays, India's data, the US's own on the US tab, each index's next weekly expiry (LIVE3-015)", async () => {
  const { comingMarketEvents } = await import("../src/lib/eventTime.ts");
  const ev = (id, kind, date, title) => ({ id, kind, date, time: null, title, detail: "", figure: null, previous: null, url: null, status: "scheduled" });
  const events = [ev("a", "expiry", "2026-11-05", "SENSEX weekly expiry"), ev("b", "us", "2026-11-06", "US jobs report"), ev("c", "india", "2026-11-08", "Muhurat trading session"),
    ev("d", "expiry", "2026-11-09", "NIFTY weekly expiry"), ev("e", "holiday", "2026-11-10", "Exchange holiday"), ev("f", "expiry", "2026-11-12", "SENSEX weekly expiry"),
    ev("g", "us", "2026-11-10", "US consumer prices (CPI)"), ev("h", "expiry", "2026-11-25", "NIFTY monthly expiry")];
  const o = { today: "2026-11-04", nowHm: "19:00", end: "2026-12-04", weekEnd: "2026-11-11" };
  const ids = comingMarketEvents(events, o).map((e) => e.id);
  assert.deepEqual(ids, ["a", "b", "c", "d", "e", "g"], "both weeklies (NIFTY's too), the holiday and the US's data; no second SENSEX weekly, no monthly");
  assert.deepEqual(comingMarketEvents(events, { ...o, region: "US" }).map((e) => e.id), ["b", "g"]);
  assert.match(read("src/lib/mine.ts"), /comingMarketEvents\(ev\.events, \{ today, nowHm: istHm\(\), end, weekEnd: addDaysIso\(today, 7\) \}\)/);
});

test("a note column only some rows fill goes under the items, on every screen (LIVE3-015, LIVE3-021)", async () => {
  const src = read("src/components/kit/DataTable.tsx");
  assert.match(src, /export const sparseNotes = \(withNote: number, rows: number\): boolean => withNote \* 2 <= rows;/);
  assert.match(read("src/components/kit/FigureTable.tsx"), /const under = withNote && \(phone \|\| sparseNotes\(rows\.filter\(noted\)\.length, rows\.length\)\);/);
  assert.match(read("src/components/kit/FactTable.tsx"), /const under = notes && \(\(noteUnder && phone\) \|\| sparseNotes\(/);
  // the watchlist is a table, not tiles
  assert.match(read("src/pages/SpaceHomes.tsx"), /<WatchTable region=\{r\}/);
  assert.doesNotMatch(read("src/components/Research.tsx"), /inv-tile/);
});

test("an empty state's second way to start is a quiet button beside the first, not a link in the sentence (LIVE3-022)", () => {
  assert.match(read("src/components/kit/States.tsx"), /\{action && also \? <div className="k-row k-state-acts"><Action a=\{action\} \/><Action a=\{also\} quiet \/><\/div>/);
  const paper = read("src/pages/PaperPage.tsx");
  assert.match(paper, /action=\{\{ label: "Go to your notebooks", to: "\/notebooks" \}\} also=\{\{ label: "Build an options strategy", to: "\/options" \}\}/);
  // no empty state in the app keeps a starting route as a link inside its sentence while it has a button
  const fs2 = fs.readdirSync(new URL("../src/pages", import.meta.url), { recursive: true }).filter((f) => f.endsWith(".tsx"));
  for (const f of fs2) {
    const src = read(`src/pages/${f}`);
    for (const m of src.matchAll(/<EmptyState [^>]*action=\{\{[^}]*\}\}[^>]*>([^]*?)<\/EmptyState>/g))
      assert.doesNotMatch(m[1], /<Link className="link" to="\/(options|notebooks|research\/watchlist)"/, `${f}: ${m[1].slice(0, 80)}`);
  }
});
