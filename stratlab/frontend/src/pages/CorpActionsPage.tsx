import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, marketTz } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { REGION_NAME, saveRegion, savedRegion, type Region } from "../lib/research";
import { RegionSwitch } from "../components/Research";
import { ActionLine, KIND_NAME, exDay, type ActionKind, type CorpAction } from "../components/CorpActions";
import { Info } from "../components/ui";
import { Earlier } from "../components/Earlier";
import { Card, CardHead, CheckField, EmptyState, ErrorState, Field, FormGrid, PageHeader, Seg, Select, Skeleton, StockPicker } from "../components/kit";

interface CalendarView {
  region: Region; scope: "mine" | "all"; kind: string; today: string; updated_at: string | null; ahead: CorpAction[]; recent: CorpAction[];
  more: number; mine_count: number; alerts: boolean; kinds: ActionKind[]; ahead_known: boolean; ahead_note?: string | null; note: string;
  recent_days?: number; universe?: { companies: number | null; updated_at: string | null } | null;
}

/** Ex-dates in day groups. */
function DayGroups({ rows, today, showMine }: { rows: CorpAction[]; today: string; showMine: boolean }) {
  const days = [...new Set(rows.map((r) => r.ex_date))];
  return <div className="inv-days">{days.map((d) => (
    <div key={d} className="inv-day">
      <span className="k-eyebrow">Ex-date {exDay(d)}{d === today ? " · today" : ""}</span>
      <div className="inv-rows">{rows.filter((r) => r.ex_date === d).map((r) => <ActionLine key={r.id} a={r} showEx={false} showMine={showMine} />)}</div>
    </div>
  ))}</div>;
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
  const [tries, setTries] = useState(0);
  // another market or another set of companies is a different list: the find-a-company text and the old list don't carry over
  const [shownFor, setShownFor] = useState(`${region}|${scope}`);
  if (shownFor !== `${region}|${scope}`) { setShownFor(`${region}|${scope}`); setQ(""); setData(null); }

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
  }, [region, scope, kind, q, tries]);

  const toggleAlerts = async () => {
    if (!data) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/corp-actions/alerts", { method: "PUT", body: { on: !data.alerts } });
      setData({ ...data, alerts: r.alerts });
      notify(r.alerts ? "You'll get a message when one of your stocks announces a corporate action, and the evening before its ex-date." : "Corporate action messages off.");
    } catch (e) { fail(e); }
  };
  const empty = data && !data.ahead.length && !data.recent.length;
  const lookBack = (data?.recent_days ?? 14) >= 28 ? "Last four weeks" : "Last two weeks";

  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/corporate-actions")} title="Dividends, bonuses and splits" asOf={data?.updated_at} asOfLabel="Updated" asOfTz={marketTz(region)}
        lede={region === "IN"
          ? "Dividends, bonus issues, splits, buybacks, rights issues and demergers by ex-date, as companies announced them to the exchange."
          : "Dividends and splits of the S&P 500 and the US companies you follow, by ex-date: dividends companies have declared for the next four weeks, and those that have gone ex."}
        info={region === "US" ? <>Dividends ahead are the ones companies have declared, from the US market calendar, for the next four weeks, with the record and pay dates the company gave.
          Past ex-dates, and splits, are read once a day from each company's price history: the S&P 500 and StratLab's own groups{data?.universe?.companies ? ` (${data.universe.companies.toLocaleString("en-IN")} companies read)` : ""}, plus any US stock you follow. A split ahead isn't listed until its ex-date. Amounts are per share.</> : undefined}
        infoLabel="About the US list" />
      <div className="k-toolbar">
        <RegionSwitch region={region} setRegion={setRegion} />
        <Seg label="Which companies" value={scope} onChange={(v) => setParam("scope", v)} options={[{ value: "mine", label: "My stocks" }, { value: "all", label: "All" }]} />
      </div>
      <Card>
        <FormGrid label="Filter the calendar">
          <Field label="Kind of action">
            {(id) => <Select id={id} value={kind} onChange={(v) => setParam("kind", v)}
              options={[{ value: "", label: "Every kind" }, ...(Object.keys(KIND_NAME) as ActionKind[]).map((k) => ({ value: k, label: KIND_NAME[k] }))]} />}
          </Field>
          {scope === "all" && (
            <Field key={region} label="Find a company">
              {(id) => <StockPicker id={id} market={region} onText={setQ} onPick={(s) => setQ(s)} placeholder={region === "IN" ? "Like TCS or Infosys" : "Like AAPL or Apple"} />}
            </Field>
          )}
        </FormGrid>
        {data && (
          <CheckField checked={data.alerts} onChange={toggleAlerts}
            label={<>Message me when my stocks announce a corporate action, and the evening before an ex-date
              <Info>Sent by phone notification or Telegram, whichever you set up in Settings. Your stocks are your watchlist, holdings, notebooks and paper sessions. The My Stocks newsletter lists the week's ex-dates too.</Info></>} />
        )}
      </Card>
      {error && <ErrorState title="The calendar couldn't be opened" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>}
      {!data && !error && <Card><Skeleton label="Opening the corporate actions calendar" lines={4} /></Card>}
      {data && empty && (
        <Card>
          <EmptyState title={scope === "mine" ? (data.mine_count ? "None of your stocks has an ex-date in this window" : "No stocks to show ex-dates for yet") : "Nothing announced for this window"}
            action={scope === "mine" ? { label: "See all companies", onClick: () => setParam("scope", "all") } : undefined}>
            {scope === "mine"
              ? (data.mine_count ? `None of your ${REGION_NAME[region]} stocks has an ex-date in this window.` : `You have no ${REGION_NAME[region]} stocks yet: they come from your watchlist, holdings, notebooks and paper sessions.`)
              : q ? "No company by that name has an action in this window." : (data.ahead_note ?? "Nothing announced for this window yet.")}
          </EmptyState>
        </Card>
      )}
      {data && !empty && (
        <>
          {/* always there, and when it has nothing it says why (RC1-006: the US list was empty with no word) */}
          <Card>
            <CardHead title="Coming up" />
            {data.ahead.length === 0 ? <span className="k-small k-muted" data-testid="ahead-note">{data.ahead_note ?? "Nothing announced with an ex-date ahead."}</span> : <DayGroups rows={data.ahead} today={data.today} showMine={scope === "all"} />}
          </Card>
          {/* ex-dates gone by fold under one line, open only when there is nothing ahead to show */}
          {data.recent.length > 0 && (
            <Card label={lookBack}>
              <Earlier label={lookBack} count={data.recent.length} open={!data.ahead_known && !data.ahead.length}>
                <DayGroups rows={data.recent} today={data.today} showMine={scope === "all"} />
              </Earlier>
            </Card>
          )}
        </>
      )}
      {data && data.more > 0 && <p className="k-note">And {data.more} more.{scope === "all" ? " Find a company by name to narrow the list." : ""}</p>}
      {data && <p className="k-note inv-text">The ex-date is the first day the shares trade without the entitlement; the record date (on each row when it's another day) is when the company reads its list of holders. {data.note}{data.updated_at ? ` Updated ${ago(data.updated_at)}.` : ""}</p>}
    </div>
  );
}
