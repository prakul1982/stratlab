// Lane fix9: the LIVE9A review's findings on Mood, plans, calendars, flows, breadth and the public theme pages.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { leftWord, decksWord } = await import("../src/lib/usageText.ts");
const { pulseBeingWritten, PULSE_AI_TRIES } = await import("../src/lib/pulseMood.ts");
const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

// ---------- LIVE9A-003: a Free account's earlier counts are said as such ----------
test("the Refresh note says until when a Free account keeps its earlier daily reads", () => {
  const grace = { plan: "Free", rows: [], grace: { until: "2026-11-26T18:30:00+00:00", reads_after: 5, decks_after: 0 } };
  assert.equal(leftWord(58, grace), "58 left today (5 a day from 27 Nov)");
  assert.equal(leftWord(0, grace), "None left today (5 a day from 27 Nov)");
  assert.equal(leftWord(4, { plan: "Basic", rows: [] }), "4 left today");
  assert.match(src("components/StoredStamp.tsx"), /leftWord\(left \?\? 0, usage\)/);
});

test("the theme's download buttons say the month's decks used, and a grace deck is said as one", () => {
  const grace = { plan: "Free", rows: [], grace: { until: "2026-11-26T18:30:00+00:00", reads_after: 5, decks_after: 0 } };
  assert.equal(decksWord(0, 1, grace), "Decks this month: 0 of 1 (the sample deck only from 27 Nov)");
  assert.equal(decksWord(2, 5, { plan: "Basic", rows: [] }), "Decks this month: 2 of 5");
  assert.equal(decksWord(3, null, null), null);                // Pro: no monthly count
  assert.equal(decksWord(0, 0, null), null);                   // Free: the locked button says it
  assert.match(src("components/ThemeDive.tsx"), /data-testid="decks-left"/);
});

// ---------- LIVE9A-001/002: a previous session's read is never shown as the current one ----------
test("a mood read behind the index levels is titled and headed with its own session", () => {
  const card = src("pages/PulseMood.tsx");
  assert.match(card, /The mood · \$\{day\(m\.session\)\} session/);
  assert.match(card, /On \$\{day\(m\.session\)\}: \$\{m\.headline\}/);
  // the note saying the new session's read is under way comes before the headline
  assert.ok(card.indexOf('data-testid="pulse-mood-behind"') < card.indexOf('data-testid="pulse-mood"'));
});

test("the volatility table dates each level and the calendar drops past days", () => {
  const card = src("pages/PulseMood.tsx");
  assert.match(card, /header: "As of", cell: \(x\) => sessionWord\(x\.day/);
  assert.match(card, /ahead\(c\.results, \(r\) => r\.date\)/);
  assert.match(src("pages/Research.tsx"), /<CalendarTable c=\{mood\.calendar\} today=/);
});

// ---------- LIVE9A-008: the headlines read is asked again, never held open ----------
test("a read another visit is writing is asked again a few times", () => {
  assert.ok(pulseBeingWritten("The read is being written now. It fills in here in a moment."));
  assert.ok(!pulseBeingWritten("The AI is busy"));
  assert.ok(PULSE_AI_TRIES >= 4);
  assert.match(src("pages/Research.tsx"), /pulseBeingWritten\(\(e as Error\)\.message\) && tries < PULSE_AI_TRIES/);
});

// ---------- LIVE9A-031: one Mood title ----------
test("the Mood page keeps one title for both markets", async () => {
  const { PULSE_TITLE } = await import("../src/lib/pulseMood.ts");
  assert.equal(PULSE_TITLE, "Market mood");
  assert.doesNotMatch(src("pages/Research.tsx"), /How the market feels today/);
});

// ---------- LIVE9A-016: breadth rows even, shares plain, (i) inline ----------
test("breadth: the alert is in the card head, shares are plain, the (i) keeps to its word", async () => {
  const { partTone } = await import("../src/lib/breadthTable.ts");
  assert.equal(partTone({ tone: "share" }, 75), undefined);
  assert.equal(partTone({ tone: "share" }, 33.2), undefined);
  assert.equal(partTone({ tone: "up" }, 10), "k-up");
  const page = src("pages/BreadthPage.tsx");
  assert.match(page, /actions=\{!locked \? <BreadthAlertButton group=\{group\} \/> : undefined\}/);
  assert.doesNotMatch(page, /extra=\{r\.key === "p50"/);
  assert.match(page, /<span className="k-keep">/);
  assert.match(page, /<Box title="Share above averages"/);
  assert.match(src("styles.css"), /\.k-keep \{ white-space: nowrap; \}/);
});

// ---------- LIVE9A-018: the Flows lock said once ----------
test("flows: the lock is the page's own plan note, so the banner isn't added", () => {
  const page = src("pages/FlowsPage.tsx");
  assert.match(page, /<PlanNote>Each recorded day's FII and DII net buying/);
  assert.match(src("components/PageLock.tsx"), /main \.plan-note:not\(\.page-lock\)/);
});

// ---------- LIVE9A-010: the heatmap says its day is the last close while the market trades ----------
test("heatmap: the facts line says the last close while the market is open", async () => {
  const { closesTail } = await import("../src/lib/heatmap.ts");
  assert.equal(closesTail(false), "");
  assert.match(closesTail(true), /^, the last close · the market is open; the map is redrawn after today's close$/);
  assert.match(src("pages/HeatmapPage.tsx"), /Closes of <b>\{asOf\}<\/b>\{closesTail\(open\)\}/);
});

// ---------- LIVE9A-015: US IPO sizes with the underwriters' option, and a missed pricing day ----------
test("US IPOs: the size without the option and the day a filed offering missed are shown", () => {
  const page = src("pages/IposPage.tsx");
  assert.match(page, /sizeText\(\{ \.\.\.r, size: r\.size_base \}\)\} without the underwriters' 15% option/);
  assert.match(page, /Was expected to price \{fmtDate\(r\.expected\)\}/);
});
