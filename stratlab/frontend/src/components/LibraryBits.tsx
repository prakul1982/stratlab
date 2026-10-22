import { num, pct } from "../lib/format";
import { opSay, refName } from "../lib/rules";
import type { Cond, Strategy, VerdictKind } from "../lib/types";
import { VERDICT_FACT } from "./ui";
import { Signed } from "./kit/Signed";
import { Badge } from "./kit/Badge";

/* The pieces of a library strategy that its page behind sign-in and its read-only public page both draw: what an entry
 * looks like, which of its figures exist, and its rules in words. Kept apart from pages/LibraryPage.tsx so the public
 * page doesn't download the signed-in one (and with it the app's account code). */

export interface LibEntry {
  id: string; name: string; question: string; description: string; author: string; market: string;
  instrument: { symbol: string; name?: string } | null; group: { name: string; members?: unknown[] } | null;
  tf: string; side: string; range: { from: string; to: string } | null; strategy: Strategy;
  verdict: { verdict: VerdictKind; headline: string; summary: string; passed: number; total: number; checks?: { id: string; status: string }[];
    /** the server's words for the result, from the checks themselves (R6V-005): the same on the card and the page */
    label?: string; fact_headline?: string; fact_summary?: string };
  /** the return after costs beside buy and hold over the same period, in percent (gap < 0: behind buy and hold) */
  vs_hold?: { ret: number; hold: number; gap: number } | null;
  stats: { ret: number | null; buy_hold: number | null; mdd: number | null; trades: number | null; unseen: number | null };
  published_at: string; copies: number; mine?: boolean; reported?: boolean; hidden?: boolean;
  /** StratLab's own entries: run by StratLab through its own backtest and verdict. */
  official?: boolean; badge?: string;
  /** false when the experiment never traded: its return, fall and unseen result are "not run", not 0.0% */
  ran?: boolean;
  /** one line for why the verdict is what it is, from the verdict's own checks */
  reason?: string | null;
}

/** The figures a card shows: all of them when the experiment traded, and "–" for the ones that need trades when it didn't. */
export const shownStats = (e: LibEntry) => {
  const ran = e.ran !== false && (e.stats.trades ?? 1) > 0;
  return { ran, ret: ran ? e.stats.ret : null, unseen: ran ? e.stats.unseen : null, mdd: ran ? e.stats.mdd : null, buy_hold: e.stats.buy_hold };
};

import { TOTAL_NOTE } from "../lib/libraryText";
export { CHECK_RESULT, testedRange, TOTAL_AFTER_COSTS, TOTAL_HOLD, TOTAL_NOTE, whereShown } from "../lib/libraryText";

/** The verdict filter, in the words of the checks rather than a judgement of the strategy (R5O-014). */
// the filter says what "passed" is about: the checks test whether a result holds up, not whether it beat buying and
// holding (R47-010: "Passed the checks" read as "a good strategy" beside cards that trail buy and hold); and a strategy
// with a warning or a check not run is in it too, so it says what holds for all of them (R80-012)
export const VERDICTS: [string, string][] = [["", "Any result"],
  ...(Object.entries(VERDICT_FACT) as [string, string][]).map(([v, l]): [string, string] => [v, v === "edge" ? "No check failed" : l])];

/** What the checks test, said once on a card whose strategy passed them but trails buy and hold (R47-010). */
export const CHECKS_NOT_HOLD = "The checks test whether the result holds up, not whether it beat buying and holding.";

/** The checks line under the badge, without what the badge already says ("3 of 4 checks run · all 3 passed" twice, R47-016). */
export function checksBeyond(line: string, label: string | null | undefined): string {
  if (!label) return line;
  if (line.startsWith(label)) return line.slice(label.length).replace(/^\s*·\s*/, "");
  // a badge that already gives the count ("3 of 4 checks run · 2 passed") beside "3 of 4 checks run · 2 passed · nearby
  // settings not run": only what it doesn't say is left (R48-005)
  if (/\bpassed\b/i.test(label)) {
    const m = /^\d+ of \d+ checks run · (?:all )?\d+ passed(?: · (.*))?$/.exec(line);
    if (m) return m[1] ?? "";
  }
  return line;
}

export { checksOf, headTone, trails, unseenLabel } from "../lib/tradeUi";

/** The return beside buy and hold, as the notebook's verdict says it (R5O-014). */
/** A plain badge beside the checks badge when the strategy trails buy and hold, so "Passed" never reads as "beat the market". */
export function BehindHold({ e }: { e: LibEntry }) {
  const h = e.vs_hold;
  if (!h || h.gap > -0.05) return null;
  return <Badge tone="plain" dot={false}>Behind buy and hold by {num(Math.abs(h.gap), 1)} points</Badge>;
}

export function HoldLine({ e }: { e: LibEntry }) {
  const h = e.vs_hold;
  if (!h) return null;
  const gap = Math.abs(h.gap);
  return (
    <p className="k-note lib-hold" data-testid="lib-hold">
      <Signed value={h.ret} fmt={(v) => pct(v)} /> {TOTAL_NOTE} against <Signed value={h.hold} fmt={(v) => pct(v)} /> total for buying and holding over the same dates:{" "}
      {gap < 0.05 ? "about the same." : <b>{num(gap, 1)} points {h.gap < 0 ? "behind" : "ahead"}.</b>}
    </p>
  );
}

const line = (c: Cond) => `${refName(c.l)} ${opSay(c.op)} ${refName(c.r)}`;

/** A strategy's rules, one line each: buy when, sell when, short when, cover when, and its stop. */
export function Rules({ s }: { s: Strategy }) {
  const parts: [string, Cond[]][] = [["Buy when", s.entry], ["Sell when", s.exit], ["Short when", s.shortEntry ?? []], ["Cover when", s.shortExit ?? []]];
  return (
    <div className="k-stack k-tight k-small">
      {parts.filter(([, cs]) => cs?.length).map(([label, cs]) => (
        <span key={label}><b>{label}</b> {cs.map(line).join(label === "Sell when" || label === "Cover when" || s.entryJoin === "any" ? " or " : " and ")}</span>
      ))}
      {s.risk?.sl ? <span className="k-muted">Stop {s.risk.sl}{s.risk.stopType === "points" ? " points" : s.risk.stopType === "atr" ? "× ATR" : s.risk.stopType === "swing" ? " candles (swing)" : "%"}{s.risk.tgt ? ` · target ${s.risk.tgt}${s.risk.tgtType === "r" ? "R" : s.risk.tgtType === "points" ? " points" : "%"}` : ""}</span> : null}
    </div>
  );
}
