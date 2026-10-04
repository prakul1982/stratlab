import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";
import { REGION_NAME, saveRegion, savedRegion, type Region } from "../lib/research";
import { ResearchNav } from "../components/Research";
import { ActionLine, KIND_NAME, exDay, type ActionKind, type CorpAction } from "../components/CorpActions";
import { Info, Loading } from "../components/ui";
import { Earlier } from "../components/Earlier";

interface CalendarView {
  region: Region; scope: "mine" | "all"; kind: string; today: string; updated_at: string | null; ahead: CorpAction[]; recent: CorpAction[];
  more: number; mine_count: number; alerts: boolean; kinds: ActionKind[]; ahead_known: boolean; note: string;
}

/** Ex-dates in day groups. */
function DayGroups({ rows, today }: { rows: CorpAction[]; today: string }) {
  const days = [...new Set(rows.map((r) => r.ex_date))];
  return <>{days.map((d) => (
    <div key={d} className="stack" style={{ gap: 8 }}>
      <span className="eyebrow">Ex-date {exDay(d)}{d === today ? " · today" : ""}</span>
      {rows.filter((r) => r.ex_date === d).map((r) => <ActionLine key={r.id} a={r} />)}
    </div>
  ))}</>;
}

/** Ex-dates in day groups, under one heading. */
function Days({ title, rows, today, empty }: { title: string; rows: CorpAction[]; today: string; empty: string }) {
  return (
    <section className="card stack" style={{ gap: 14 }}>
      <h2 className="h3">{title}</h2>
      {rows.length === 0 ? <span className="small muted">{empty}</span> : <DayGroups rows={rows} today={today} />}
    </section>
  );
}

export function CorpActionsPage() {
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("region")?.toUpperCase();
  const [region, setRegionState] = useState<Region>(fromUrl === "US" || fromUrl === "IN" ? fromUrl : savedRegion());
  const scope = params.get("scope") === "all" ? "all" : "mine";
  const kind = params.get("kind") ?? "";
  const { fail, notify } = useApp();
  const [q, setQ] = useState("");
  const [data, setData] = useState<CalendarView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setParam = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p, { replace: true }); };
  const setRegion = (r: Region) => { setRegionState(r); saveRegion(r); setParam("region", r); };

  useEffect(() => {
    let live = true;
    setError(null);
    const t = setTimeout(() => {
      const qs = new URLSearchParams({ region, scope, kind, q: scope === "all" ? q : "" });
      api<CalendarView>(`/research/corp-actions?${qs}`).then((x) => live && setData(x)).catch((e) => live && setError((e as Error).message));
    }, q ? 300 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [region, scope, kind, q]);

  const toggleAlerts = async () => {
    if (!data) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/corp-actions/alerts", { method: "PUT", body: { on: !data.alerts } });
      setData({ ...data, alerts: r.alerts });
      notify(r.alerts ? "You'll get a message when one of your stocks announces a corporate action, and the evening before its ex-date." : "Corporate action messages off.");
    } catch (e) { fail(e); }
  };
  const empty = data && !data.ahead.length && !data.recent.length;

  return (
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region={region} setRegion={setRegion} />
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Corporate actions · {REGION_NAME[region]}</span>
        <h1 className="page-title">Dividends, bonuses and splits</h1>
        <p className="page-sub">{region === "IN"
          ? "Dividends, bonus issues, splits, buybacks, rights issues and demergers by ex-date, as companies announced them to the exchange."
          : "Dividends and splits of US companies you follow, by ex-date. Dates ahead aren't available for the US yet."}</p>
      </div>
      <div className="row wrap" style={{ gap: 12 }}>
        <div className="seg" role="radiogroup" aria-label="Which companies">
          <button role="radio" aria-checked={scope === "mine"} aria-pressed={scope === "mine"} onClick={() => setParam("scope", "mine")}>My stocks</button>
          <button role="radio" aria-checked={scope === "all"} aria-pressed={scope === "all"} onClick={() => setParam("scope", "all")}>All</button>
        </div>
        <select className="input" style={{ flex: "0 1 200px", minHeight: 40 }} value={kind} onChange={(e) => setParam("kind", e.target.value)} aria-label="Kind of action">
          <option value="">Every kind</option>
          {(Object.keys(KIND_NAME) as ActionKind[]).map((k) => <option key={k} value={k}>{KIND_NAME[k]}</option>)}
        </select>
        {scope === "all" && <input className="input" style={{ flex: "1 1 200px", maxWidth: 320 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a company" aria-label="Find a company" />}
      </div>
      {data && (
        <label className="row small" style={{ gap: 8 }}>
          <input type="checkbox" checked={data.alerts} onChange={toggleAlerts} />
          Message me when my stocks announce a corporate action, and the evening before an ex-date
          <Info>Sent by phone notification or Telegram, whichever you set up on the Account page. Your stocks are your watchlist, holdings, notebooks and paper sessions. The My Stocks newsletter lists the week's ex-dates too.</Info>
        </label>
      )}
      {error && <p className="small muted">{error}</p>}
      {!data && !error && <Loading label="Opening the corporate actions calendar" />}
      {data && empty && (
        <div className="card stack" style={{ gap: 10 }}>
          <p className="muted">{scope === "mine"
            ? (data.mine_count ? `None of your ${REGION_NAME[region]} stocks has an ex-date in this window.` : `You have no ${REGION_NAME[region]} stocks yet: they come from your watchlist, holdings, notebooks and paper sessions.`)
            : q ? "No company by that name has an action in this window." : "Nothing announced for this window yet."}</p>
          {scope === "mine" && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setParam("scope", "all")}>See all companies</button>}
        </div>
      )}
      {data && !empty && (
        <>
          {(data.ahead_known || data.ahead.length > 0) && <Days title="Coming up" rows={data.ahead} today={data.today} empty="Nothing announced with an ex-date ahead." />}
          {/* ex-dates gone by fold under one line, open only when there is nothing ahead to show */}
          {data.recent.length > 0 && (
            <section className="card" aria-label="Last two weeks">
              <Earlier label="Last two weeks" count={data.recent.length} open={!data.ahead_known && !data.ahead.length}>
                <DayGroups rows={data.recent} today={data.today} />
              </Earlier>
            </section>
          )}
        </>
      )}
      {data && data.more > 0 && <p className="tiny muted">And {data.more} more. Find a company by name to narrow the list.</p>}
      {data && <p className="small muted" style={{ maxWidth: "80ch" }}>The ex-date is the first day the shares trade without the entitlement; in India it's also the record date. {data.note}{data.updated_at ? ` Updated ${ago(data.updated_at)}.` : ""}</p>}
    </div>
  );
}
