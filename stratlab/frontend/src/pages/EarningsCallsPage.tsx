import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { SCOPE_OPTIONS } from "../lib/companyScope";
import { useCompanyScope } from "../lib/useCompanyScope";
import { eyebrowOf } from "../lib/eyebrow";
import { fmtDate, marketTz, safeHref } from "../lib/format";
import { useRegion, type Region } from "../lib/research";
import { RegionSwitch } from "../components/Research";
import { Card, DataTable, EmptyState, ErrorState, PageHeader, PlanNote, Seg, Skeleton, type Column } from "../components/kit";

/* /research/earnings-calls (f5): the Calendar's "Earnings calls" tab. Every results call and meeting with analysts or investors
 * coming up, India from the companies' own notices to the exchange (date, time and zone as filed, the notice and a webcast or
 * dial-in link when the filing gives one) and the US from the results calendar (the day and the session). "Held" lists the last
 * three weeks with what was filed after each call: its transcript, recording and presentation. Links are only ever the filings'
 * own. Free: this week's calls; Basic: the full calendar, the filters and the feed (plans.py earnings_calls). Facts only. */

export interface CallLink { kind: string; label: string; url: string; filed: string | null }
export interface CallRow {
  id: string; region: Region; symbol: string; name: string; date: string; until: string | null; dates: string[] | null; time: string | null;
  tz: string | null; session: string | null; type: "call" | "meet" | "results"; type_label: string; links: CallLink[]; noticed: boolean; mine: boolean;
}
interface CallsView {
  region: Region; scope: "all" | "mine"; when: "upcoming" | "past"; kind: string; today: string; from: string; to: string; updated_at: string | null;
  matching: number; rows: CallRow[]; more: number; counts: { call: number; meet: number; results: number }; note: string; pending: boolean;
  full: boolean; plan_needed: string | null; mine_count: number;
}

const WHEN = [{ value: "upcoming", label: "Coming up" }, { value: "past", label: "Held" }];
const KINDS = [{ value: "all", label: "Both" }, { value: "call", label: "Earnings calls" }, { value: "meet", label: "Analyst meets" }];

/** "Mon 16 Nov" or "Mon 16 Nov to Wed 18 Nov" for a run of meetings. */
export function callDay(r: Pick<CallRow, "date" | "until">): string {
  const d = fmtDate(r.date, { weekday: true, year: false });
  return r.until && r.until !== r.date ? `${d} to ${fmtDate(r.until, { weekday: true, year: false })}` : d;
}

/** The time as filed with its zone ("16:00 IST"), the US session ("After the close, ET"), or nothing when the filing gives none. */
export function callTime(r: Pick<CallRow, "time" | "tz" | "session">): string | null {
  if (r.time) return `${r.time}${r.tz ? ` ${r.tz}` : ""}`;
  if (r.session) return `${r.session[0].toUpperCase()}${r.session.slice(1)}${r.tz ? `, ${r.tz}` : ""}`;
  return null;
}

function Links({ r }: { r: CallRow }) {
  if (!r.links.length) return <span className="k-muted">–</span>;
  return (
    <span className="calls-links">
      {r.links.map((x) => (
        <a key={x.url} className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">
          {x.label}<span aria-hidden="true"> ↗</span><span className="sr-only">, {r.name} (opens in a new tab)</span>
        </a>
      ))}
    </span>
  );
}

