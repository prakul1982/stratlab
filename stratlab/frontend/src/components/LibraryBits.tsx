import { useEffect, useMemo, useState, type ReactNode } from "react";
import { num, pct } from "../lib/format";
import { opSay, refName } from "../lib/rules";
import type { Cond, Strategy, VerdictKind } from "../lib/types";
import { plainTerms } from "../lib/plainTerms";
import { libMeta, strategyName } from "../lib/libraryList";
import { TOTAL_AFTER_COSTS, TOTAL_HOLD, pricesStop, testedRange } from "../lib/libraryText";
import { checksOf, headTone, trails, unseenLabel } from "../lib/tradeUi";
import { VERDICT_FACT, VerdictBadge } from "./ui";
import { Signed } from "./kit/Signed";
import { Badge } from "./kit/Badge";
import { DataTable, type Column } from "./kit/DataTable";

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
  published_at: string; copies: number;
  /** when this version was tested (a StratLab entry keeps its first published_at through its weekly re-runs) */
  ran_at?: string; mine?: boolean; reported?: boolean; hidden?: boolean;
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
export { CHECK_RESULT, pricesStop, testedRange, TOTAL_AFTER_COSTS, TOTAL_HOLD, TOTAL_NOTE, whereShown } from "../lib/libraryText";

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
export { holdResult, libMeta, libraryTally, liveOptions, marketChoices, marketName, strategyName } from "../lib/libraryList";

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

/** How many rows a phone shows before "Show 12 more" (VR6-024, VR7-004): every row stays in the page (a search engine's phone
 * browser reads them all, and the search box finds them); the rest are hidden by CSS on a phone only. */
export const PHONE_ROWS = 12;

type SortKey = "ret" | "bh" | "gap" | "mdd" | "unseen" | "checks";
const sortValue: Record<SortKey, (e: LibEntry) => number | null> = {
  ret: (e) => shownStats(e).ret, bh: (e) => e.stats.buy_hold, gap: (e) => e.vs_hold?.gap ?? null,
  mdd: (e) => shownStats(e).mdd, unseen: (e) => shownStats(e).unseen,
  checks: (e) => (e.verdict.total ? e.verdict.passed / e.verdict.total + e.verdict.passed / 100 : null),
};

/** The library as a table (TABLES EVERYWHERE, owner 4 Nov: "make tables?" on /library's cards): one row a strategy, the figures
 * in columns that line up and sort by a click on their name, its rules and details one tap away under its row. On a phone each
 * row is a compact card (the name, the return after costs, the gap to buy and hold, the checks), the rest in its details. Drawn
 * by the signed-in library and the public one alike; `actions` is each page's own buttons, `extra` what goes at the end of the
 * details (the signed-in page's report form and plan notes). */
