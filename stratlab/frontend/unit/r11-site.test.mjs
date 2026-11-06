// Release 11 (owner screenshots of 5 Nov): an old hand-run audit is history, not a list of today's problems (item 24), and the Themes page's
// "Draft a blog post" bar is the owner's only (item 15). Every value is fixed.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("item 24: a hand-run audit over a week old is folded as history, its counts greyed, and counted nowhere as an issue", async () => {
  const { oldAudit, STALE_DAYS } = await import("../src/pages/admin/auditAge.ts");
  const now = Date.parse("2026-11-05T17:00:00Z");
  assert.equal(STALE_DAYS, 7);
  assert.deepEqual(oldAudit("2026-10-03T09:00:00Z", now), { days: 33, day: "3 Oct" });
  assert.equal(oldAudit("2026-10-30T09:00:00Z", now), null);                     // six days: still the latest results, shown as they are
  assert.equal(oldAudit("2026-10-29T16:00:00Z", now)?.days, 7);                   // a week and an hour: old
  assert.equal(oldAudit(null, now), null);
  assert.equal(oldAudit("not a date", now), null);
  const panel = read("src/pages/admin/AuditPanel.tsx");
  assert.match(panel, /Last hand-run audit, \{old\.day\} \(old\)/);
  assert.match(panel, /testId="audit-old"/);
  assert.match(panel, /<Disclosure summary=\{<span className="k-muted">Last hand-run audit/);     // closed: no open prop
  assert.doesNotMatch(panel, /audit-old"[^>]*open/);
  assert.match(panel, /className=\{old \? undefined : "k-down"\}/);                                // no red mismatch count on an old run
  assert.match(read("src/pages/admin/admin.css"), /\.adm-old \.k-table td/);
  // the Overview's list of things to look at reads only the whole-market check, never the hand-run audit
  const att = read("src/pages/admin/attention.ts");
  assert.doesNotMatch(att, /\/admin\/audit[^/]/);
  assert.doesNotMatch(att, /finished_at|hand-run/);
});

test("item 15: the Draft a blog post bar is drawn for an admin only, and its endpoint is an admin route", () => {
  const page = read("src/pages/ThemesPage.tsx");
  // R15 (owner: "did you remove the blog button for me too?"): on every theme with figures, not only a notable one
  assert.match(page, /\{me\?\.is_admin && dive\.members > 0 && \(\s*<Notice action=\{\{ label: "Draft a blog post"/);
  assert.match(read("src/lib/theme.ts"), /draft: \(r: Region, theme: string\) => api<[^>]+>\("\/admin\/blog\/theme"/);
  assert.match(read("../backend/app/blog_pages.py"), /@admin_router\.post\("\/admin\/blog\/theme"\)\ndef admin_blog_theme\(req: ThemeDraft, profile=Depends\(admin\.admin_profile\)\)/);
});
