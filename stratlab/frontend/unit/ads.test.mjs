// ADS-1: ads are ready to switch on and do nothing until they are. Who sees what (by plan, page, answer and switch), the answer's
// storage, the places an ad may be drawn, the security policy and the words about ads. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const A = await import("../src/lib/ads.ts");

const ENV = { VITE_ADSENSE_CLIENT: "ca-pub-1234567890123456", VITE_ADSENSE_SLOT_PUBLIC: "1111111111", VITE_ADSENSE_SLOT_AI: "2222222222", VITE_ADS_ENABLED: "true" };
const on = A.adsConfig(ENV);
const off = A.adsConfig({});
const ctx = (o) => ({ slot: "ai", cfg: on, path: "/research/IN/RELIANCE", choice: null, signedIn: true, plan: "free", ...o });

// ---------- the settings ----------
test("ads are off unless the switch, the publisher ID and the slot's ID are all set", () => {
  assert.deepEqual(off, { on: false, client: "ca-pub-8125241692814953", slots: { public: "", ai: "" } }, "the owner's ID is the default; no slot, so nothing draws");
  assert.equal(A.adsLive(off, "public"), false);
  assert.equal(A.adsLive(on, "public"), true);
  assert.equal(A.adsLive(on, "ai"), true);
  assert.equal(A.adsLive(A.adsConfig({ ...ENV, VITE_ADS_ENABLED: "false" }), "ai"), false, "the kill switch beats the IDs");
  assert.equal(A.adsLive(A.adsConfig({ ...ENV, VITE_ADS_ENABLED: "" }), "ai"), false, "off by default");
  assert.equal(A.adsConfig({ ...ENV, VITE_ADSENSE_CLIENT: "" }).client, A.DEFAULT_CLIENT, "no ID set: the owner's");
  assert.equal(A.adsLive(A.adsConfig({ ...ENV, VITE_ADSENSE_SLOT_AI: "" }), "ai"), false, "each slot needs its own ID");
  assert.equal(A.adsLive(A.adsConfig({ ...ENV, VITE_ADSENSE_SLOT_AI: "" }), "public"), true);
  // a pasted mistake counts as not set
  assert.equal(A.adsConfig({ ...ENV, VITE_ADSENSE_CLIENT: "pub-1234567890123456" }).client, "");
  assert.equal(A.adsConfig({ ...ENV, VITE_ADSENSE_CLIENT: 'ca-pub-1234567890123456"><script>' }).client, "");
  assert.equal(A.adsConfig({ ...ENV, VITE_ADSENSE_SLOT_PUBLIC: "12ab" }).slots.public, "");
});

test("/config.js can turn ads off (or set the IDs) without a rebuild", () => {
  assert.equal(A.adsLive(A.adsConfig(ENV, { ADS_ENABLED: "false" }), "ai"), false);
  const only = A.adsConfig({}, { ADS_ENABLED: "true", ADSENSE_CLIENT: "ca-pub-1234567890123456", ADSENSE_SLOT_PUBLIC: "3333333333" });
  assert.equal(A.adsLive(only, "public"), true);
  assert.equal(A.adsLive(only, "ai"), false);
});

// ---------- who sees what ----------
test("the Free-account slot: an ad after Allow, the question before it, a StratLab card otherwise, nothing on Basic or Pro", () => {
  assert.equal(A.adMode(ctx({ choice: "yes" })), "ad");
  assert.equal(A.adMode(ctx({ choice: null })), "consent");
  assert.equal(A.adMode(ctx({ choice: "no" })), "house");
  for (const plan of ["basic", "pro", null]) for (const choice of ["yes", "no", null]) {
    assert.equal(A.adMode(ctx({ plan, choice })), "none", `${plan} / ${choice}: no ads, no card, nothing while the plan is unknown`);
    assert.equal(A.adMode(ctx({ plan, choice, cfg: off })), "none", `${plan} with ads off`);
  }
});

test("ads off: Free sees the StratLab card whatever the answer was; no ad and no question", () => {
  for (const choice of ["yes", "no", null]) assert.equal(A.adMode(ctx({ cfg: off, choice })), "house");
  assert.equal(A.adMode(ctx({ cfg: A.adsConfig({ ...ENV, VITE_ADS_ENABLED: "false" }), choice: "yes" })), "house", "the kill switch removes a saved yes");
  assert.equal(A.adMode(ctx({ cfg: A.adsConfig({ ...ENV, VITE_ADSENSE_SLOT_AI: "" }), choice: "yes" })), "house");
});

