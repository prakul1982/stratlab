import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, safeHref, fmtDate, marketTz } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { REGION_NAME, useRegion, type Region } from "../lib/research";
import { RegionSwitch } from "../components/Research";
import { Info } from "../components/ui";
import { Earlier } from "../components/Earlier";
import { Badge, Card, CardHead, CheckField, EmptyState, ErrorState, Field, PageHeader, Seg, Skeleton, StockPicker } from "../components/kit";

/* /research/results: the dates companies have called their board meetings to consider results (or, in the US, set for
 * their quarterly results), week by week, for your stocks or every company, and the figures once they are filed. */

interface ResultNumber { label: string; value: string }
export interface ResultRow {
  region: Region; symbol: string; name: string | null; date: string; when: string | null; purpose: string; url: string | null;
  mine?: boolean; out?: { at: string; title: string; url: string | null; numbers: ResultNumber[] } | null;
}
interface ResultsView {
  region: Region; scope: "mine" | "all"; today: string; updated_at: string | null; more: number; mine_count: number; alerts: boolean; note: string;
  weeks: { label: string; from: string; to: string; rows: ResultRow[] }[];
}

/** "Thu 15 Oct", from an ISO date, without the browser's time zone moving it a day. */
export function resultDay(iso: string) {
  return fmtDate(iso.slice(0, 10), { weekday: true, year: false });
}

function ResultLine({ r, showMine }: { r: ResultRow; showMine: boolean }) {
  return (
    <div className="inv-row">
      <span className="k-row">
        <Link className="btn quiet sm" to={`/research/${r.region}/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>
        {r.name && <span className="k-small k-muted">{r.name}</span>}
        {showMine && r.mine && <Badge tone="plain" dot={false}>Yours</Badge>}
      </span>
      <span className="k-small">{r.purpose}{r.when ? `, ${r.when}` : ""}</span>
      {r.out && (
        <span className="k-small">
          Results filed {resultDay(r.out.at)}{r.out.url ? <>: <a className="link" href={safeHref(r.out.url)} target="_blank" rel="noopener noreferrer">{r.out.title} ↗</a></> : `: ${r.out.title}`}
          {r.out.numbers.length > 0 && <span className="k-muted"> · {r.out.numbers.map((n) => `${n.label} ${n.value}`).join(" · ")} (as stated)</span>}
        </span>
      )}
    </div>
  );
}

export function ResultsPage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const scope = params.get("scope") === "all" ? "all" : "mine";
  const { fail, notify } = useApp();
  const [q, setQ] = useState("");
  const [data, setData] = useState<ResultsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let live = true;
    setError(null);
    const t = setTimeout(() => {
      const qs = new URLSearchParams({ region, scope, q: scope === "all" ? q : "" });
      api<ResultsView>(`/research/results?${qs}`).then((x) => live && setData(x)).catch((e) => live && setError((e as Error).message));
    }, q ? 300 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [region, scope, q, tries]);

  const setScope = (s: string) => { const p = new URLSearchParams(params); p.set("scope", s); setParams(p, { replace: true }); };
  const toggleAlerts = async () => {
    if (!data) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/results/alerts", { method: "PUT", body: { on: !data.alerts } });
      setData({ ...data, alerts: r.alerts });
      notify(r.alerts ? "You'll get a message on the morning of each results day for your stocks, and when the results are filed." : "Results messages off.");
    } catch (e) { fail(e); }
  };
  const empty = data && data.weeks.every((w) => w.rows.length === 0);

  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/results")} title="Results this week and next"
        lede={region === "IN" ? "Board meetings companies have called to consider their financial results, from their filings with the exchange."
          : "The dates US companies have set for their quarterly results, and the earnings release once it's filed."}
        asOf={data?.updated_at} asOfLabel="Updated" asOfTz={marketTz(region)} />
      <div className="k-toolbar">
        <RegionSwitch region={region} setRegion={setRegion} />
        <Seg label="Which companies" value={scope} onChange={setScope} options={[{ value: "mine", label: "My stocks" }, { value: "all", label: "All companies" }]} />
      </div>
      {(scope === "all" || data) && (
        <Card>
          {scope === "all" && (
            <Field label="Find a company">
              {(id) => <StockPicker id={id} market={region} onText={setQ} onPick={(s) => setQ(s)} placeholder="Find a company, like TCS or Infosys" />}
            </Field>
          )}
          {data && (
            <CheckField checked={data.alerts} onChange={toggleAlerts}
              label={<>Message me on the morning of a results day for my stocks, and when the results are filed
                <Info>Sent by phone notification or Telegram, whichever you set up in Settings. If you get the My Stocks newsletter, it lists the week's results dates too.</Info></>} />
          )}
        </Card>
      )}
      {error && <ErrorState title="The results calendar couldn't be opened" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>}
      {!data && !error && <Card><Skeleton label="Opening the results calendar" lines={4} /></Card>}
      {data && empty && (
        <Card>
          <EmptyState title={scope === "mine" ? "None of your stocks has a results date yet" : "No results dates found"}
            action={scope === "mine" ? { label: "See all companies", onClick: () => setScope("all") } : undefined}>
            {scope === "mine"
              ? (data.mine_count ? `None of your ${REGION_NAME[region]} stocks has a results date in these two weeks.` : `You have no ${REGION_NAME[region]} stocks yet: they come from your watchlist, notebooks and paper sessions.`)
              : q ? "No company by that name has a results date in these two weeks." : "No results dates announced for these two weeks yet."}
          </EmptyState>
        </Card>
      )}
      {data && !empty && data.weeks.map((w) => {
        const days = [...new Set(w.rows.map((r) => r.date))];
        const ahead = days.filter((d) => d >= data.today), past = days.filter((d) => d < data.today);     // the days gone by fold away
        const day = (d: string) => (
          <div key={d} className="inv-day">
            <span className="k-eyebrow">{resultDay(d)}{d === data.today ? " · today" : ""}</span>
            <div className="inv-rows">{w.rows.filter((r) => r.date === d).map((r) => <ResultLine key={`${r.symbol}-${r.date}`} r={r} showMine={scope === "all"} />)}</div>
          </div>
        );
        return (
          <Card key={w.label}>
            <CardHead title={w.label} actions={<span className="k-note">{resultDay(w.from)} to {resultDay(w.to)}</span>} />
            {days.length === 0 ? <span className="k-small k-muted">Nothing announced for this week yet.</span>
              : ahead.length ? ahead.map(day) : <span className="k-small k-muted">Nothing left this week.</span>}
            <Earlier label="Earlier this week" count={w.rows.filter((r) => r.date < data.today).length} className="in-card">
              {past.map(day)}
            </Earlier>
          </Card>
        );
      })}
      {data && data.more > 0 && <p className="k-note">And {data.more} more. Find a company by name to narrow the list.</p>}
      {data && <p className="k-note inv-text">{data.note}{data.updated_at ? ` Updated ${ago(data.updated_at)}.` : ""}</p>}
    </div>
  );
}
