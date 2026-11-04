// LIVE3 (live review of production, Wed 4 Nov), the FIXB lane: sign-in, phone overlays, layout shift, result pages,
// tables. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

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
