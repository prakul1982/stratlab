import { num, pct } from "../lib/format";
import { opSay, refName } from "../lib/rules";
import { CHECK_NAMES, checksLine } from "../lib/tradeUi";
import type { Cond, Strategy, VerdictKind } from "../lib/types";
import { VERDICT_FACT } from "./ui";
import { Signed } from "./kit/Signed";

/* The pieces of a library strategy that its page behind sign-in and its read-only public page both draw: what an entry
 * looks like, which of its figures exist, and its rules in words. Kept apart from pages/LibraryPage.tsx so the public
 * page doesn't download the signed-in one (and with it the app's account code). */

export interface LibEntry {
  id: string; name: string; question: string; description: string; author: string; market: string;
  instrument: { symbol: string; name?: string } | null; group: { name: string; members?: unknown[] } | null;
  tf: string; side: string; range: { from: string; to: string } | null; strategy: Strategy;
  verdict: { verdict: VerdictKind; headline: string; summary: string; passed: number; total: number; checks?: { id: string; status: string }[] };
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

/** The verdict filter, in the words of the checks rather than a judgement of the strategy (R5O-014). */
export const VERDICTS: [string, string][] = [["", "Any result"], ...(Object.entries(VERDICT_FACT) as [string, string][])];

/** "3 of 4 checks passed · nearby settings not run": which check didn't run, by name. */
export const checksOf = (e: LibEntry) => checksLine(e.verdict.passed, e.verdict.total,
  (e.verdict.checks ?? []).filter((c) => c.status === "skip").map((c) => CHECK_NAMES[c.id] ?? c.id));

/** The return beside buy and hold, as the notebook's verdict says it (R5O-014). */
export function HoldLine({ e }: { e: LibEntry }) {
  const h = e.vs_hold;
  if (!h) return null;
  const gap = Math.abs(h.gap);
  return (
    <p className="k-note lib-hold" data-testid="lib-hold">
      <Signed value={h.ret} fmt={(v) => pct(v)} /> after costs against <Signed value={h.hold} fmt={(v) => pct(v)} /> for buying and holding:{" "}
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
        <span key={label}><b>{label}</b> {cs.map(line).join(s.entryJoin === "any" && label !== "Sell when" ? " or " : " and ")}</span>
      ))}
      {s.risk?.sl ? <span className="k-muted">Stop {s.risk.sl}{s.risk.stopType === "points" ? " points" : s.risk.stopType === "atr" ? "× ATR" : "%"}{s.risk.tgt ? ` · target ${s.risk.tgt}${s.risk.tgtType === "r" ? "R" : s.risk.tgtType === "points" ? " points" : "%"}` : ""}</span> : null}
    </div>
  );
}
