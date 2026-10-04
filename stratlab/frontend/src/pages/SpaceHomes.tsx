import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { money, pct, signClass } from "../lib/format";
import { homeOf } from "../lib/spaces";
import { NAV_GROUPS } from "../lib/navGroups";
import { useWatchlist, REGION_NAME, type Region } from "../lib/research";
import type { LiveRow } from "../lib/types";
import { AsOf, Fig, Loading } from "../components/ui";
import { Panel, QuoteGrid } from "../components/Research";
import { SummaryLine, type FilingSummary } from "../components/Filings";
import { FirstSteps } from "../components/FirstSteps";
import { BreadthCard } from "../components/BreadthCard";
import { PromoCountdown } from "../components/PromoCountdown";
import { PositioningCard } from "../components/PositioningCard";
import { Book, Layers, Library, Pulse, Upload } from "../components/Icons";
import { AskBar, InvestorStart, NotebooksHome } from "./Home";
import { resultDay, type ResultRow } from "./Research";

/* The three spaces' home pages: /trade, /invest and /money. `/` opens the one whose menu shows. Each reuses the
 * pages' own pieces; nothing here is new data, only what those pages already show, gathered. */

/** `/`: the home of the space showing (for "All", of what the person came for). Waits for the account on a first visit. */
export function SpaceHome() {
  const { me, meError, space, focus } = useApp();
  if (!me && !meError) return <Loading label="Opening StratLab" />;
  return <Navigate to={homeOf(space, focus)} replace />;
}

/** The new-account checklist and the launch offer sit on top of every space's home. */
function Top() {
  return <><PromoCountdown /><FirstSteps /></>;
}

/* ---------- Trade: the strategy lab ---------- */
/** Tools the strip and the positioning panel already link to: the notebooks' "what you can do" leaves them out. */
const TRADE_LINKED = ["options", "positioning", "paper", "library", "import"];

export function TradeHome() {
  return (
    <div className="space-home">
      <Top />
      <TradeStrip />
      <PositioningCard />
      <NotebooksHome hide={TRADE_LINKED} />
    </div>
  );
}

/** Options first and big, then four tools in a 2 by 2 block beside it: paper sessions running now, the journal, the
 * library and import. Positioning has its own panel under the strip. Blurbs stay one or two short lines. */
function TradeStrip() {
  const [rows, setRows] = useState<LiveRow[] | null>(null);
  useEffect(() => { api<LiveRow[]>("/live/sessions").then(setRows).catch(() => setRows([])); }, []);
  const [journal, setJournal] = useState<{ count: number; net: number; win_rate: number | null } | null>(null);
  useEffect(() => { api<{ count: number; net: number; win_rate: number | null }>("/trade/journal/brief").then(setJournal).catch(() => setJournal(null)); }, []);
  const running = rows?.filter((r) => r.status === "running") ?? [];
  const options = running.filter((r) => r.instrument?.type === "OPTIONS");
  return (
    <section className="space-strip" aria-label="Trade">
      <Link to="/options" className="card space-card space-card-lead">
        <span className="row" style={{ gap: 8 }}><Layers size={20} /><b>Options</b></span>
        <span className="small muted">Straddles, condors or any structure up to eight legs, paper traded at the live bid and ask, at a set time or on your own signal.</span>
        <span className="small space-card-foot">{options.length > 0 ? `${options.length} option session${options.length === 1 ? "" : "s"} running · ` : ""}Build a structure →</span>
      </Link>
      <Link to="/paper" className="card space-card">
        <span className="row" style={{ gap: 8 }}><Pulse size={18} /><b>Paper trading</b></span>
        <span className="small muted" data-testid="paper-summary">
          {rows === null ? "Checking your sessions…" : running.length
            ? `${running.length} running: ${running.slice(0, 3).map((r) => r.name).join(", ")}${running.length > 3 ? "…" : ""}`
            : rows.length ? `None running · ${rows.length} stopped` : "Run a notebook's rules live with fake money."}
        </span>
      </Link>
      <Link to="/trade/journal" className="card space-card" data-trade="/trade/journal">
        <span className="row" style={{ gap: 8 }}><Book size={18} /><b>Trade journal</b></span>
        <span className="small muted">{journal?.count
          ? `${journal.count} closed trade${journal.count === 1 ? "" : "s"} · ${money(journal.net, "INR")} after charges · ${journal.win_rate}% won`
          : "Your real trades as round trips, after charges."}</span>
      </Link>
      <Link to="/library" className="card space-card">
        <span className="row" style={{ gap: 8 }}><Library size={18} /><b>Strategy library</b></span>
        <span className="small muted">Rules others published, with the verdict they earned.</span>
      </Link>
      <Link to="/import" className="card space-card">
        <span className="row" style={{ gap: 8 }}><Upload size={18} /><b>Import a strategy</b></span>
        <span className="small muted">Pine Script, Python, MetaTrader, AmiBroker or plain words.</span>
      </Link>
    </section>
  );
}

/* ---------- Invest: research ---------- */
/** Tools the panels and the questions on the Invest home already link to. */
const INVEST_LINKED = ["breadth", "filings", "investor", "watchlist", "rotation", "scan"];

