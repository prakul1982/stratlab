import type { CheckStatus } from "./types";
import { currencySymbol, signCls } from "./format";

/** A paper session's own page: options sessions at /options/s/<id>, a notebook signal's at /trade/signals/<id>, the rest at
 * /paper/<id> (R7T-011: an options session opened at /paper/<id> crashed the page). */
export function sessionPath(s: { id: string; kind?: string | null; instrument?: { type?: string | null; signal?: boolean } | null }): string {
  if (s.kind === "options" || s.instrument?.type === "OPTIONS") return `/options/s/${s.id}`;
  if (s.kind === "signal" || s.instrument?.signal) return `/trade/signals/${s.id}`;
  return `/paper/${s.id}`;
}

/** The class for a gain or a loss in the kit's colours (green up, red down, nothing at zero or when unknown). */
export const upDown = (v: number | null | undefined): string => signCls(v);

/** The kit Badge tone for a check's status. */
/** Every verdict runs the same four checks (unseen data, nearby settings, bad-luck drawdown, enough trades). */
export const CHECKS = 4;

/** "3 of 4 checks run · all 3 passed", "4 of 4 checks run · 2 passed": counted out of the same four everywhere (a check can be
 * skipped, say nearby settings on a group of stocks, but it is still one of the four), in the library's words (R60-002: a
 * card read "3 of 4 checks run · all 3 passed" over "3 of 4 checks passed · 1 not run"). `run` is how many weren't skipped. */
export function checksLine(passed: number, run: number, notRun?: string[]): string {
  if (run <= 0) return "No checks could be run";
  const skipped = Math.max(0, CHECKS - run);
  // with the names of the checks that didn't run, say which (R5O-014: "1 not run" alone left people guessing)
  const which = notRun?.length === skipped && skipped ? ` · ${notRun.join(" and ")} not run` : "";
  return `${run} of ${CHECKS} checks run · ${passed >= run ? `all ${run} passed` : `${passed} passed`}${which}`;
}

/** The checks as a count for a table cell, out of the same four: "2 of 4", "3 of 4 (1 not run)" (DA-031: the compare table's
 * cell read the verdict's sentence "4 of 4 checks run · 2 passed"). */
export function checksCell(passed: number, run: number): string {
  const skipped = Math.max(0, CHECKS - Math.max(0, run));
  return `${Math.min(passed, CHECKS)} of ${CHECKS}${skipped ? ` (${skipped} not run)` : ""}`;
}

/** The checks line under a headline, or "" when the headline already says it (R61-007: "…; 3 of 4 checks run · all 3 passed."
 * over "3 of 4 checks run · all 3 passed" on the landing page's cards). */
export function underHeadline(line: string, headline: string | null | undefined): string {
  const lead = line.split(" · ")[0].toLowerCase();
  return headline && headline.toLowerCase().includes(lead) ? "" : line;
}

/** A verdict's headline as two lines: the comparison with buying and holding as the headline, and the checks as their own
 * line under it. The stored headline joins them with "; " ("44.5 points ahead of buy and hold after costs; 4 of 4 checks run ·
 * 2 passed."), which at headline size ran to four or five lines and fused two messages (DA-020). */
export function splitHeadline(headline: string): { main: string; checks: string } {
  const i = headline.indexOf("; ");
  if (i < 0) return { main: headline, checks: "" };
  const checks = headline.slice(i + 2).trim();
  return { main: headline.slice(0, i).replace(/\.$/, "") + ".", checks: checks.charAt(0).toUpperCase() + checks.slice(1) };
}

/** A verdict's summary as short lines, one sentence each (DA-028: a group's summary, with its notes, was one wall of text). A
 * sentence ends at a full stop before a capital letter or a sign, so "62.5 points" and "+4.1%" stay whole. */
export function summaryLines(summary: string | null | undefined): string[] {
  return (summary ?? "").split(/(?<=[.!?])\s+(?=[A-Z0-9+−-])/).map((x) => x.trim()).filter(Boolean);
}

