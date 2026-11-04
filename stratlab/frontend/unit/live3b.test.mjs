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