export function LibraryTable({ rows, actions, extra, label = "Strategies", rules = true }: {
  rows: LibEntry[]; actions: (e: LibEntry) => ReactNode; extra?: (e: LibEntry) => ReactNode; label?: string;
  /** the rules in the details (the public list leaves them to the strategy's own page) */
  rules?: boolean;
}) {
  const [by, setBy] = useState<{ key: SortKey; desc: boolean } | null>(null);
  const [pages, setPages] = useState(1);
  useEffect(() => { setPages(1); }, [rows]);
  const sorted = useMemo(() => {
    if (!by) return rows;
    const v = sortValue[by.key];
    // a strategy with no figure (never traded) goes last whichever way the column is sorted
    return [...rows].sort((a, b) => { const x = v(a), y = v(b); return x == null ? (y == null ? 0 : 1) : y == null ? -1 : by.desc ? y - x : x - y; });
  }, [rows, by]);
  const extraRow = new Set(sorted.slice(PHONE_ROWS * pages).map((e) => e.id));
  const fig = (n: number | null, tone = true) => (n == null ? "–" : tone ? <Signed value={n} fmt={(v) => pct(v)} /> : pct(n));
  const cols: Column<LibEntry>[] = [
    { key: "name", header: "Strategy", rowHeader: true, wrap: true, cell: (e) => (
      <span className="k-stack k-tight"><b>{strategyName(e)}</b>
        <span className="k-note">By {e.author}{e.copies ? ` · copied ${e.copies} time${e.copies === 1 ? "" : "s"}` : ""}</span>
        {pricesStop(e.range, e.ran_at ?? e.published_at) && <span className="k-note k-warn-text" data-testid="lib-stops">{pricesStop(e.range, e.ran_at ?? e.published_at)}</span>}</span>) },
    { key: "market", header: "Market", wrap: true, cell: (e) => <span className="k-small">{libMeta(e)}</span> },
    { key: "ret", header: TOTAL_AFTER_COSTS, numeric: true, sortable: true, up: true, info: TOTAL_NOTE_INFO, cell: (e) => fig(shownStats(e).ret, !trails(e)) },
    { key: "bh", header: TOTAL_HOLD, numeric: true, sortable: true, info: "The total return of simply buying at the start and holding to the end, over the same dates.", cell: (e) => fig(e.stats.buy_hold) },
    { key: "gap", header: "vs hold (pts)", numeric: true, sortable: true, cell: (e) => (e.vs_hold ? <span data-testid="lib-gap"><Signed value={e.vs_hold.gap} fmt={(v) => `${v > 0 ? "+" : ""}${num(v, 1)}`} /></span> : "–") },
    { key: "mdd", header: "Worst fall", numeric: true, sortable: true, cell: (e) => fig(shownStats(e).mdd) },
    { key: "unseen", header: "Unseen period", numeric: true, sortable: true, info: "The total return over the last 30% of the test, the part the strategy wasn't tuned on.", cell: (e) => fig(shownStats(e).unseen) },
    { key: "checks", header: "Checks", wrap: true, sortable: true, cell: (e) => (
      <span className="k-stack k-tight"><VerdictBadge v={e.verdict.verdict} facts label={e.verdict.label} tone={headTone(e)} />
        {!shownStats(e).ran ? <span className="k-note">Not run</span> : checksBeyond(checksOf(e), e.verdict.label) && <span className="k-note">{checksBeyond(checksOf(e), e.verdict.label)}</span>}</span>) },
    { key: "act", header: "", action: true, cell: actions },
  ];
  const details = (e: LibEntry) => (
    <div className="k-stack k-tight lib-details">
      {/* on a phone the figures the compact row leaves out are here, as a table */}
      <table className="k-table lib-mini" aria-label={`More figures for ${strategyName(e)}`}>
        <tbody>
          <tr><th scope="row">Market</th><td>{libMeta(e)}</td></tr>
          <tr><th scope="row">{TOTAL_HOLD}</th><td className="k-num">{fig(e.stats.buy_hold)}</td></tr>
          <tr><th scope="row">Worst fall</th><td className="k-num">{fig(shownStats(e).mdd)}</td></tr>
          <tr><th scope="row">{unseenLabel(e)}</th><td className="k-num">{fig(shownStats(e).unseen)}</td></tr>
        </tbody>
      </table>
      {e.range && <p className="k-note lib-line" data-testid="lib-window">Tested {testedRange(e.range)}{e.stats.trades != null ? ` · ${e.stats.trades} trades` : ""}</p>}
      {e.reason && <p className="k-note lib-line lib-reason">{e.reason}</p>}
      {e.description && <p className="k-small lib-about">{plainTerms(e.description)}</p>}
      {rules && <Rules s={e.strategy} />}
      {extra?.(e)}
    </div>
  );
  return (
    <>
      <div className="lib-table">
        <DataTable label={label} rows={sorted} rowKey={(e) => e.id} columns={cols} stack
          rowAttrs={(e): Record<string, string> => (extraRow.has(e.id) ? { className: "lib-extra" } : {})}
          sort={{ key: by?.key ?? "", desc: by?.desc ?? true, onSort: (k) => setBy((b) => (b?.key === k ? { key: k as SortKey, desc: !b.desc } : { key: k as SortKey, desc: true })) }}
          detail={{ label: "Rules and details", render: details }} />
      </div>
      {sorted.length > PHONE_ROWS * pages && (
        <div className="k-row lib-more" data-testid="lib-show-more">
          <span className="k-note">Showing {PHONE_ROWS * pages} of {sorted.length}.</span>
          <button type="button" className="btn quiet sm" onClick={() => setPages((n) => n + 1)}>Show {Math.min(PHONE_ROWS, sorted.length - PHONE_ROWS * pages)} more</button>
        </div>
      )}
    </>
  );
}

const TOTAL_NOTE_INFO = "The total return over the whole test, after brokerage, taxes and slippage: not a yearly rate.";