export function InvestHome() {
  return (
    <div className="space-home">
      <Top />
      <InvestorStart hide={INVEST_LINKED}>
        <div className="grid2 space-panels">
          <WatchPanel />
          <ResultsToday />
        </div>
        <div className="grid2 space-panels">
          <BreadthCard />
          <RedFlags />
        </div>
      </InvestorStart>
    </div>
  );
}

/** The watchlist's prices, India then the US. */
function WatchPanel() {
  const { items } = useWatchlist();
  const by = (r: Region) => (items ?? []).filter((w) => w.region === r);
  const regions = (["IN", "US"] as Region[]).filter((r) => by(r).length);
  return (
    <Panel title="Your watchlist" right={<Link to="/research/investor" className="link">At a glance →</Link>}>
      {items === null ? <Loading label="Opening your watchlist" />
        : !regions.length ? <p className="small muted">Press Watch on any company to keep it here, with live prices.</p>
        : regions.map((r) => (
          <div key={r} className="stack" style={{ gap: 6 }}>
            {regions.length > 1 && <span className="eyebrow">{REGION_NAME[r]}</span>}
            <QuoteGrid region={r} symbols={by(r).slice(0, 6).map((w) => w.symbol)} names={Object.fromEntries(by(r).map((w) => [w.symbol, w.name]))} />
          </div>
        ))}
    </Panel>
  );
}

type ResultsView = { today: string; weeks: { rows: ResultRow[] }[] };

/** Results days for your stocks: today's, else the next one. */
function ResultsToday() {
  const [rows, setRows] = useState<{ today: ResultRow[]; next: ResultRow | null } | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all((["IN", "US"] as Region[]).map((r) => api<ResultsView>(`/research/results?region=${r}&scope=mine`).catch(() => null)))
      .then((views) => {
        if (!live) return;
        const all = views.flatMap((v) => (v ? v.weeks.flatMap((w) => w.rows).map((r) => ({ ...r, today: v.today })) : []));
        const today = all.filter((r) => r.date === r.today);
        const next = all.filter((r) => r.date > r.today).sort((a, b) => a.date.localeCompare(b.date))[0] ?? null;
        setRows({ today, next });
      });
    return () => { live = false; };
  }, []);
  return (
    <Panel title="Results today" right={<Link to="/research/results" className="link">Calendar →</Link>}>
      {rows === null ? <Loading label="Checking results dates" />
        : rows.today.length ? (
          <div className="stack" style={{ gap: 6 }}>
            {rows.today.slice(0, 6).map((r) => (
              <Link key={`${r.region}-${r.symbol}`} className="space-line" to={`/research/${r.region}/${encodeURIComponent(r.symbol)}`}>
                <b>{r.symbol}</b><span className="small muted">{r.out ? "Results filed" : r.purpose}{r.when ? `, ${r.when}` : ""}</span>
              </Link>
            ))}
          </div>
        ) : (
          <p className="small muted">None of your stocks has results today.{rows.next ? ` Next: ${rows.next.symbol} on ${resultDay(rows.next.date)}.` : ""}</p>
        )}
    </Panel>
  );
}

type Filings = { rows: { symbol: string; summary: FilingSummary }[] };

/** Watchlist companies with red flags filed lately (India; Basic and up, as on the red flags page). */
function RedFlags() {
  const { me } = useApp();
  const allowed = !!me?.plan_info?.features?.filings;
  const [data, setData] = useState<Filings | null>(null);
  useEffect(() => { if (allowed) api<Filings>("/research/filings").then(setData).catch(() => setData({ rows: [] })); }, [allowed]);
  const flagged = data?.rows.filter((r) => r.summary.red > 0) ?? [];
  return (
    <Panel title="Red flags in your watchlist" right={<Link to="/research/filings" className="link">All filings →</Link>}>
      {!allowed ? <p className="small muted">Red flags for your whole watchlist are on the Basic plan. Each company's own page shows its red flags on every plan.</p>
        : data === null ? <Loading label="Reading your companies' filings" />
        : !data.rows.length ? <p className="small muted">Your watchlist has no India stocks yet: their filings show here.</p>
        : !flagged.length ? <p className="small muted">No red flags filed by your {data.rows.length} India watchlist compan{data.rows.length === 1 ? "y" : "ies"} lately.</p>
        : (
          <div className="stack" style={{ gap: 8 }}>
            {flagged.slice(0, 5).map((r) => (
              <div key={r.symbol} className="space-line">
                <Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}#filings`}><b>{r.symbol}</b></Link>
                <SummaryLine s={r.summary} />
              </div>
            ))}
          </div>
        )}
    </Panel>
  );
}

/* ---------- Money: what you own ---------- */
type Totals = { value: number; invested: number; pnl: number | null; pnl_pct: number | null; day: number | null; day_pct: number | null; count: number };
type Holdings = { rows: unknown[]; totals: Totals; us?: (Totals & { in_total: boolean }) | null; updated_at: string | null; prices_at?: string | null };
type TaxYear = { fy: number; label: string; count: number; tax_with_cess: number; stcg: { net: number }; ltcg: { net: number }; exemption: { left: number } };
type Tax = { years: TaxYear[]; current_fy: number; updated_at: string | null; prices_at: string | null; trades: number };