test("the public slot: signed-out visitors only, nothing while ads are off, and no card in its place", () => {
  const pub = (o) => ctx({ slot: "public", path: "/library", signedIn: false, plan: null, ...o });
  assert.equal(A.adMode(pub({ choice: "yes" })), "ad");
  assert.equal(A.adMode(pub({ choice: null })), "consent");
  assert.equal(A.adMode(pub({ choice: "no" })), "none");
  assert.equal(A.adMode(pub({ cfg: off, choice: "yes" })), "none");
  assert.equal(A.adMode(pub({ cfg: off })), "none");
  assert.equal(A.adMode(pub({ signedIn: true, choice: "yes" })), "none", "someone with a saved sign-in is not a visitor");
  assert.equal(A.adMode(pub({ plan: "free", choice: "yes" })), "none");
  assert.equal(A.adMode(pub({ cfg: A.adsConfig({ ...ENV, VITE_ADSENSE_SLOT_PUBLIC: "" }), choice: "yes" })), "none");
  for (const path of ["/", "/library", "/library/seed-rsi", "/verdict/abc"]) assert.equal(A.adMode(pub({ path, choice: "yes" })), "ad", path);
});

test("Google's own consent message on the page: ours steps aside, unless the visitor already said no", () => {
  assert.equal(A.adMode(ctx({ cmp: true })), "ad");
  assert.equal(A.adMode(ctx({ cmp: true, choice: "no" })), "house");
  assert.equal(A.adMode(ctx({ cmp: false })), "consent");
});

test("never on money, tax, holdings, net worth, account, admin, sign-in or payment pages, whatever the plan and answer", () => {
  const never = ["/money", "/money/net-worth", "/money/tax-tools", "/money/itr", "/holdings", "/tax-report", "/account", "/account/plan", "/settings", "/admin",
    "/admin/users", "/login", "/signup", "/upgrade", "/plans", "/pricing", "/checkout", "/invite", "/import", "/alerts", "/assistant", "/paper", "/options", "/mine",
    "/n/abc", "/notebooks", "/money?x=1", "/holdings#top"];
  for (const path of never) {
    assert.equal(A.adsAllowedOn(path), false, path);
    for (const slot of ["ai", "public"]) for (const choice of ["yes", "no", null])
      assert.equal(A.adMode(ctx({ slot, path, choice, signedIn: false, plan: slot === "ai" ? "free" : null })), "none", `${slot} on ${path}`);
  }
  for (const path of ["/", "/library", "/library/seed-x", "/verdict/abc", "/research/IN/RELIANCE", "/research/US/AAPL", "/stocks/in/TCS"]) assert.equal(A.adsAllowedOn(path), true, path);
});

// ---------- the answer ----------
test("the answer is yes or no with a date, good for a year, and a damaged or old one is no answer", () => {
  const now = Date.UTC(2026, 9, 28);
  assert.equal(A.parseChoice(A.encodeChoice("yes", now), now + 864e5), "yes");
  assert.equal(A.parseChoice(A.encodeChoice("no", now), now + 364 * 864e5), "no");
  assert.equal(A.parseChoice(A.encodeChoice("yes", now), now + 366 * 864e5), null, "asked again after a year");
  for (const bad of [null, undefined, "", "yes", "{}", "{not json", JSON.stringify({ c: "maybe", at: now }), JSON.stringify({ c: "yes" }), JSON.stringify({ c: "yes", at: "today" })])
    assert.equal(A.parseChoice(bad, now), null, String(bad));
});

test("saving the answer never throws when storage is off, and is kept for the page view", () => {
  const was = globalThis.localStorage;
  Object.defineProperty(globalThis, "localStorage", { configurable: true, get() { throw new Error("blocked"); } });
  try {
    assert.equal(A.readChoice(), null);
    A.writeChoice("no");
    assert.equal(A.readChoice(), "no");
  } finally {
    if (was === undefined) delete globalThis.localStorage; else Object.defineProperty(globalThis, "localStorage", { configurable: true, value: was });
  }
});

test("the page script and the app share one key and one format", () => {
  const js = read("public/ads.js");
  assert.equal(/var KEY = "([^"]+)"/.exec(js)[1], A.CHOICE_KEY);
  assert.equal(Number(/var DAYS = (\d+)/.exec(js)[1]), A.CHOICE_DAYS);
  assert.match(js, /JSON\.stringify\(\{ c: c, at: Date\.now\(\) \}\)/);
  assert.match(js, /typeof j\.at === "number"/);
});

