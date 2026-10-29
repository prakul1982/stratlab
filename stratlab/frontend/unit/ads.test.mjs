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
  assert.deepEqual(off, { on: false, client: "ca-pub-8125241692814953", slots: { public: "", ai: "" }, pixel: "", clarity: "z4n5s4xn12" }, "the owner's IDs are the defaults; no slot, so no ad draws; no pixel");
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
test("the Free-account slot: an ad after Allow, a StratLab card before an answer or after No thanks, nothing on Basic or Pro", () => {
  assert.equal(A.adMode(ctx({ choice: "yes" })), "ad");
  assert.equal(A.adMode(ctx({ choice: null })), "house");
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
  assert.equal(A.adMode(pub({ choice: null })), "none", "no ad before the visitor says yes");
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
  assert.equal(A.adMode(ctx({ cmp: false })), "house");
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
  assert.match(js, /var rec = \{ c: c, at: Date\.now\(\) \};[\s\S]*JSON\.stringify\(rec\)/);
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
  assert.doesNotMatch(tsx, /writeChoice|AdAsk/, "the question is the banner's, not the slot's");
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
  // the banner reads its settings from lib/adsConfig.ts, not the slot's code, so a page without a slot never loads it (R8V-013)
  assert.deepEqual(users, ["src/components/Research.tsx", "src/pages/Login.tsx", "src/pages/PublicLibrary.tsx", "src/pages/PublicVerdict.tsx"]);
  assert.match(read("src/components/Tracking.tsx"), /import \{ CONFIG \} from "\.\.\/lib\/adsConfig";/);
  // the library loads the slot's code only when ads can draw there
  assert.match(read("src/pages/PublicLibrary.tsx"), /const PublicAd = \(\) => \(ADS_HERE \? <Suspense fallback=\{null\}><PublicAdLazy \/><\/Suspense> : null\);/);
  assert.match(read("src/pages/Login.tsx"), /<div className="lp-wrap"><PublicAd \/><\/div>/);
  assert.equal(read("src/pages/Login.tsx").match(/<PublicAd/g).length, 1, "at most one slot on the landing page");
  assert.equal(read("src/pages/PublicLibrary.tsx").match(/<PublicAd \/>/g).length, 2, "one on the list and one on a strategy");
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
  for (const part of ["only if you allow them", "Google ads (AdSense)", "Meta Pixel", "Microsoft Clarity", "Basic and Pro have no ads", "IP address", "Do Not Track", "No thanks",
    "Money, tax, holdings, net worth, Account, Settings, Admin, sign-in or payment pages", "Change my choice", "stratlab.ads", "adssettings.google.com"]) assert.ok(privacy.includes(part), part);
  assert.doesNotMatch(privacy, /no advertising trackers|Nothing is used for advertising/, "the old claims are gone");
  assert.equal(LEGAL_UPDATED["/privacy"], "28 October 2026");
  const q = FAQ.find((f) => f.q === "Does StratLab show ads or track me?");
  assert.ok(q);
  const a = faqText(q);
  for (const part of ["Only if you allow it", "Google ads", "Meta", "Microsoft Clarity", "No thanks", "Basic and Pro have no ads", "cookies", "Money, tax, holdings, net worth, Account or payment pages", "emails"]) assert.ok(a.includes(part), part);
});