export function MoneyHome() {
  return (
    <div className="space-home">
      <Top />
      <div className="stack" style={{ gap: 28 }}>
        <div className="stack" style={{ gap: 8 }}>
          <span className="eyebrow">Money</span>
          <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em" }}>Your money</h1>
          <p className="muted" style={{ fontSize: 17 }}>What you own and what it means at tax time, from your own files. Facts and arithmetic: seen only by you.</p>
        </div>
        <div className="grid2 space-panels">
          <HoldingsSummary />
          <TaxSummary />
        </div>
        <section className="stack" style={{ gap: 10 }} aria-labelledby="money-tools">
          <h2 id="money-tools" className="h2">Everything in Money</h2>
          <div className="explore-grid">
            {NAV_GROUPS.Money.map((e) => (
              <Link key={e.to} to={e.to} className="card explore-card" data-money={e.to}><b>{e.label}</b><span className="small muted">{e.blurb ?? e.title}</span></Link>
            ))}
          </div>
        </section>
        <AskBar />
      </div>
    </div>
  );
}

function HoldingsSummary() {
  const [h, setH] = useState<Holdings | null | "error">(null);
  useEffect(() => { api<Holdings>("/holdings").then(setH).catch(() => setH("error")); }, []);
  return (
    <Panel title="My Holdings" right={<Link to="/holdings" className="link">Open →</Link>}>
      {h === null ? <Loading label="Adding up your holdings" />
        : h === "error" ? <p className="small muted">Your holdings couldn't be opened just now. <Link className="link" to="/holdings">Try the page</Link>.</p>
        : !h.rows.length ? (
          <div className="stack" style={{ gap: 10, alignItems: "flex-start" }}>
            <p className="small muted">No holdings yet. Bring the holdings file your broker gives you, or add stocks by hand.</p>
            <Link to="/holdings" className="btn sm">Add your holdings</Link>
          </div>
        ) : (
          <div className="stack" style={{ gap: 10 }} data-testid="holdings-summary">
            <div className="space-figs">
              <Fig label={`Value · ${h.totals.count} stock${h.totals.count === 1 ? "" : "s"}`} value={money(h.totals.value, "INR")} />
              <Fig label="Gain or loss" tone={signClass(h.totals.pnl)} value={h.totals.pnl != null && money(h.totals.pnl, "INR")}
                note={h.totals.pnl_pct != null && pct(h.totals.pnl_pct)} noteTone={signClass(h.totals.pnl)} missing="Needs the buy prices" />
              {h.totals.day != null && <Fig label="Today" tone={signClass(h.totals.day)} value={money(h.totals.day, "INR")} />}
              {h.us && h.us.count > 0 && <Fig label={`US stocks${h.us.in_total ? " (in the rupee value)" : ""}`} value={money(h.us.value, "USD")} />}
            </div>
            <AsOf parts={[["Prices", h.prices_at], ["Holdings", h.updated_at]]} />
          </div>
        )}
    </Panel>
  );
}

function TaxSummary() {
  const [t, setT] = useState<Tax | null | "error">(null);
  useEffect(() => { api<Tax>("/tax").then(setT).catch(() => setT("error")); }, []);
  const year = t && t !== "error" ? t.years.find((y) => y.fy === t.current_fy) ?? null : null;
  return (
    <Panel title="Tax this year" right={<Link to="/tax-report" className="link">Tax report →</Link>}>
      {t === null ? <Loading label="Working out this year's gains" />
        : t === "error" ? <p className="small muted">The tax report couldn't be opened just now. <Link className="link" to="/tax-report">Try the page</Link>.</p>
        : !t.trades ? (
          <div className="stack" style={{ gap: 10, alignItems: "flex-start" }}>
            <p className="small muted">Upload your broker's tradebooks to see this financial year's capital gains and the tax on them.</p>
            <Link to="/tax-report" className="btn sm">Add your tradebooks</Link>
          </div>
        ) : (
          <div className="stack" style={{ gap: 10 }} data-testid="tax-summary">
            <div className="space-figs">
              <Fig label={`Capital gains tax, ${year?.label ?? "this year"} (estimate)`} value={money(year?.tax_with_cess ?? 0, "INR")} />
              <Fig label="Short-term gains" tone={signClass(year?.stcg.net)} value={money(year?.stcg.net ?? 0, "INR")} />
              <Fig label="Long-term gains" tone={signClass(year?.ltcg.net)} value={money(year?.ltcg.net ?? 0, "INR")} />
            </div>
            <p className="tiny muted">Assumes only the sales in the tradebooks you uploaded, matched first in, first out, at this year's rates after set-off and the yearly long-term exemption, with 4% cess and before any surcharge. {year?.count ? `${year.count} sale${year.count === 1 ? "" : "s"} so far this year.` : "No sales this year yet."} An estimate to check with your CA.</p>
            <AsOf parts={[["Trades", t.updated_at], ["Prices", t.prices_at]]} />
          </div>
        )}
    </Panel>
  );
}
