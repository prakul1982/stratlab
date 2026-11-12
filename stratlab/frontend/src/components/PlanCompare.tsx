import { Card, CardHead } from "./kit/Card";
import { DataTable, type Column } from "./kit/DataTable";
import { Disclosure } from "./kit/Disclosure";
import type { ReactNode } from "react";
import { Info } from "./ui";
import { ADS, FLAG_GROUP, FLAG_GROUPS, FLAGS, LIMITS, NUMBERS, unlimitedLabel, type Limits, type PlanId } from "../lib/plans";
import { EVERYONE, hasMore, MORE_FLAGS, SHARE_LINKS } from "../lib/planFeatures";

/** Every limit and feature side by side, from the server's plans when signed in; signed out, the
 * same tables from the app's own copy of the limits (R60-012: a visitor comparing plans saw less than a signed-in user). */
export function PlanCompare({ plans }: { plans?: Record<string, Partial<Limits>> }) {
  const lim = (p: PlanId): Limits => ({ ...LIMITS[p], ...(plans?.[p] ?? {}) });
  const num = (p: PlanId, k: keyof Limits) => {
    const v = lim(p)[k] as number | null;
    // Free's one session is a trial of 5 market days: said as a trial in the cell (DK-005)
    // FREE-TIER: no decks of its own on Free: the sample deck (Plans page) shows what one holds
    return v == null ? unlimitedLabel(p, k) : p === "free" && k === "live_limit" ? `${v} (5-market-day trial)` : v === 0 && k === "decks_per_month" ? "0 (a sample deck to download)" : v.toLocaleString("en-IN");
  };
  const shareCell = (p: PlanId) => {
    const v = (plans?.[p] as { share_links_per_month?: number | null } | undefined)?.share_links_per_month;
    const n = v === undefined ? SHARE_LINKS[p] : v;
    return n == null ? "Unlimited" : n.toLocaleString("en-IN");
  };
  const ids: PlanId[] = ["free", "basic", "pro"];
  const names = { free: "Free", basic: "Basic", pro: "Pro" };
  type Row = { id: string; label: string; cell: (p: PlanId) => string };
  // VR1-163: a value's own note ("Unlimited (up to 200 a day)", "1 (5-market-day trial)") is a line under it, not four lines in a 55px column; a long note on a row's name sits behind an (i)
  // VR5-011: a hyphenated word in the note stays whole ("(5-market-day trial)" broke at each hyphen into five lines in the 55px column on a phone)
  const noteOf = (t: string): ReactNode => t.split(/(\S+-\S+)/).map((x, i) => (i % 2 ? <span key={i} className="k-nowrap">{x}</span> : x));
  const valueOf = (v: string): ReactNode => { const m = /^(.+?) (\(.+\))$/.exec(v); return m ? <>{m[1]} <span className="k-sub-line">{noteOf(m[2])}</span></> : v; };
  const nameOf = (v: string): ReactNode => { const m = /^(.+?) \((.{20,})\)$/.exec(v); return m ? <>{m[1]}<Info label={`About ${m[1].toLowerCase()}`}>{m[2].charAt(0).toUpperCase() + m[2].slice(1)}.</Info></> : v; };
  // "What each plan adds" in three parts under subheadings (DI-032: 40-odd rows mixing trading, research and money)
  const flagRows = (g: string) => FLAGS.filter(([f]) => (FLAG_GROUP[f] ?? "research") === g)
    .map(([f, label]) => ({ id: String(f), label, cell: (p: PlanId) => (lim(p).features.includes(f) ? "✓" : "–") }))
    .concat(g === "research" ? MORE_FLAGS.map(([f, label]) => ({ id: f, label, cell: (p: PlanId) => (hasMore(p, f) ? "✓" : "–") })) : []);
  const groups: { id: string; title: string; sub?: string; rows: Row[] }[] = [
    // "Ads" closes the limits: a fact about the plan like the numbers above it (ADS-1)
    { id: "limits", title: "How much", rows: [...NUMBERS.map(([k, label]) => ({ id: String(k), label, cell: (p: PlanId) => num(p, k) })),
      // bet 3: public share links (planFeatures.ts SHARE_LINKS, the server's share_links_per_month), after the other limits
      { id: "share_links_per_month", label: "Public share links a month, of a deep dive or a theme", cell: (p: PlanId) => shareCell(p) },
      { id: "ads", label: "Ads on StratLab (Google ads on public pages and under AI answers)", cell: (p: PlanId) => ADS[p] }] },
    ...FLAG_GROUPS.map((g) => ({ id: `paid-${g.id}`, title: g.title, sub: "What each plan adds", rows: flagRows(g.id) })),
  ];
  const everyone: Row[] = EVERYONE.map((label) => ({ id: label, label, cell: () => "✓" }));
  const columns = (first: string): Column<Row>[] => [
    // the group's name is the heading just above the table: said again as the first column's header it was the same word twice, so it is named for assistive tools only (VR3-016)
    { key: "label", header: <span className="sr-only">{first}</span>, wrap: true, cell: (r) => nameOf(r.label) },
    ...ids.map((p) => ({ key: p, header: names[p], numeric: true, cell: (r: Row) => valueOf(r.cell(p)) })),
  ];
  // one table per group, each with the plan names on top; the header stays in view as the page scrolls past it
  const body = (<>
      {groups.map((g, i) => (
        <div key={g.id} className="k-stack" data-plans-group={g.id}>
          {g.sub && groups[i - 1]?.sub !== g.sub && <h3 className="k-sub">{g.sub}</h3>}
          {g.sub ? <h4 className="k-sub k-small">{g.title}</h4> : <h3 className="k-sub">{g.title}</h3>}
          <DataTable label={`Plans side by side: ${g.sub ? `${g.sub.toLowerCase()}, ` : ""}${g.title.toLowerCase()}`} columns={columns(g.title)} rows={g.rows} rowKey={(r) => r.id} pinHead />
        </div>
      ))}
      {/* the same on every plan: a table like the others, folded so the page stays short (DP1-022: three lists said the same facts) */}
      <div className="k-stack" data-plans-group="all">
        <Disclosure summary={`On every plan (${everyone.length} tools)`}>
          <DataTable label="Plans side by side: on every plan" columns={columns("On every plan")} rows={everyone} rowKey={(r) => r.id} />
        </Disclosure>
      </div>
  </>);
  // R11 (owner, 5 Nov): the comparison is the page's table, open under the cards, not a lone card with one folded line; the cards above
  // carry five short lines each, so the table is where every limit and feature is said (LIVE1C-092's 10,000px page had the long lists three times)
  return (
    <Card id="compare" className="k-compare">
      <CardHead title="Compare the plans" />
      {body}
    </Card>
  );
}