export function EarningsCallsPage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const [scope, setScope] = useCompanyScope();
  const when = params.get("when") === "past" ? "past" : "upcoming";
  const kind = ["call", "meet"].includes(params.get("kind") ?? "") ? params.get("kind")! : "all";
  const [q, setQ] = useState("");
  const [data, setData] = useState<CallsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const set = (k: string, v: string) => { const p = new URLSearchParams(params); if (v && v !== "all" && v !== "upcoming") p.set(k, v); else p.delete(k); setParams(p, { replace: true }); };
  // a plan without the full calendar asks for this week's calls only: the filters would be refused (402), so it asks again without them
  const [teaser, setTeaser] = useState(false);
  const full = !teaser && (data?.full ?? true);
  useEffect(() => {
    let live = true;
    setError(null);
    const t = setTimeout(() => {
      const qs = new URLSearchParams(full ? { region, scope, when, kind, q: q.trim() } : { region });
      for (const [k, v] of [...qs]) if (!v) qs.delete(k);
      api<CallsView>(`/research/earnings-calls?${qs}`).then((x) => { if (live) { setData(x); if (!x.full) setTeaser(true); } })
        .catch((e) => { if (!live) return; if (e instanceof ApiError && e.status === 402) setTeaser(true); else setError((e as Error).message); });
    }, q ? 300 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [region, scope, when, kind, q, tries, full]);

  const tz = marketTz(region);
  const cols: Column<CallRow>[] = [
    { key: "when", header: when === "past" ? "Held" : "When", rowHeader: true, cell: (r) => (
      <span className="calls-when"><span className="nowrap">{callDay(r)}{r.date === data?.today ? " · today" : ""}</span>
        {callTime(r) && <span className="k-sub-line">{callTime(r)}</span>}</span>) },
    { key: "co", header: "Company", wrap: true, cell: (r) => (
      <><Link className="link" to={`/research/${r.region}/${encodeURIComponent(r.symbol)}`}>{r.name}</Link>
        <span className="k-note k-muted"> · {r.symbol}{r.mine ? " · yours" : ""}</span></>) },
    { key: "type", header: "Event", wrap: true, cell: (r) => r.type_label + (r.noticed ? "" : " (from the filing after it)") },
    { key: "links", header: "Links", wrap: true, csv: (r) => r.links.map((x) => `${x.label}: ${x.url}`).join(" | "), cell: (r) => <Links r={r} /> },
  ];

  const lede = region === "IN"
    ? "Results calls and meetings with analysts or investors, from the companies' own notices to the exchange: the day, the time as filed, and the notice and webcast or dial-in link when the filing gives one. After a call, its transcript, recording and presentation once they are filed."
    : "The days US companies report their results and the session they announced, before the open or after the close, with the earnings release once it is filed.";
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/earnings-calls")} title="Earnings calls" lede={lede}
        asOf={data?.updated_at ?? null} asOfPending={!data && !error} asOfTz={tz} info={data?.note} infoLabel="About these dates" />
      <Card label="What to show" className="cal-filters">
        <div className="k-toolbar">
          <RegionSwitch region={region} setRegion={(r: Region) => { setData(null); setRegion(r); }} />
          {full && <Seg label="Show" value={when} onChange={(v) => set("when", v)} options={WHEN} />}
          {full && <Seg label="Companies" value={scope} onChange={(v) => setScope(v)} options={SCOPE_OPTIONS} />}
          {full && region === "IN" && <Seg label="Type" value={kind} onChange={(v) => set("kind", v)} options={KINDS} />}
          {full && <input className="k-input sm" type="search" aria-label="Find a company" placeholder="Find a company" autoComplete="off" value={q} onChange={(e) => setQ(e.target.value)} />}
        </div>
        <p className="k-small k-muted" data-testid="calls-count">
          {!data ? "Reading the calendar…" : `${data.matching.toLocaleString("en-IN")} ${region === "IN" ? "calls and meetings" : "results days"} ${data.when === "past" ? "held" : ""} from ${fmtDate(data.from, { weekday: true, year: false })} to ${fmtDate(data.to, { weekday: true, year: false })}`}
          {data && data.scope === "mine" ? ". Your holdings, watchlist, notebooks and paper sessions." : data ? "." : ""}
        </p>
        {data && !data.full && (
          <div data-testid="calls-locked"><PlanNote>This week's calls, each with its notice and webcast or dial-in link, are on every plan. Every week ahead, the calls already held with their transcript, recording and presentation, the filters and your stocks' calls in your calendar feed are on the {data.plan_needed} plan.</PlanNote></div>
        )}
      </Card>
      {error ? <ErrorState title="The calendar couldn't be read" action={{ label: "Try again", onClick: () => setTries((x) => x + 1) }}>{error}</ErrorState>
        : !data ? <Card><Skeleton label="Reading the calendar" page /></Card>
        : data.pending && !data.rows.length ? (
          <Card><EmptyState title="The first read hasn't finished">The exchange's notices are read each evening after the filings of the day; the calendar fills after that read.</EmptyState></Card>
        ) : (
          <Card label={when === "past" ? "Calls held" : "Calls coming up"} testId="calls-table">
            <DataTable csv="earnings calls" stack label={when === "past" ? "Earnings calls and meetings held" : "Earnings calls and meetings coming up"} columns={cols}
              rows={data.rows} rowKey={(r) => r.id}
              empty={data.scope === "mine" ? "None of your stocks has a call or meeting in these days." : q ? "No company by that name has a call in these days." : "Nothing in these days."} />
            {data.more > 0 && <p className="k-small k-muted">The first {data.rows.length.toLocaleString("en-IN")} are shown; find a company or narrow the type to see the other {data.more.toLocaleString("en-IN")}.</p>}
          </Card>
        )}
    </div>
  );
}