/** The summary lines the Experiment page's verdict block keeps (VR1-062: the verdict was said four times: headline, caption, a paragraph and
 * the figures again). The sentence that restates both returns ("The strategy returned -4.8% after costs, less than buying and holding over the
 * same period (+50.2%).") goes, as the headline gives the gap and The numbers the two figures; the plain "lost money" sentence goes when the line
 * under the headline already says it. Everything else (too few trades, the yearly rate, notes) stays. */
export function heroSummary(summary: string | null | undefined, caption = ""): string[] {
  const saysLost = /lost money after costs/i.test(caption);
  return summaryLines(summary).filter((l) => !/^The strategy returned .+ (more than|less than|about the same as) buying and holding over the same period \(.+\)\.$/.test(l)
    && !(saysLost && l === "After costs, the strategy lost money over the period."));
}

/** A run's badge words where the plain "Passed the checks" would overstate it: the count when some checks didn't pass
 * (R62-003: "Passed the checks" over a verdict of "4 of 4 checks run · 2 passed"), as short as the other badges beside it in
 * the runs table ("Too few trades" beside "4 of 4 checks run · 2 passed", DA-031). Undefined keeps the badge's own words. */
export function badgeLabel(v: { verdict: string; passed: number; total: number }): string | undefined {
  return v.verdict === "edge" && v.passed < v.total ? `Passed ${v.passed} of ${CHECKS} checks` : undefined;
}

/** A strategy that lost money after costs: no pass count is headlined for it (R16-006); its checks are shown for reference. */
export const LOST_CHECKS = "Lost money after costs · its checks are shown for reference";   // the same words as the share card (R58-009): the checks did run
export const lostMoney = (verdict?: string, ret?: number | null) => verdict === "no_edge" && ret != null && ret <= 0;

/** "months" when the unseen part (the last 30% of the test range) spans under a year, else "years": a 6-month test has no
 * unseen years. Without a range, "years". */
export function unseenWord(range?: { from: string; to: string } | null): "months" | "years" {
  const days = range ? (Date.parse(range.to.slice(0, 10)) - Date.parse(range.from.slice(0, 10))) / 86_400_000 : NaN;
  return days * 0.3 < 365 ? "months" : "years";
}

/** The checks' plain names, for "nearby settings not run". */
export const CHECK_NAMES: Record<string, string> = { unseen: "unseen years", nearby: "nearby settings", shuffle: "bad-luck fall", sample: "enough trades" };

/** The parts of a library entry its verdict's words are worked out from. */
type Held = { range: { from: string; to: string } | null; stats: { ret: number | null }; vs_hold?: { gap: number } | null;
  verdict: { verdict: string; passed: number; total: number; checks?: { id: string; status: string }[] } };

/** The unseen figure's name, by the span it covers: "Unseen months" on a 6-month test, "Unseen years" on a long one. */
export const unseenLabel = (e: { range: { from: string; to: string } | null }) => `Unseen ${unseenWord(e.range)}`;

/** The checks' count, in the words of the verdict's label ("3 of 4 checks run · all 3 passed · nearby settings not run"), so the
 * list, the card and the page's headline count the same way. */
export function checksOf(e: Held): string {
  if (lostMoney(e.verdict.verdict, e.stats.ret)) return LOST_CHECKS;
  const notRun = (e.verdict.checks ?? []).filter((c) => c.status === "skip").map((c) => (CHECK_NAMES[c.id] ?? c.id).replace("years", unseenWord(e.range)));
  const run = e.verdict.total, passed = e.verdict.passed;
  return checksLine(passed, run, notRun);
}

/** Whether the rules trail buy and hold: a result behind it is not shown as a win. */
export const trails = (e: Held) => !!e.vs_hold && e.vs_hold.gap <= -0.05;

/** The headline's colour class: a verdict that trails buy and hold is not blue. */
export const headTone = (e: Held) => (trails(e) && e.verdict.verdict === "edge" ? "mixed" : e.verdict.verdict);

export const checkTone =(s: CheckStatus | "pass" | "warn" | "fail" | "skip"): "ok" | "warn" | "plain" => (s === "pass" ? "ok" : s === "fail" ? "warn" : "plain");