test("the cards that hold a Free account's place state facts: no advice wording, no data vendors, the plan's real numbers", async () => {
  const P = await import("../src/lib/plans.ts");
  const H = await import("../src/lib/houseAds.ts");        // (apart from lib/ads.ts so a policy page doesn't download the plans: R5V-020)
  assert.equal(H.HOUSE.length, 3);
  const all = H.HOUSE.map((c) => `${c.title} ${c.text} ${c.cta}`).join(" ");
  assert.doesNotMatch(all, /\b(buy|sell|hold|target|recommend)\b|yahoo|screener|finnhub|kite|zerodha/i);
  const plans = H.HOUSE.find((c) => c.id === "plans");
  for (const n of [P.LIMITS.free.ai_builds_per_month, P.LIMITS.free.deepdives_per_month, P.LIMITS.basic.ai_builds_per_month, P.LIMITS.basic.deepdives_per_month]) assert.ok(plans.text.includes(String(n)), String(n));
  assert.deepEqual(H.HOUSE.map((c) => c.title), ["Basic has more AI builds and deep dives", "Test your idea with the four luck checks", "Read today's market brief"]);
  // the same company always gets the same card, and the cards are spread over companies
  assert.equal(H.houseCard("RELIANCE"), H.houseCard("RELIANCE"));
  assert.ok(new Set(["RELIANCE", "TCS", "INFY", "AAPL", "MSFT", "HDFCBANK", "ITC", "SBIN"].map((s) => H.houseCard(s).id)).size >= 2);
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

// ---------- the Meta Pixel and Microsoft Clarity ----------
const T = { ...A.adsConfig({ VITE_META_PIXEL_ID: "1234567890", VITE_CLARITY_ID: "abc123def4" }) };
const track = (o) => A.trackersFor({ cfg: T, choice: "yes", path: "/library", ...o });

test("Clarity is the owner's project unless set; an empty setting turns it off; the pixel has no default", () => {
  assert.equal(A.DEFAULT_CLARITY, "z4n5s4xn12");
  assert.equal(A.adsConfig({}).clarity, "z4n5s4xn12");
  assert.equal(A.adsConfig({}).pixel, "");
  assert.equal(A.adsConfig({ VITE_CLARITY_ID: "" }).clarity, "");
  assert.equal(A.adsConfig({}, { CLARITY_PROJECT_ID: "" }).clarity, "", "/config.js can switch it off without a rebuild");
  assert.equal(A.adsConfig({ VITE_CLARITY_ID: "abc123def4" }).clarity, "abc123def4");
  assert.equal(A.adsConfig({ VITE_CLARITY_ID: "x" }, { CLARITY_PROJECT_ID: "q9w8e7r6t5" }).clarity, "q9w8e7r6t5", "/config.js over the build");
  assert.equal(A.adsConfig({ VITE_CLARITY_ID: "bad id;<script>" }).clarity, "", "a pasted mistake counts as not set");
  assert.equal(A.adsConfig({ VITE_META_PIXEL_ID: "1234567890" }).pixel, "1234567890");
  for (const bad of ["abc", "12", "1234567890'); alert(1);//"]) assert.equal(A.adsConfig({ VITE_META_PIXEL_ID: bad }).pixel, "", bad);
});

test("nothing loads before Allow: no tracker without a saved yes, whatever the page", () => {
  for (const choice of [null, "no"]) for (const path of ["/", "/library", "/research/IN/RELIANCE", "/mine"]) assert.deepEqual(track({ choice, path }), { pixel: false, clarity: false }, `${choice} ${path}`);
  assert.deepEqual(track({}), { pixel: true, clarity: true });
  assert.deepEqual(track({ path: "/mine" }), { pixel: true, clarity: true }, "the app shell is included");
  assert.deepEqual(A.trackersFor({ cfg: A.adsConfig({}), choice: "yes", path: "/library" }), { pixel: false, clarity: true }, "no pixel ID: no pixel");
  assert.deepEqual(A.trackersFor({ cfg: A.adsConfig({}, { CLARITY_PROJECT_ID: "" }), choice: "yes", path: "/library" }), { pixel: false, clarity: false });
  assert.deepEqual(track({ dnt: true }), { pixel: false, clarity: false }, "Do Not Track and Global Privacy Control win over a yes");
});

test("neither tracker runs on money, tax, holdings, net worth, account, settings, admin or payment pages", () => {
  for (const path of ["/money", "/money/net-worth", "/money/tax-tools", "/holdings", "/tax-report", "/account", "/settings", "/admin", "/admin/users", "/checkout", "/upgrade", "/plans", "/login", "/signup", "/money?x=1", "/holdings#a"])
    assert.deepEqual(track({ path }), { pixel: false, clarity: false }, path);
  for (const path of ["/", "/pricing", "/library", "/verdict/abc", "/research/US/AAPL", "/trade", "/invest", "/mine", "/news"]) assert.equal(A.trackAllowedOn(path), true, path);
});

test("the question is asked only when something needs it, once, and not on a private page", () => {
  const ask = (o) => A.askNow({ cfg: T, choice: null, path: "/library", ...o });
  assert.equal(ask({}), true);
  assert.equal(ask({ choice: "yes" }), false);
  assert.equal(ask({ choice: "no" }), false);
  for (const path of ["/money", "/holdings", "/account", "/admin", "/plans"]) assert.equal(ask({ path }), false, path);
  const none = A.adsConfig({}, { CLARITY_PROJECT_ID: "" });
  assert.equal(A.askNeeded(none), false, "no slot, no pixel, no Clarity: nothing to ask");
  assert.equal(A.askNow({ cfg: none, choice: null, path: "/library" }), false);
  assert.equal(A.askNeeded(A.adsConfig(ENV, { CLARITY_PROJECT_ID: "" })), true, "an ad slot alone needs the question");
  assert.equal(A.askNeeded(A.adsConfig({ VITE_META_PIXEL_ID: "1234567890" }, { CLARITY_PROJECT_ID: "" })), true);
});

test("the question names only what is switched on, in plain words", () => {
  const w = (cfg) => A.consentWords(cfg);
  assert.match(w(A.adsConfig({})).text, /Microsoft Clarity, which records how pages are used with all text hidden/);
  assert.doesNotMatch(w(A.adsConfig({})).text, /Google|Meta/);
  assert.equal(w(A.adsConfig({})).title, "Analytics");
  const all = w(A.adsConfig({ ...ENV, VITE_META_PIXEL_ID: "1234567890" }));
  assert.equal(all.title, "Ads and analytics");
  assert.match(all.text, /Google ads, Meta's ad measurement and Microsoft Clarity/);
  assert.match(all.text, /Say no and none of them load/);
  assert.equal(w(A.adsConfig(ENV, { CLARITY_PROJECT_ID: "" })).title, "Ads");
  assert.doesNotMatch(all.text, /\b(buy|sell|hold|target)\b/i);
});

test("a sign-up is an account made in the last 15 minutes", () => {
  const now = Date.UTC(2026, 9, 28, 12);
  assert.equal(A.isNewSignUp(new Date(now - 5 * 60_000).toISOString(), now), true);
  assert.equal(A.isNewSignUp(new Date(now - 16 * 60_000).toISOString(), now), false);
  for (const bad of [null, undefined, "", "not a date"]) assert.equal(A.isNewSignUp(bad, now), false);
});

test("the trackers' scripts are fetched in lib/track.ts only, and only from the component's gated effect", () => {
  const track = read("src/lib/track.ts"), tracking = read("src/components/Tracking.tsx");
  assert.match(track, /connect\.facebook\.net\/en_US\/fbevents\.js/);
  assert.match(track, /www\.clarity\.ms\/tag\//);
  for (const f of ["index.html", "public/config.js", "public/boot.js", "public/ads.js", "src/components/AdUnit.tsx", "src/lib/ads.ts", "src/lib/analytics.ts"]) assert.doesNotMatch(read(f), /fbevents|clarity\.ms/, f);
  assert.match(tracking, /if \(want\.pixel\) \{ loadPixel\(CONFIG\.pixel\); pixelPageView\(pathname\); flushSignup\(\); \}/);
  assert.match(tracking, /if \(want\.clarity\) startClarity\(CONFIG\.clarity\); else stopClarity\(\);/);
  assert.match(tracking, /askNow\(/);
  // the sign-up path reaches the pixel through the one gated place
  assert.match(read("src/lib/analytics.ts"), /markSignup\(\);/);
  // mounted once in each half of the site
  assert.match(read("src/visitor/visitorMain.tsx"), /<Tracking \/>/);
  assert.match(read("src/main.tsx"), /<Tracking \/>/);
});

test("the pixel and Clarity, run against a stand-in page: nothing before they are called, no extras, strict masking, stop on a private page", async () => {
  const added = [], attrs = {};
  const el = (tag) => ({ tag, setAttribute(k, v) { attrs[`${tag}:${k}`] = v; }, set src(v) { this._src = v; }, get src() { return this._src; } });
  const root = { setAttribute(k, v) { root[k] = v; } }, body = { setAttribute(k, v) { body[k] = v; } };
  globalThis.window = globalThis;
  globalThis.document = { createElement: el, head: { appendChild: (n) => added.push(n) }, getElementById: (id) => (id === "root" ? root : null), body };
  const T2 = await import("../src/lib/track.ts?stand-in");
  assert.deepEqual(added, [], "importing it loads nothing");
  assert.equal(globalThis.fbq, undefined);
  // before the pixel is loaded: no event, a sign-up waits
  T2.pixelPageView("/library"); T2.markSignup(); T2.flushSignup();
  assert.deepEqual(added, []);
  T2.loadPixel("1234567890"); T2.loadPixel("1234567890");
  assert.equal(added.length, 1, "the script once");
  assert.equal(added[0].src, "https://connect.facebook.net/en_US/fbevents.js");
  const calls = globalThis.fbq.queue.map((a) => [...a]);
  assert.deepEqual(calls, [["set", "autoConfig", false, "1234567890"], ["init", "1234567890"]], "automatic extras off, then init");
  assert.equal(globalThis.fbq.disablePushState, true);
  T2.pixelPageView("/library"); T2.pixelPageView("/library"); T2.pixelPageView("/");
  T2.flushSignup(); T2.flushSignup();
  assert.deepEqual(globalThis.fbq.queue.slice(2).map((a) => [...a]), [["track", "PageView"], ["track", "PageView"], ["track", "CompleteRegistration"]]);
  // Clarity: stopping before it started does nothing; starting masks everything and loads the project's tag once
  T2.stopClarity();
  assert.equal(globalThis.clarity, undefined);
  T2.startClarity("abc123def4"); T2.startClarity("abc123def4");
  assert.equal(added.length, 2);
  assert.equal(added[1].src, "https://www.clarity.ms/tag/abc123def4");
  assert.equal(root["data-clarity-mask"], "True"); assert.equal(body["data-clarity-mask"], "True");
  T2.stopClarity();
  assert.deepEqual([...globalThis.clarity.q.at(-1)], ["stop"]);
  T2.stopClarity();
  assert.equal(globalThis.clarity.q.filter((a) => a[0] === "stop").length, 1, "stopped once");
  T2.startClarity("abc123def4");
  assert.deepEqual([...globalThis.clarity.q.at(-1)], ["start"], "started again on an allowed page");
  assert.equal(added.length, 2, "without a second script");
  delete globalThis.window; delete globalThis.document; delete globalThis.fbq; delete globalThis._fbq; delete globalThis.clarity;
});

test("the security policy lets in the pixel's and Clarity's hosts and nothing broader", () => {
  const v = JSON.parse(read("vercel.json"));
  const csp = v.headers.flatMap((h) => h.headers).find((h) => h.key === "Content-Security-Policy").value;
  const d = Object.fromEntries(csp.split(";").map((x) => x.trim().split(/\s+/)).filter((x) => x[0]).map(([k, ...rest]) => [k, rest]));
  for (const h of ["https://connect.facebook.net", "https://www.clarity.ms", "https://*.clarity.ms"]) assert.ok(d["script-src"].includes(h), `script-src ${h}`);
  for (const h of ["https://www.facebook.com", "https://connect.facebook.net", "https://www.clarity.ms", "https://*.clarity.ms"]) assert.ok(d["connect-src"].includes(h), `connect-src ${h}`);
  assert.ok(!d["script-src"].includes("'unsafe-inline'") && !d["script-src"].includes("https:"));
});

test("Do Not Track and Global Privacy Control stop Google ads too: our own card or nothing, and no question (owner, 28 Oct)", async () => {
  const cfg = on;
  const base = { cfg, path: "/library", choice: "yes", signedIn: false, plan: null };
  assert.equal(A.adMode({ ...base, slot: "public" }), "ad");
  assert.equal(A.adMode({ ...base, slot: "public", dnt: true }), "none");
  assert.equal(A.adMode({ ...base, slot: "ai", path: "/research/IN/TCS", plan: "free", dnt: true }), "house");
  assert.equal(A.askNow({ cfg, choice: null, path: "/library" }), true);
  assert.equal(A.askNow({ cfg, choice: null, path: "/library", dnt: true }), false);
  const js = readFileSync(new URL("../public/ads.js", import.meta.url), "utf8");
  assert.match(js, /n\.globalPrivacyControl === true\) \{\s+boxes\.forEach\(drop\); return;/);
  const { LEGAL_BLOCKS } = await import("../src/content/legal.ts");
  assert.ok(JSON.stringify(LEGAL_BLOCKS["/privacy"]).includes("Google ads, the Meta Pixel and Clarity do not load"));
});

test("the morning Zerodha alert links straight to the broker login, which Admin opens at once unless today's login is done", () => {
  const py = readFileSync(new URL("../../backend/app/kite_auto.py", import.meta.url), "utf8");
  assert.match(py, /LOGIN_LINK = "\/admin\/data\?kite=login"/);
  assert.match(py, /url=LOGIN_LINK\)/);
  const page = read("src/pages/admin/DataSection.tsx");
  assert.match(page, /params\.get\("kite"\) === "login"/);
  assert.match(page, /if \(loggedInToday\) \{ notify\("Already logged in to the broker today: nothing to do\."\); return; \}/);
  assert.match(page, /window\.location\.assign\(url\);/);
});
