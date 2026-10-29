// A harsh public-site audit, the landing page, /plans and the public library (DK-001 to DK-015): the frontend's side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("DK-003: each plan card is six to eight short lines, not run-on paragraphs", async () => {
  const { FEATURES } = await import("../src/lib/plans.ts");
  for (const p of ["free", "basic", "pro"]) {
    const lines = FEATURES[p].filter((f) => !f.endsWith(":") && !/^Everything in /.test(f));
    assert.ok(lines.length >= 6 && lines.length <= 8, `${p}: ${lines.length} lines`);
    for (const l of lines) assert.ok(l.split(/\s+/).length <= 34, `${p}: "${l}" is ${l.split(/\s+/).length} words`);
  }
  // the free card says its trial in one short line, with the facts it had
  assert.ok(FEATURES.free.some((f) => /^Paper trading trial: 1 strategy on 1 stock for 5 market days from your first start, then Basic or Pro$/.test(f)));
  assert.ok(!FEATURES.free.some((f) => /\(after that, paper trading needs/.test(f)));
});

test("DK-005: the comparison tables share their column widths, and Free's one session reads as a trial", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.k-compare \.k-table \{ table-layout: fixed; \}/);
  assert.match(css, /\.k-compare \.k-table th:not\(:first-child\), \.k-compare \.k-table td:not\(:first-child\) \{ width: 17%;/);
  const src = read("src/components/PlanCompare.tsx");
  assert.match(src, /className="k-compare"/);
  assert.match(src, /`\$\{v\} \(5-market-day trial\)`/);
  assert.doesNotMatch(src, /, for 5 market days/);
});