/** "Every trade"'s caption and the trades it has no row for (R11C-003: "200 closed + 10 still open" under a header of 250
 * trades, and rows that summed to $301,405 against a total of $279,150). Only the newest closed trades are kept as rows, so
 * the caption says "Newest 200 of 250 closed", and the P&L of the rest is the total less the rows: the rows and one line
 * for the rest add up to the total. */
export function tradeListFacts(e: { trades: { exit_t?: string | null; pnl: number }[]; stats: { n: number; pnl?: number | null };
  trimmed_pnl?: number; omitted_pnl?: number }) {
  const open = e.trades.filter((t) => !t.exit_t).length;
  const closed = e.trades.length - open;
  const n = Math.max(e.stats.n ?? closed, closed);
  const hidden = n - closed;
  const listed = e.trades.reduce((sum, t) => sum + (t.pnl || 0), 0);
  const total = e.stats.pnl ?? listed + (e.omitted_pnl ?? 0) + (e.trimmed_pnl ?? 0);
  const count = (k: number) => k.toLocaleString("en-IN");
  const still = open ? ` + ${count(open)} still open` : "";
  return {
    open, closed, hidden, total, hiddenPnl: hidden ? total - listed : 0,
    caption: hidden ? `Newest ${count(closed)} of ${count(n)} closed${still}` : `${count(closed)} closed${still}`,
  };
}

/* ---------- signal sessions (review 5b) ---------- */

/** A signal session that can still take signals, or would once it is attached again: "paused" is the server's word for a
 * session saved as running that no container is running right now. Either is stopped before it can be deleted. */
export const stoppable = (status: string) => status === "running" || status === "paused";

/** The test signal's quantity as typed: a number above 0 (the server's own rule), or why not. Nothing is ever sent as 1
 * in its place. */
export function testQty(text: string): { qty: number } | { error: string } {
  const t = text.replace(/,/g, "").trim();
  const v = Number(t);
  if (!t || !Number.isFinite(v)) return { error: "Enter the test quantity as a number, for example 1." };
  if (v <= 0) return { error: "The test quantity has to be above 0." };
  return { qty: v };
}

/** A test signal's own id, so a second send of the same click is logged as a repeat and never fills twice (the server
 * takes up to 64 letters, digits or . _ : -). */
export function testSignalId(now = Date.now(), rnd = Math.random()): string {
  return `page-${now.toString(36)}-${Math.floor(rnd * 36 ** 6).toString(36).padStart(6, "0")}`;
}

/** The paper capital box of a new signal session, in the instrument's currency (the market's until one is picked): the
 * symbol beside it and the server's default as the example (10,00,000 rupees; 10,000 of anything else). */
export function capitalField(currency: string | null | undefined): { unit: string; placeholder: string } {
  const c = currency || "INR";
  return { unit: currencySymbol(c), placeholder: c === "INR" ? "10,00,000" : "10,000" };
}

/** The account's day figure on a paper session's page (options, group). A running session shows today's P&L (closed trades plus the
 * open one); a stopped or paused one isn't trading today, so its last saved day isn't "Today": the server sends null
 * when that day is gone, and the label never says "Today". */
export function dayStat(running: boolean, status: string, today: number | null | undefined, openNet: number):
  { label: string; value: number | null; text: string | null } {
  if (running) return { label: "Today", value: (today ?? 0) + openNet, text: null };
  const word = status === "paused" ? "paused" : "stopped";
  if (today == null) return { label: "Day's P&L", value: null, text: `None today: the session is ${word}` };
  return { label: `Day's P&L, up to the ${status === "paused" ? "pause" : "stop"}`, value: today + openNet, text: null };
}

/** Why a group trade's quantity is smaller than its slot: the pot's cash left free when it opened (R38-003). */
export function qtyNote(t: { cash_short?: boolean }): string | null {
  return t.cash_short ? "Sized to the cash left free" : null;
}

/** The sessions not running, paused apart from stopped ("1 paused", "2 stopped"), as Paper trading lists them (R84-013). */
export function notRunning(rows: { status?: string | null }[]): string[] {
  const paused = rows.filter((r) => r.status === "paused").length;
  const stopped = rows.filter((r) => r.status !== "running" && r.status !== "paused").length;
  return [paused ? `${paused} paused` : "", stopped ? `${stopped} stopped` : ""].filter(Boolean);
}
