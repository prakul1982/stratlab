// Release 42, lane m1 (LIVE7A/LIVE7B live review of Release 41): market-page fixes. Each test names its finding. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const dayText = (d) => ({ "2026-11-10": "10 Nov", "2026-11-11": "11 Nov", "2026-11-12": "12 Nov" })[d] ?? d;

test("LIVE7A-001: Mood's tables carry their own session's date when the read is behind the index levels", async () => {
  const { moodDay, moodBehindNote, sessionWord } = await import("../src/lib/pulseMood.ts");
  // US at 06:42 ET, 12 Nov: levels are the 11 Nov close, the read is of 10 Nov
  assert.equal(moodDay({ session: "2026-11-10", behind: "2026-11-11" }, "2026-11-11"), "2026-11-10");
  assert.equal(moodDay({ session: "2026-11-10" }, "2026-11-11"), "2026-11-10");
  assert.equal(moodBehindNote({ session: "2026-11-10", behind: "2026-11-11" }, "2026-11-11", dayText),
    "These figures are of the 10 Nov session; the 11 Nov session's are being read.");
  // an up-to-date read: the levels' day, and no note
  assert.equal(moodDay({ session: "2026-11-11" }, "2026-11-11"), "2026-11-11");
  assert.equal(moodBehindNote({ session: "2026-11-11" }, "2026-11-11", dayText), null);
  // while the market trades (no closed day) the read of today stays "Today"
  assert.equal(moodDay({ session: "2026-11-12" }, null), null);
  assert.equal(moodDay(null, "2026-11-11"), "2026-11-11");
  // another market's row says "today" only when its session is today's now, not when the read was made
  assert.equal(sessionWord("2026-11-11", "2026-11-12", dayText), "on 11 Nov");
  assert.equal(sessionWord("2026-11-12", "2026-11-12", dayText), "today");
  const page = read("src/pages/Research.tsx");
  assert.match(page, /closedDay=\{moodDay\(mood, pulseClosedDay\(data\?\.indices\)\)\}/);
  assert.match(page, /behindNote=\{moodBehindNote\(/);
  assert.match(read("src/pages/PulseMood.tsx"), /const b = behind && given\.live \? \{ \.\.\.given, live: false \} : given;/);
});

test("LIVE7A-023: a yield's move is in basis points, the rest in percent", async () => {
  const { quoteMove } = await import("../src/lib/pulseMood.ts");
  assert.deepEqual(quoteMove({ change_pct: 2.45, change_bp: 12 }), { value: 12, text: "+12 bp" });
  assert.deepEqual(quoteMove({ change_pct: -1.2, change_bp: -6 }), { value: -6, text: "−6 bp" });
  assert.deepEqual(quoteMove({ change_pct: 0.38 }), { value: 0.38, text: "+0.38%" });
  assert.deepEqual(quoteMove({ change_pct: null }), { value: null, text: "–" });
});

test("LIVE7A-015 / LIVE7A-024: after the bell the count is the day's; the index's last close is there on every plan", async () => {
  const { liveRows } = await import("../src/lib/breadthTable.ts");
  const { liveTitle } = await import("../src/lib/breadthLive.ts");
  const f = (value, prev) => ({ value, prev, change: null });
  const t = { day: "2026-11-11", prev_day: "2026-11-10", adv: f(357, 300), dec: f(142, 190), pct20: f(50, 48), pct50: f(55, 54), pct200: f(60, 60), index: f(23779.3, 23600) };
  const l = { adv: 305, dec: 191, pct20: 51, pct50: 56, pct200: 61, idx: 23865.8 };
  const idx = liveRows(l, t, "NIFTY 500", null).find((r) => r.key === "idx");
  assert.equal(idx.parts[0].before, 23779.3);                                       // Free: no history, the close from today's numbers
  assert.equal(liveRows(l, t, "NIFTY 500", 23779.3).find((r) => r.key === "idx").parts[0].before, 23779.3);
  assert.match(liveRows(l, t, "NIFTY 500", null, true)[0].means, /on the day/);
  assert.match(liveRows(l, t, "NIFTY 500", null)[0].means, /so far today/);
  assert.equal(liveTitle({ as_of: "15:30", state: "final", close: true }), "Today, at the close");
  assert.equal(liveTitle({ as_of: "15:15", state: "final" }), "Today, final at 15:15");
  assert.match(read("src/pages/BreadthPage.tsx"), /header: final \? \(live\.close \? "Close" : `At \$\{live\.as_of\}`\) : "Now"/);
});

test("LIVE7B-002 / LIVE7A-016: one daily count beside Refresh, the fresh AI reads Plans and Account state; none on the market's read", async () => {
  const { refreshesLeft } = await import("../src/lib/usageText.ts");
  const rows = [{ key: "research_ai", label: "Fresh AI reads, refreshes included", used: 10, limit: 60, left: 50, resets: "day" }];
  assert.equal(refreshesLeft({ plan: "Basic", rows }), 50);                         // Account's "10 of 60", not a separate "10 left today"
  assert.equal(refreshesLeft({ plan: "Pro", rows: [{ ...rows[0], limit: null, left: null }] }), null);   // Pro: no count shown, as Plans says
  const stamp = read("src/components/StoredStamp.tsx");
  assert.match(stamp, /const left = counted \? refreshesLeft\(usage\) : null;/);
  const page = read("src/pages/Research.tsx");
  assert.match(page, /onRefresh=\{refreshAI\} counted=\{false\} \/>/);
  assert.match(page, /data-testid="pulse-tone-none"/);
  assert.match(read("src/lib/plans.ts"), /"Fresh AI reads a day, refreshes included \(/);
});

test("LIVE7A-018: Flows' lock names what that page locks; Plans names the flow history", async () => {
  const { gateFor, featureName, lockWhat } = await import("../src/lib/gates.ts");
  const { lockWords } = await import("../src/lib/lockText.ts");
  const g = gateFor("/invest/flows");
  assert.equal(lockWords(lockWhat("/invest/flows", g.feature), "Basic", "Free", g.whole),
    "Basic adds each recorded day's FII and DII net buying, as a table and a chart. Everything else here is on your Free plan.");
  assert.match(featureName("positioning"), /FII\/DII flow history/);
  assert.equal(lockWhat("/trade/positioning", "positioning"), featureName("positioning"));       // Positioning's own lock keeps the plan's row
  assert.match(read("src/components/PageLock.tsx"), /const what = lockWhat\(pathname, gate\.feature\);/);
});

test("LIVE7B-016: Next and Monthly are one choice when they are the same contract", async () => {
  const { expiryChoices } = await import("../src/lib/options.ts");
  const fmt = (d) => d.slice(5);
  // weekly expiries 17 Nov and 23 Nov (the month's last): Next is the monthly
  let c = expiryChoices(["2026-11-17", "2026-11-23", "2026-11-30"].slice(0, 2), "next", fmt);
  assert.deepEqual(c.options.map((o) => o.label), ["Nearest · 11-17", "Next = monthly · 11-23"]);
  assert.equal(c.value, "next");
  c = expiryChoices(["2026-11-17", "2026-11-23"], "month", fmt);
  assert.equal(c.value, "month");
  assert.equal(c.options[1].value, "month");
  // different contracts: three choices
  c = expiryChoices(["2026-11-10", "2026-11-17", "2026-11-24"], "current", fmt);
  assert.deepEqual(c.options.map((o) => o.label), ["Nearest · 11-10", "Next · 11-17", "Monthly · 11-24"]);
  // a date picked elsewhere stays "date"
  assert.equal(expiryChoices(["2026-11-10", "2026-11-17"], "2026-12-29", fmt).value, "date");
});

test("LIVE7B-018: the year a Money page opens on says what it is", async () => {
  const { fyRole } = await import("../src/lib/fy.ts");
  assert.equal(fyRole(2026, 2026), "this year");
  assert.equal(fyRole(2025, 2026), "being filed");
  assert.equal(fyRole(2024, 2026), "");
  assert.match(read("src/pages/money/TaxToolsPage.tsx"), /fyRole\(x\.fy, current\) \? ` \(\$\{fyRole\(x\.fy, current\)\}\)` : ""/);
  assert.match(read("src/pages/SpaceHomes.tsx"), /\$\{year\.label\} is the year being filed\./);
});

test("LIVE7B-019: an upload's day is India's day wherever it is read", async () => {
  const { ago, asOf } = await import("../src/lib/format.ts");
  const at = "2026-10-10T20:57:00Z";                                                // 11 Oct, 02:27 IST (10 Oct in UTC, this run's zone)
  assert.equal(ago(at), "11 Oct 2026");                                             // over a week before the unit clock's 28 Oct
  assert.match(asOf(at), /^11 Oct 2026, 02:27/);
});
