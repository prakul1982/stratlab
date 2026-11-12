// Bet 3 MVP (public, shareable research): the share-link helpers, the plan copy that names share links, the Account card and the
// share buttons, search, and the host's headers (framing relaxed for /embed/* only; share links and embeds kept out of search).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const vercel = JSON.parse(read("vercel.json"));
const sourceRe = (source) => new RegExp("^" + source.replace(/\(\?:/g, "(?:") + "$");
const header = (path, key) => vercel.headers.filter((h) => !/\/:[a-z]/i.test(h.source) && sourceRe(h.source).test(path))
  .flatMap((h) => h.headers).filter((h) => h.key === key).map((h) => h.value);

test("the share count line and labels say what a link is, with or without a limit", async () => {
  const { shareCountLine, shareKindLabel, sharedNote } = await import("../src/lib/researchShare.ts");
  assert.equal(shareCountLine(0, 1), "0 of 1 share link made this month");
  assert.equal(shareCountLine(2, 30), "2 of 30 share links made this month");
  assert.equal(shareCountLine(1, null), "1 share link made this month (no limit on your plan)");
  assert.equal(shareKindLabel({ kind: "theme", region: "US" }), "Theme · US");
  assert.equal(shareKindLabel({ kind: "deep", region: "IN" }), "Deep dive · India");
  assert.match(sharedNote("deep"), /dated snapshot of this deep dive, not your account; turn it off any time in Account/);
  for (const t of [shareCountLine(3, 30), sharedNote("theme")]) assert.doesNotMatch(t, /\b(buy|sell|upside|target)\b/i);
});

test("every plan's full list names its share links with the server's number, and the comparison table has the row", async () => {
  const { SHARE_LINKS, FEATURES } = await import("../src/lib/planFeatures.ts");
  assert.deepEqual(SHARE_LINKS, { free: 1, basic: 30, pro: null });
  assert.ok(FEATURES.free.some((f) => /\b1 share link$/.test(f)));
  assert.ok(FEATURES.basic.some((f) => /\b30 public share links\b/.test(f)));
  assert.ok(FEATURES.pro.some((f) => /deep dives and decks, with unlimited share links/.test(f)));
  assert.match(read("src/components/PlanCompare.tsx"), /Public share links a month, of a deep dive or a theme/);
  // the landing page's first load (plans.ts) doesn't carry it: its JavaScript budget has no room (review-r5)
  assert.doesNotMatch(read("src/lib/plans.ts"), /share_links/);
});

test("the share button sits on the deep dive and a finished theme; Account lists the links and turns them off", () => {
  assert.match(read("src/pages/DeepDive.tsx"), /<ShareResearchButton kind="deep" region=\{region\} target=\{sym\}/);
  assert.match(read("src/pages/ThemesPage.tsx"), /themeReady\(r\) && <ShareResearchButton kind="theme"/);
  const card = read("src/components/ResearchSharesCard.tsx");
  assert.match(card, /<Card id="shares" label="Shared research links">/);
  assert.match(card, /ConfirmDialog title="Turn this link off\?"/);
  assert.match(card, /EmptyState title="No share links yet"/);
  assert.match(card, /<Skeleton label="Loading your share links"/);
  assert.match(read("src/pages/AccountPage.tsx"), /<ResearchSharesCard \/>/);
});

test("search finds the shared links on Account", async () => {
  const { match } = await import("../src/lib/features.ts");
  const hits = match("share link");
  assert.ok(hits.some((f) => f.to === "/account#shares"), hits.map((f) => f.to).join(", "));
});

test("the host lets other sites frame /embed/* only, and keeps share links and embeds out of search", () => {
  for (const p of ["/embed/price/in/TCS", "/embed/theme/us/semiconductor"]) {
    assert.deepEqual(header(p, "X-Frame-Options"), [], p);
    assert.deepEqual(header(p, "Content-Security-Policy").map((v) => /frame-ancestors \*$/.test(v)), [true], p);
    assert.deepEqual(header(p, "X-Robots-Tag"), ["noindex, follow"], p);
  }
  for (const p of ["/", "/research/IN/TCS", "/themes/in/defence", "/r/abcdefghijklmnopqrstuvwx", "/embedded", "/account"]) {
    assert.deepEqual(header(p, "X-Frame-Options"), ["DENY"], p);
    assert.ok(header(p, "Content-Security-Policy").every((v) => /frame-ancestors 'none'/.test(v)), p);
  }
  assert.deepEqual(header("/r/abcdefghijklmnopqrstuvwx", "X-Robots-Tag"), ["noindex, follow"]);
  assert.deepEqual(header("/themes/in/defence", "X-Robots-Tag"), [], "a theme page decides for itself (its own robots tag)");
  const rw = (src) => vercel.rewrites.find((r) => r.source === src)?.destination ?? "";
  for (const src of ["/r/:token", "/themes/:path*", "/embed/:path*"]) assert.match(rw(src), new RegExp(`^https://.+${src.replace(/[*]/g, "\\*")}$`), src);
  assert.equal(vercel.rewrites.at(-1).destination, "/index.html");
});
