// Round 64 (19 Oct 2026): the owner's money pages, live refresh, reliability — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R64-001: the watchlist has three columns on a phone: company, price with its change, and a bin", () => {
  const src = read("src/pages/Research.tsx");
  const table = src.slice(src.indexOf('label="Your watchlist"'), src.indexOf("</Card>", src.indexOf('label="Your watchlist"')));
  assert.deepEqual([...table.matchAll(/\{ key: "(\w+)"/g)].map((m) => m[1]), ["s", "p", "r"]);
  assert.match(table, /header: `Price · \$\{/);
  assert.match(table, /className="btn quiet sm icon-only" aria-label=\{`Remove \$\{w\.symbol\} from your watchlist`\} title="Remove"/);
});

test("R64-002: an expiring chain's IV says so, and the missing percentile says why in a whole sentence", () => {
  const src = read("src/pages/PositioningPage.tsx");
  assert.match(src, /These options expire today, so their IV runs high in their last hours; the India VIX card reads the next expiry's/);
  assert.match(src, /Not given on the day these options expire/);
  assert.doesNotMatch(src, /the recorded days are its"\} \/>/);
});

test("R64-003: a company chart's candles are kept 5 minutes between the minute's price refreshes", () => {
  const src = read("src/charts/price/lazy.tsx");
  assert.match(src, /const CHART_KEEP_MS = 5 \* 60_000;/);
  assert.match(src, /settleLast\(a\.candles \?\? \[\], reading\)/);
});

test("R64-005, R64-008, R64-010: retries, each index's weekly expiry, and no price stamp without open lots", () => {
  assert.match(read("src/pages/Login.tsx"), /lazy\(\(\) => importWithRetry\(\(\) => import\("\.\.\/components\/PlanCompare"\)\)/);
  assert.match(read("src/pages/trade/EventsPage.tsx"), /if \(isWeekly\(e\) && !seen\.has\(e\.title\)\)/);
  assert.match(read("src/lib/mine.ts"), /!named\.has\(e\.title\)\) \{ named\.add\(e\.title\); weekly\.add\(e\); \}/);
  assert.match(read("src/pages/TaxReportPage.tsx"), /asOf=\{rep\?\.below_cost\.open \? rep\.prices_at : undefined\}/);
});
