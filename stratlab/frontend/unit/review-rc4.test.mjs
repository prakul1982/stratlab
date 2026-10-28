// RC-4 (28 Oct 2026): consent — a yes given on a page the server draws is for Google ads alone. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const A = await import("../src/lib/ads.ts");

const PIXEL = A.adsConfig({ VITE_META_PIXEL_ID: "1234567890", VITE_CLARITY_ID: "abc123def4", VITE_ADSENSE_CLIENT: "ca-pub-1234567890123456", VITE_ADSENSE_SLOT_PUBLIC: "1111111111", VITE_ADS_ENABLED: "true" });
const NOW = Date.UTC(2026, 9, 28, 12);

test("RC4-005: a yes given on a page the server draws is for Google ads alone, and says so", () => {
  const js = read("public/ads.js");
  assert.match(js, /if \(c === "yes"\) rec\.s = "ads";/, "the yes carries its scope");
  assert.match(js, /no\.addEventListener\("click", function \(\) \{ write\("no"\)/, "a no is a no to everything");
  assert.match(js, /StratLab shows Google ads on public pages/, "the question names Google ads only");
  const code = js.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.doesNotMatch(code, /Meta|Clarity|pixel/i, "the page script says and does nothing about the other two");
  const adsOnly = JSON.stringify({ c: "yes", at: NOW, s: "ads" });
  assert.equal(A.parseChoice(adsOnly, NOW), "yes", "the ad slots take it as a yes");
  assert.equal(A.parseAdsOnly(adsOnly, NOW), true);
  assert.equal(A.parseAdsOnly(A.encodeChoice("yes", NOW), NOW), false, "the app's own Allow is a full one");
  assert.equal(A.parseAdsOnly(A.encodeChoice("no", NOW), NOW), false);
  assert.equal(A.parseAdsOnly(adsOnly, NOW + 366 * 864e5), false, "a year on it is not an answer at all");
  assert.equal(A.parseAdsOnly("not json", NOW), false);
  assert.equal(A.encodeChoice("yes", NOW, "ads"), adsOnly);
});

test("RC4-005: that yes does not start the pixel or Clarity, and the app asks about them", () => {
  const go = (o) => A.trackersFor({ cfg: PIXEL, choice: "yes", path: "/library", ...o });
  assert.deepEqual(go({}), { pixel: true, clarity: true });
  assert.deepEqual(go({ adsOnly: true }), { pixel: false, clarity: false }, "a yes about ads is not a yes to these");
  const ask = (o) => A.askNow({ cfg: PIXEL, choice: "yes", path: "/library", ...o });
  assert.equal(ask({}), false, "a full yes is not asked again");
  assert.equal(ask({ adsOnly: true }), true, "the question about the others is still open");
  assert.equal(ask({ adsOnly: true, declined: true }), false, "and once No thanks is said it is not asked again");
  assert.equal(ask({ adsOnly: true, path: "/money" }), false, "never on a private page");
  const adsOnlyCfg = A.adsConfig({ VITE_ADSENSE_CLIENT: "ca-pub-1234567890123456", VITE_ADSENSE_SLOT_PUBLIC: "1111111111", VITE_ADS_ENABLED: "true" }, { CLARITY_PROJECT_ID: "" });
  assert.equal(A.askNow({ cfg: adsOnlyCfg, choice: "yes", path: "/library", adsOnly: true }), false, "nothing else is on: nothing more to ask");
  assert.equal(A.askNow({ cfg: PIXEL, choice: "no", path: "/library", adsOnly: false }), false, "No thanks sticks");
  const words = A.consentWords(PIXEL, true);
  assert.equal(words.title, "Analytics");
  assert.doesNotMatch(words.text, /Google/, "the ads were answered already");
  assert.match(words.text, /Meta's ad measurement and Microsoft Clarity/);
  assert.equal(A.consentWords(PIXEL).title, "Ads and analytics");
});

test("RC4-005: No thanks to the others keeps the ads allowed; the app's Allow replaces the ads-only note", () => {
  const store = new Map();
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) } });
  try {
    store.set(A.CHOICE_KEY, JSON.stringify({ c: "yes", at: Date.now(), s: "ads" }));
    assert.equal(A.readChoice(), "yes");
    assert.equal(A.readAdsOnly(), true);
    assert.equal(A.readDeclined(), false);
    A.declineTrackers();
    assert.equal(A.readChoice(), "yes", "the ads stay allowed");
    assert.equal(A.readDeclined(), true);
    assert.equal(JSON.parse(store.get(A.CHOICE_KEY)).t, "no");
    A.writeChoice("yes");
    assert.equal(A.readAdsOnly(), false, "an Allow in the app covers everything it names");
    assert.equal(A.readDeclined(), false);
    A.writeChoice("no");
    A.declineTrackers();
    assert.equal(A.readChoice(), "no", "a no is left as it was");
    A.clearChoice();
    assert.equal(A.readChoice(), null);
  } finally {
    delete globalThis.localStorage;
  }
});

test("RC4-005: the banner and the Privacy page follow the answer's scope", () => {
  const t = read("src/components/Tracking.tsx");
  assert.match(t, /trackersFor\(\{ cfg: CONFIG, choice, path: pathname, dnt: doNotTrack\(\), adsOnly \}\)/);
  assert.match(t, /askNow\(\{ cfg: CONFIG, choice, path: pathname, adsOnly, declined \}\)/);
  assert.match(t, /adsOnly \? declineTrackers\(\) : writeChoice\("no"\)/);
  assert.match(t, /allowed for Google ads only/);
  const legal = read("src/content/legal.ts");
  assert.match(legal, /on a company page, the question is about Google ads only/);
  assert.match(legal, /Meta's and Microsoft's are asked about separately and stay off until you allow them/);
});
