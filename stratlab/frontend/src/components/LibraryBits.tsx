import { opSay, refName } from "../lib/rules";
import type { Cond, Strategy, VerdictKind } from "../lib/types";

/* The pieces of a library strategy that its page behind sign-in and its read-only public page both draw: what an entry
 * looks like, which of its figures exist, and its rules in words. Kept apart from pages/LibraryPage.tsx so the public
 * page doesn't download the signed-in one (and with it the app's account code). */

export interface LibEntry {
  id: string; name: string; question: string; description: string; author: string; market: string;
  instrument: { symbol: string; name?: string } | null; group: { name: string; members?: unknown[] } | null;
  tf: string; side: string; range: { from: string; to: string } | null; strategy: Strategy;
  verdict: { verdict: VerdictKind; headline: string; summary: string; passed: number; total: number; checks?: { id: string; status: string }[] };
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

export const VERDICTS: [string, string][] = [["", "Any verdict"], ["edge", "Likely a real edge"], ["mixed", "Mixed evidence"], ["not_enough", "Not enough evidence"], ["luck", "Probably luck"], ["no_edge", "No edge here"]];

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
