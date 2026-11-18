// R61 (owner, 17 Nov, on Release 60): the share above the 50-day average is coloured on the Breadth page as on the Invest home's card
// (R15 #12: green above half, red below); the 20- and 200-day shares stay plain (fix9, LIVE9A-016). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { partTone, shareTone, measureRows, liveRows } = await import("../src/lib/breadthTable.ts");

test("the Breadth page colours the share above the 50-day average by the home card's rule, and only that share", () => {
  assert.equal(partTone({ tone: "half" }, 75), "k-up");
  assert.equal(partTone({ tone: "half" }, 33.2), "k-down");
  assert.equal(partTone({ tone: "half" }, 50), undefined);
  assert.equal(partTone({ tone: "half" }, null), undefined);
  for (const v of [12, 49.9, 50.1, 88]) assert.equal(partTone({ tone: "half" }, v), shareTone(v));   // the home card's own function
  const fig = (value) => ({ value, prev: value, change: 0 });
  const t = { day: "2026-11-16", prev_day: "2026-11-13", adv: fig(300), dec: fig(200), unch: fig(5), stocks: fig(505), pct20: fig(40), pct50: fig(61), pct200: fig(30),
    highs: fig(10), lows: fig(4), up4: fig(3), down4: fig(2), ad_ratio: fig(1.5), mcclellan: fig(10), summation: fig(100), trin: fig(1), stage2: fig(20) };
  const tones = (rows) => Object.fromEntries(rows.filter((r) => /^p\d+$/.test(r.key)).map((r) => [r.key, r.parts[0].tone]));
  assert.deepEqual(tones(measureRows(t, null)), { p20: "share", p50: "half", p200: "share" });
  const live = liveRows({ adv: 300, dec: 200, pct20: 40, pct50: 61, pct200: 30, idx: null }, t, "NIFTY 500", null, false);
  assert.deepEqual(tones(live), { p20: "share", p50: "half", p200: "share" });
});

import { readFileSync } from "node:fs";
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R61: every visitor's Continue with Google has the email way beside it, drawn only while email sign-in is on", () => {
  const way = read("src/components/EmailWay.tsx");
  assert.match(way, /if \(!emailSignInOn\(\)\) return null;/);
  assert.match(way, /<a className=\{`btn outline\$\{small \? " sm" : ""\} email-way/);    // R64: a real button, never a text line
  // (updated on purpose, LIVE12B-024: a plan card names its plan; "Sign in with email" stays the words everywhere else)
  assert.match(way, /<Mail \/>\{label\}/);
  assert.match(way, /label = "Sign in with email"/);
  assert.match(read("src/lib/signin.ts"), /export const EMAIL_SIGNIN_PATH = "\/login#email";/);
  const login = read("src/pages/Login.tsx");
  assert.ok((login.match(/<EmailWay\b/g) ?? []).length >= 4, "hero, closing call, plan cards and the rule template");
  // (updated on purpose, R64 owner: "make it proper": the hero's email way is a full-size button in the row beside Google)
  assert.match(login, /\{cta\(\)\}\n\s*\{\/\*[^\n]*\*\/\}\n\s*\{!login && <EmailWay className="lp-cta-2" \/>\}/);
  assert.match(read("src/pages/AdLanding.tsx"), /<EmailWay next=\{null\} className="lp-cta-2" \/>/);
  assert.match(read("src/pages/PublicLibrary.tsx"), /small && emailSignInOn\(\) \? <button type="button" className="btn sm" onClick=\{\(\) => void startSignIn\("\/library"\)\}>Sign in<\/button>/);
  // the sign-in page opened at #email puts the cursor in the address box
  assert.match(read("src/components/EmailSignIn.tsx"), /if \(location\.hash !== "#email" \|\| !box\.current\) return;/);
});