// ---------- the script comes only after Allow ----------
test("Google's script is loaded only after Allow, below the fold, and never from a static tag", () => {
  const js = read("public/ads.js");
  // the only place the script's address appears is load(), which start() reaches for a saved yes (or Google's own message) and the Allow button
  assert.equal(js.match(/adsbygoogle\.js/g).length, 1);
  assert.match(js, /pagead2\.googlesyndication\.com\/pagead\/js\/adsbygoogle\.js\?client=/);
  assert.match(js, /if \(choice === "no"\) \{ boxes\.forEach\(drop\); return; \}\s*if \(choice === "yes" \|\| googleMessage\(\)\) \{ whenNear\(load\); return; \}\s*ask\(boxes\[0\]\)/);
  assert.match(js, /yes\.addEventListener\("click", function \(\) \{ write\("yes"\);/);
  assert.match(js, /rootMargin: "300px 0px"/);
  const tsx = read("src/components/AdUnit.tsx");
  assert.equal(tsx.match(/adsbygoogle\.js/g).length, 2, "the duplicate check and the one address");
  assert.match(tsx, /function addScript/);
  assert.match(tsx, /rootMargin: "300px 0px"/);
  for (const f of ["index.html", "public/config.js", "public/boot.js"]) assert.doesNotMatch(read(f), /googlesyndication|adsbygoogle/, f);
});

test("the ad is labelled, holds its height, and is not styled like StratLab's own cards", () => {
  const css = read("src/styles.css");
  const rule = (sel) => new RegExp(`^${sel.replace(/[.]/g, "\\.")} \\{([^}]*)\\}`, "m").exec(css)?.[1] ?? "";
  assert.match(rule(".ad-box"), /min-height: 280px/);
  assert.doesNotMatch(rule(".ad"), /background|box-shadow|border-radius/);
  assert.match(read("src/components/AdUnit.tsx"), /<p className="ad-label">Advertisement<\/p>/);
  assert.match(read("src/components/AdUnit.tsx"), /aria-label="Advertisement"/);
});

// ---------- where it is drawn ----------
function sources(dir) {
  const out = [];
  for (const n of readdirSync(new URL(`../${dir}`, import.meta.url))) {
    const rel = `${dir}/${n}`;
    if (statSync(new URL(`../${rel}`, import.meta.url)).isDirectory()) out.push(...sources(rel)); else if (/\.tsx?$/.test(n)) out.push(rel);
  }
  return out;
}

test("an ad slot is drawn in exactly these places, and in none of the money, account, admin, sign-in or payment files", () => {
  const users = sources("src").filter((f) => /AdUnit|AiAd|PublicAd/.test(read(f)) && !/^src\/components\/(AdUnit|AiAd)\.tsx$/.test(f)).sort();
  assert.deepEqual(users, ["src/components/Research.tsx", "src/pages/Login.tsx", "src/pages/PublicLibrary.tsx", "src/pages/PublicVerdict.tsx"]);
  assert.match(read("src/pages/Login.tsx"), /<div className="lp-wrap"><PublicAd \/><\/div>/);
  assert.equal(read("src/pages/Login.tsx").match(/<PublicAd/g).length, 1, "at most one slot on the landing page");
  assert.equal(read("src/pages/PublicLibrary.tsx").match(/<PublicAd/g).length, 2, "one on the list and one on a strategy");
  assert.equal(read("src/pages/PublicVerdict.tsx").match(/<PublicAd/g).length, 1);
  // the hero is above every slot
  const login = read("src/pages/Login.tsx");
  assert.ok(login.indexOf("<PublicAd") > login.indexOf('id="alerts"') && login.indexOf("<PublicAd") < login.indexOf("<Pricing"));
  // the one slot in the app is under a written AI read, and only when there is one
  const r = read("src/components/Research.tsx");
  assert.equal(r.match(/<AiAd /g).length, 1);
  assert.match(r, /\{r && !error && <AiAd seed=\{symbol\} \/>\}/);
  assert.ok(r.indexOf("<AiAd") > r.indexOf("export function AIRead") && r.indexOf("<AiAd") < r.indexOf("export function SourcesNote"));
});

test("the app's slot reads the plan the app already uses, and shows nothing until it is known", () => {
  const s = read("src/components/AiAd.tsx");
  assert.match(s, /me\?\.plan \?\? null/);
  assert.doesNotMatch(read("src/components/AdUnit.tsx"), /lib\/app|lib\/api/, "the public pages must not pull in the account code");
});

// ---------- the plans say it ----------
test("Basic and Pro have no ads, and the plans say so", async () => {
  const P = await import("../src/lib/plans.ts");
  assert.ok(P.FEATURES.basic.some((f) => /^No ads, /.test(f)));
  assert.deepEqual(P.ADS, { free: "After you allow them", basic: "None", pro: "None" });
  assert.match(read("src/components/PlanCompare.tsx"), /ADS\[p\]/);
  // Free's card names no ad: the page says it in the table row, the FAQ and the policy
  assert.ok(!P.FEATURES.free.some((f) => /\bads?\b/i.test(f)));
});

test("the privacy page and the FAQ say plainly: Google ads after consent, what Google may set, how to say no, none on Basic and Pro", async () => {
  const { LEGAL_BLOCKS, LEGAL_UPDATED } = await import("../src/content/legal.ts");
  const { FAQ, faqText } = await import("../src/content/faq.ts");
  const privacy = JSON.stringify(LEGAL_BLOCKS["/privacy"]);
  for (const part of ["may show ads from Google AdSense", "Basic and Pro have no ads", "Only after you say yes", "What Google may set", "IP address", "How to say no", "No thanks",
    "Never on personal money pages", "stratlab.ads", "adssettings.google.com"]) assert.ok(privacy.includes(part), part);
  assert.doesNotMatch(privacy, /no advertising trackers|Nothing is used for advertising/, "the old claims are gone");
  assert.equal(LEGAL_UPDATED["/privacy"], "28 October 2026");
  const q = FAQ.find((f) => f.q === "Does StratLab show ads?");
  assert.ok(q);
  const a = faqText(q);
  for (const part of ["Google ads", "Allow ads", "No thanks", "Basic and Pro have no ads", "cookies", "Money, tax, holdings, net worth or account pages", "emails"]) assert.ok(a.includes(part), part);
});

test("the cards that hold a Free account's place state facts: no advice wording, no data vendors, the plan's real numbers", async () => {
  const P = await import("../src/lib/plans.ts");
  assert.equal(A.HOUSE.length, 3);
  const all = A.HOUSE.map((c) => `${c.title} ${c.text} ${c.cta}`).join(" ");
  assert.doesNotMatch(all, /\b(buy|sell|hold|target|recommend)\b|yahoo|screener|finnhub|kite|zerodha/i);
  const plans = A.HOUSE.find((c) => c.id === "plans");
  for (const n of [P.LIMITS.free.ai_builds_per_month, P.LIMITS.free.deepdives_per_month, P.LIMITS.basic.ai_builds_per_month, P.LIMITS.basic.deepdives_per_month]) assert.ok(plans.text.includes(String(n)), String(n));
  assert.deepEqual(A.HOUSE.map((c) => c.title), ["Basic has more AI builds and deep dives", "Test your idea with the four luck checks", "Read today's market brief"]);
  // the same company always gets the same card, and the cards are spread over companies
  assert.equal(A.houseCard("RELIANCE"), A.houseCard("RELIANCE"));
  assert.ok(new Set(["RELIANCE", "TCS", "INFY", "AAPL", "MSFT", "HDFCBANK", "ITC", "SBIN"].map((s) => A.houseCard(s).id)).size >= 2);
});

// ---------- the host's rules ----------
test("the security policy lets in only what AdSense needs and stays strict otherwise", () => {
  const v = JSON.parse(read("vercel.json"));
  const csp = v.headers.flatMap((h) => h.headers).find((h) => h.key === "Content-Security-Policy").value;
  const d = Object.fromEntries(csp.split(";").map((x) => x.trim().split(/\s+/)).filter((x) => x[0]).map(([k, ...rest]) => [k, rest]));
  const ads = (list) => list.filter((h) => /google|doubleclick|googlesyndication|adtrafficquality/.test(h)).sort();
  assert.deepEqual(ads(d["script-src"]), ["https://*.adtrafficquality.google", "https://adservice.google.com", "https://googleads.g.doubleclick.net", "https://pagead2.googlesyndication.com", "https://tpc.googlesyndication.com"]);
  assert.deepEqual(ads(d["frame-src"]), ["https://*.adtrafficquality.google", "https://googleads.g.doubleclick.net", "https://tpc.googlesyndication.com", "https://www.google.com"]);
  assert.ok(ads(d["connect-src"]).includes("https://pagead2.googlesyndication.com") && ads(d["connect-src"]).includes("https://*.adtrafficquality.google"));
  // nothing else loosened
  assert.deepEqual(d["default-src"], ["'self'"]);
  assert.ok(!d["script-src"].includes("'unsafe-inline'") && !d["script-src"].includes("'unsafe-eval'") && !d["script-src"].includes("https:") && !d["script-src"].includes("*"));
  assert.deepEqual(d["frame-ancestors"], ["'none'"]);
  assert.deepEqual(d["object-src"], ["'none'"]);
  assert.deepEqual(d["base-uri"], ["'self'"]);
  assert.ok(!d["frame-src"].includes("*") && !d["frame-src"].includes("https:"));
  assert.deepEqual(d["style-src"], ["'self'", "'unsafe-inline'"]);
});