test("DK-004, DK-008: /plans is one heading and one line with the public header; Library and Companies are in every public menu", async () => {
  const login = read("src/pages/Login.tsx");
  assert.match(login, /const NAV_LINKS = \(plansOnly: boolean\)/);
  assert.match(login, /plansOnly \? PUBLIC_MENU/);
  assert.match(login, /\["\/library", "Library"\], \["\/stocks", "Companies"\]/);
  assert.match(login, /<Pricing top=\{plansOnly \? \{ heading: heading \?\? "Plans and prices", error \} : undefined\} \/>/);
  assert.doesNotMatch(login, /lp-sec-plans/);
  const { PUBLIC_MENU } = await import("../src/components/PublicFrame.tsx").catch(() => ({ PUBLIC_MENU: null }));
  const frame = read("src/components/PublicFrame.tsx");
  assert.match(frame, /\["\/library", "Library"\],\s*\["\/stocks", "Companies"\]/);
  assert.match(frame, /<SiteLinks \/><LegalLinks \/>/);
  assert.match(login, /<SiteLinks \/>/);
  void PUBLIC_MENU;
  assert.match(read("../backend/app/stock_pages.py"), /\/library">Library<\/a><a href="\/stocks">Companies/);
});

test("DK-006: /plans is indexed with its own address, listed in the sitemap, and not sent a noindex header", async () => {
  const seo = await import("../src/content/seo.ts");
  const p = seo.pageMeta("/plans");
  assert.equal(p.index, true);
  assert.equal(p.canonical, undefined);                         // its own address
  assert.ok(seo.sitemapPages().some((x) => x.path === "/plans"));
  assert.match(read("../backend/app/site_pages.py"), /\("\/plans", "\d{4}-\d{2}-\d{2}"\)/);
  const vercel = JSON.parse(read("vercel.json"));
  const noindex = vercel.headers.filter((h) => h.headers.some((x) => x.key === "X-Robots-Tag")).map((h) => new RegExp(`^${h.source}$`));
  assert.ok(!noindex.some((re) => re.test("/plans")), "/plans carries no noindex header");
  assert.ok(noindex.some((re) => re.test("/plans/x")), "a path under it still does");
  const { seoFor } = await import("../src/lib/seo.ts");
  assert.deepEqual([seoFor("/plans").index, seoFor("/plans").canonical], [true, "https://stratlab.studio/plans"]);
});

test("DK-013: the home title carries the words people search, in about 65 characters", async () => {
  const { HOME_TITLE, HOME_DESCRIPTION } = await import("../src/content/seo.ts");
  assert.match(HOME_TITLE, /backtest/);
  assert.match(HOME_TITLE, /research stocks/);
  assert.ok(HOME_TITLE.length <= 65, `${HOME_TITLE.length} characters`);
  assert.ok(HOME_DESCRIPTION.length >= 120);
  const html = read("index.html");
  assert.ok(html.includes(`<title>${HOME_TITLE}</title>`));
  assert.ok(html.includes(`<meta property="og:title" content="${HOME_TITLE}">`));
});

test("DK-008, DK-009, DK-011: real company pages linked from Invest, the pause button beside the tabs, the FAQ's Contact link, a Help heading", () => {
  const login = read("src/pages/Login.tsx");
  assert.match(login, /\["\/stocks\/in\/RELIANCE", "Reliance Industries"\], \["\/stocks\/us\/AAPL", "Apple"\]/);
  assert.match(login, /data-testid="real-companies"/);
  assert.ok(login.indexOf('className="lp-demo-bar"') < login.indexOf('className="lp-demo-pause"'));
  assert.ok(login.indexOf('className="lp-demo-pause"') < login.indexOf('className="lp-demo-stack"'), "the pause button is above the card, not under it");
  assert.match(login, /<Link className="link" to="\/contact">the Contact page<\/Link> reaches a person/);
  assert.match(login, /heading === "Help"/);
  assert.match(login, /<Head eyebrow="Questions and contact" title="Help" h1>/);
  assert.match(read("src/styles.css"), /\.lp-faq-head \{ position: sticky;/);
});

test("DK-014, DK-015: the library says its result once per card, sums the list from its data, and offers only filters with something behind them", async () => {
  const { holdResult, libraryTally, liveOptions } = await import("../src/lib/libraryList.ts");
  const e = (id, verdict, gap, checks = [], market = "IN") => ({ id, market, verdict: { verdict, checks }, vs_hold: gap == null ? null : { ret: 1, hold: 2, gap } });
  assert.equal(holdResult(e("a", "edge", -108.54)), "108.5 points behind buy and hold");
  assert.equal(holdResult(e("a", "edge", 3.04)), "3.0 points ahead of buy and hold");
  assert.equal(holdResult(e("a", "edge", 0.01)), "About the same as buy and hold");
  assert.equal(holdResult(e("a", "edge", null)), null);
  const rows = [e("1", "edge", -10), e("2", "no_edge", -20, [{ id: "unseen", status: "fail" }]), e("3", "edge", 5, [], "US"), e("4", "luck", -1, [{ id: "nearby", status: "fail" }, { id: "unseen", status: "fail" }])];
  const t = libraryTally(rows);
  assert.deepEqual([t.total, t.behind, t.failed], [4, 3, 2]);
  assert.equal(t.line, "3 of 4 finished behind buy and hold · 2 failed a check");
  const verdicts = [["", "Any result"], ["edge", "No check failed"], ["mixed", "Mixed check results"], ["luck", "Failed a robustness check"], ["not_enough", "Too few trades"], ["no_edge", "Lost money after costs"]];
  assert.deepEqual(liveOptions(verdicts, rows, (r) => r.verdict.verdict, "").map(([v]) => v), ["", "edge", "luck", "no_edge"]);
  assert.deepEqual(liveOptions(verdicts, rows, (r) => r.verdict.verdict, "mixed").map(([v]) => v), ["", "edge", "mixed", "luck", "no_edge"], "the chosen one stays so it can be undone");
  const lib = read("src/pages/PublicLibrary.tsx");
  assert.match(lib, /data-testid="lib-summary"/);
  const list = lib.slice(0, lib.indexOf("export function PublicLibraryEntry"));
  assert.doesNotMatch(list, /<BehindHold|<HoldLine|lib-reason|lib-window/, "the card no longer repeats the result four ways");
  assert.match(read("src/components/LibraryBits.tsx"), /data-testid="lib-hold"/);       // the one result line, in the card both libraries draw (MO-5a)
});

test("DK-001: a card charged in rupees leads with the rupee price on the landing page and on Plans", () => {
  const login = read("src/pages/Login.tsx"), plans = read("src/pages/PlansPage.tsx");
  assert.match(login, /inRupees\(p, year\) \? rupees\(p, year\) : local \? money\(local, amount\(p, year\), currency\)/);
  assert.match(plans, /if \(!chargedInRupees\(row, currency, chargedIn\)\) return \{ \.\.\.none, shown: money\(row, local, currency\) \};/);
  assert.match(plans, /const charged = money\(inr, rupees\(p, per\), "INR"\);\n\s+return \{ shown: charged,/);
});
