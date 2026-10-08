import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, money, pct, signCls } from "../lib/format";
import { homeOf } from "../lib/spaces";
import { NAV_GROUPS } from "../lib/navGroups";
import { evWhen, useEvents } from "../lib/marketEvents";
import { useWatchlist, REGION_NAME, type Region } from "../lib/research";
import type { LiveRow } from "../lib/types";
import { AsOf, Fig, Loading, PanelSkel, VerdictBadge } from "../components/ui";
import { Card, CardHead, PageHeader, Seg } from "../components/kit";
import { Panel, QuoteGrid } from "../components/Research";
import { SummaryLine, type FilingSummary } from "../components/Filings";
import { FirstSteps } from "../components/FirstSteps";
import { BreadthCard } from "../components/BreadthCard";
import { PromoCountdown } from "../components/PromoCountdown";
import { Explore } from "../components/Explore";
import { CompanySearch } from "../components/CompanySearch";
import { Book, Calendar, Compass, Layers, Library, Pulse, Search } from "../components/Icons";
import { resultDay, type ResultRow } from "./Research";
import { fyLink, movedYearNote, openFy, yearHasTrades } from "../lib/fy";

/* The three spaces' home pages: /trade, /invest and /money. `/` opens the one whose menu shows. Each reuses the
 * pages' own pieces; nothing here is new data, only what those pages already show, gathered.
 *
 * Every home has the same shape: a short heading, the one next step (start, or pick up where you left off), one row of
 * four equal tool cards, then one or two live panels and, last, the rest of the space's tools. */

/** `/`: the home of the space showing (for "All", of what the person came for). Waits for the account on a first visit. */
export function SpaceHome() {
  const { me, meError, space, focus } = useApp();
  if (!me && !meError) return <Loading label="Opening StratLab" />;
  return <Navigate to={homeOf(space, focus)} replace />;
}

/** The launch offer and the new-account checklist, right under every space home's heading. */
function Top({ onSteps }: { onSteps?: (shown: boolean) => void }) {
  return <><PromoCountdown /><FirstSteps onShown={onSteps} /></>;
}

/** A space home's heading: the space's name, one question or title, one line under it. */
function Head({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return <PageHeader eyebrow={eyebrow} title={title} lede={children} />;
}

/** One tool on a space's strip. `status`: a live line (e.g. "2 running"); null while it loads (a placeholder of the
 * same height); left out, the card's foot says where it goes instead. */
type Tool = { to: string; icon: ReactNode; title: string; line: string; status?: string | null; go?: string; lead?: boolean; testId?: string; data?: Record<string, string> };

/** Four tools in one row of equal cards (two by two when the column is narrow). The lead tool is marked by its
 * border and tint, not its size. Every card has the same three lines, so the row never jumps when a status loads. */
function ToolStrip({ label, tools }: { label: string; tools: Tool[] }) {
  return (
    <nav className="space-strip" aria-label={label}>
      {tools.map((t) => (
        <Link key={t.to} to={t.to} className={`k-linkcard space-card${t.lead ? " space-card-lead" : ""}`} {...t.data}>
          <span className="space-card-title">{t.icon}<b>{t.title}</b></span>
          <span className="small muted space-card-line">{t.line}</span>
          {t.status === null ? <span className="space-card-foot" aria-hidden="true"><span className="skel" /></span>
            : <span className={`small space-card-foot${t.status ? " live" : ""}`} data-testid={t.testId}>{t.status || t.go || "Open →"}</span>}
        </Link>
      ))}
    </nav>
  );
}

/* ---------- Trade: the strategy lab ---------- */
/** Tools the strip and the positioning panel already link to: "more you can do" leaves them out. */
const TRADE_LINKED = ["options", "positioning", "paper", "library", "idea"];
type Journal = { count: number; net: number; win_rate: number | null };

/** Trade's first three tools: the home's cards and the All home's row. */
const TRADE_TOP: Tool[] = [
  { to: "/options", icon: <Layers size={18} />, title: "Options", lead: true, line: "Straddles, strangles, condors or any legs, at the live bid and ask." },
  { to: "/paper", icon: <Pulse size={18} />, title: "Paper trading", line: "Run a notebook's rules live with fake money." },
  { to: "/trade/journal", icon: <Book size={18} />, title: "Trade journal", line: "Your real trades as round trips, after charges.", data: { "data-trade": "/trade/journal" } },
];

export function TradeHome() {
  const [steps, setSteps] = useState(false);
  const [rows, setRows] = useState<LiveRow[] | null>(null);
  useEffect(() => { api<LiveRow[]>("/live/sessions").then(setRows).catch(() => setRows([])); }, []);
  const [journal, setJournal] = useState<Journal | null | "none">(null);
  useEffect(() => { api<Journal>("/trade/journal/brief").then(setJournal).catch(() => setJournal("none")); }, []);
  const running = rows?.filter((r) => r.status === "running") ?? [];
  const options = running.filter((r) => r.instrument?.type === "OPTIONS");
  const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
  const tools: Tool[] = [
    { ...TRADE_TOP[0], status: rows === null ? null : options.length ? `${options.length} running` : "", go: "Build a structure →" },
    { ...TRADE_TOP[1], testId: "paper-summary",
      status: rows === null ? null : running.length ? `${running.length} running` : rows.length ? `None running · ${rows.length} stopped` : "" },
    { ...TRADE_TOP[2],
      status: journal === null ? null : journal !== "none" && journal.count ? `${plural(journal.count, "closed trade")} · ${money(journal.net, "INR")}` : "" },
    { to: "/library", icon: <Library size={18} />, title: "Strategy library", line: "Published rules, each with the result of its checks." },
  ];
  return (
    <div className="space-home">
      <Head eyebrow="Trade · your strategy lab" title="Test an idea, then trade it on paper">
        Years of real prices, real costs and four checks for luck. Fake money, never real orders.
      </Head>
      <Top onSteps={setSteps} />
      {/* the checklist's first step is a first test: one guide at a time, so "Start here" waits until it's gone */}
      <NextIdea hideStart={steps} />
      <ToolStrip label="Trade tools" tools={tools} />
      <p className="k-small k-muted" data-testid="positioning-link">FII and DII flows, futures positions, PCR and India VIX are on <Link className="link" to="/trade/positioning">Positioning</Link>.</p>
      <Explore title="More you can do" hide={TRADE_LINKED} order="trade" />
    </div>
  );
}

/** Trade's next step: for a new account, how a test goes and the button to start one; after that, the latest
 * notebooks to pick up again. */
function NextIdea({ count = 3, hideStart = false }: { count?: number; hideStart?: boolean }) {
  const { notebooks } = useApp();
  if (notebooks === null) return <Card className="space-next"><PanelSkel lines={3} label="Opening your notebooks" /></Card>;
  if (!notebooks.length && hideStart) return null;
  if (!notebooks.length) return (
    <Card className="space-next" label="Start here">
      <CardHead title="Start here: your first notebook" actions={<Link to="/new" className="btn">Test your first idea</Link>} />
      <ol className="how" aria-label="How a test goes">
        <li><b>1. Describe it</b><span>In plain words. It becomes rules you can read and edit.</span></li>
        <li><b>2. Test it honestly</b><span>On years of real prices, after costs, with four checks for luck.</span></li>
        <li><b>3. Trade it on paper</b><span>If the edge holds up, run it live with fake money.</span></li>
      </ol>
    </Card>
  );
  const recent = [...notebooks].sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned)).slice(0, count);
  return (
    <Card className="space-next" label="Pick up where you left off">
      <CardHead title="Pick up where you left off" actions={<>
        <Link to="/notebooks" className="btn quiet sm">All {notebooks.length} notebook{notebooks.length === 1 ? "" : "s"}</Link>
        <Link to="/new" className="btn sm">Test a new idea</Link>
      </>} />
      <div className="space-recent">
        {recent.map((n) => (
          <Link key={n.id} to={`/n/${n.id}`} className="space-recent-row">
            <span className="k-stack tight space-recent-text">
              <b className="space-recent-name">{n.name}</b>
              <span className="tiny muted">{n.instrument && "symbol" in n.instrument ? `${n.instrument.symbol} · ` : ""}{n.summary?.experiments ?? 0} run{n.summary?.experiments === 1 ? "" : "s"} · {ago(n.updated_at)}</span>
            </span>
            <VerdictBadge v={n.summary?.last_verdict} />
          </Link>
        ))}
      </div>
    </Card>
  );
}

/* ---------- Invest: research ---------- */
/** Tools the strip and the panels on the Invest home already link to. */
const INVEST_LINKED = ["breadth", "filings", "investor", "watchlist", "rotation", "scan", "research", "holdings"];

const INVEST_STRIP: Tool[] = [
    { to: "/research/screens", icon: <Search size={18} />, title: "Screener", lead: true, line: "Filter companies by plain facts: growth, debt, returns." },
    { to: "/research/rotation", icon: <Compass size={18} />, title: "Sector rotation", line: "Which sectors lead or lag the market, with their stocks." },
    { to: "/research/scan?set=nifty50", icon: <Pulse size={18} />, title: "Trend scan", line: "Stocks in a rising trend with the Supertrend up." },
    { to: "/research/corporate-actions", icon: <Calendar size={18} />, title: "Dividends", line: "Dividends, bonuses and splits ahead, for your stocks and all." },
];

export function InvestHome() {
  const nav = useNavigate();
  const [region, setRegion] = useState<Region>("IN");
  const popular = region === "IN" ? ["RELIANCE", "HDFCBANK", "TCS", "TITAN", "LT"] : ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"];
  const tools = INVEST_STRIP;
  return (
    <div className="space-home">
      <Head eyebrow="Invest · your research desk" title="Your research desk">
        What your watchlist, results days and red flags say today, and the market around them. Facts, not tips.
      </Head>
      <Top />
      <Card className="space-next" label="Jump to a company">
        <Seg label="Market" value={region} onChange={(v) => setRegion(v as Region)} options={[{ value: "IN", label: "₹ India" }, { value: "US", label: "$ United States" }]} />
        <CompanySearch region={region} autoFocus />
        <div className="k-row">
          <span className="k-small k-muted">Popular:</span>
          {popular.map((p) => <button key={p} className="chip" onClick={() => nav(`/research/${region}/${p}`)}>{p}</button>)}
        </div>
      </Card>
      <ToolStrip label="Invest tools" tools={tools} />
      <NextEvents />
      <div className="grid2 space-panels">
        <WatchPanel />
        <ResultsToday />
      </div>
      <div className="grid2 space-panels">
        <BreadthCard />
        <RedFlags />
      </div>
      <Explore title="More you can do" hide={INVEST_LINKED} order="invest" />
    </div>
  );
}

/** The next few market events (RBI policy, data releases, the Fed, index changes) on one line each, from the Events page. */
function NextEvents({ limit = 3, testId = "invest-events" }: { limit?: number; testId?: string }) {
  const v = useEvents();
  const next = v ? v.events.filter((e) => e.date >= v.today && e.kind !== "expiry" && e.kind !== "holiday").slice(0, limit) : null;
  if (next && !next.length) return null;
  return (
    <Card testId={testId} label="Coming up">
      <CardHead title="Coming up" actions={<Link to="/trade/events" className="link small">Market events →</Link>} />
      {next === null ? <PanelSkel label="Reading the market events" lines={1} /> : (
        <div className="space-events">
          {next.map((e) => <span key={e.id} className="small"><span className="muted">{evWhen(e)}</span> {e.title}</span>)}
        </div>
      )}
    </Card>
  );
}

/** The watchlist's prices, India then the US. */
function WatchPanel() {
  const { items } = useWatchlist();
  const by = (r: Region) => (items ?? []).filter((w) => w.region === r);
  const regions = (["IN", "US"] as Region[]).filter((r) => by(r).length);
  return (
    <Panel title="Your watchlist" right={<Link to="/research/investor" className="link">At a glance →</Link>}>
      {items === null ? <PanelSkel label="Opening your watchlist" />
        : !regions.length ? <p className="small muted">Press Watch on any company to keep it here, with live prices.</p>
        : regions.map((r) => (
          <div key={r} className="k-stack snug">
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
      {rows === null ? <PanelSkel label="Checking results dates" />
        : rows.today.length ? (
          <div className="k-stack snug">
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

/** Held and watched companies with red flags filed lately (India; Basic and up, as on the red flags page). */
function RedFlags() {
  const { me } = useApp();
  const allowed = !!me?.plan_info?.features?.filings;
  const [data, setData] = useState<Filings | null>(null);
  useEffect(() => { if (allowed) api<Filings>("/research/filings").then(setData).catch(() => setData({ rows: [] })); }, [allowed]);
  const flagged = data?.rows.filter((r) => r.summary.red > 0) ?? [];
  return (
    <Panel title="Red flags in your holdings and watchlist" right={<Link to="/research/filings" className="link">All filings →</Link>}>
      {!allowed ? <p className="small muted">Red flags for all your holdings and watchlist are on the Basic plan. Each company's own page shows its red flags on every plan.</p>
        : data === null ? <PanelSkel label="Reading your companies' filings" />
        : !data.rows.length ? <p className="small muted">You hold or watch no India stocks yet: their filings show here.</p>
        : !flagged.length ? <p className="small muted">No red flags filed lately by the {data.rows.length} India compan{data.rows.length === 1 ? "y" : "ies"} you hold or watch.</p>
        : (
          <div className="k-stack snug">
            {flagged.slice(0, 5).map((r) => (
              <div key={r.symbol} className="space-line">
                <Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}#filings`}><b>{r.symbol}</b></Link>
                <SummaryLine s={r.summary} to={`/research/IN/${encodeURIComponent(r.symbol)}#filings`} />
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
type TaxYear = { fy: number; label: string; count: number; intraday: { count: number }; business: { segments: unknown[] }; units?: unknown; tax_with_cess: number; stcg: { net: number }; ltcg: { net: number }; exemption: { left: number };
  total?: { available: boolean; total?: number }; audit?: string | null };
type Tax = { years: TaxYear[]; current_fy: number; updated_at: string | null; prices_at: string | null; trades: number };


export function MoneyHome() {
  // the two summaries (holdings and tax) stand for their tools; every other Money tool is one card below, so each feature shows once
  const PANELS = ["/holdings", "/tax-report"];
  const rest = NAV_GROUPS.Money.filter((e) => !PANELS.includes(e.to));
  return (
    <div className="space-home">
      <Head eyebrow="Money · seen only by you" title="Your money">
        What you own and what it means at tax time, from your own files. Facts and arithmetic.
      </Head>
      <Top />
      <div className="grid2 space-panels">
        <HoldingsSummary />
        <TaxSummary />
      </div>
      {rest.length > 0 && (
        <section className="k-stack" aria-labelledby="money-tools">
          <h2 id="money-tools" className="k-card-title">More in Money</h2>
          <div className="explore-grid">
            {rest.map((e) => (
              <Link key={e.to} to={e.to} className="k-linkcard explore-card" data-money={e.to}><b>{e.label}</b><span className="small muted">{e.blurb ?? e.title}</span></Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function HoldingsSummary() {
  const [h, setH] = useState<Holdings | null | "error">(null);
  useEffect(() => { api<Holdings>("/holdings").then(setH).catch(() => setH("error")); }, []);
  return (
    <Panel title="My Holdings" right={<Link to="/holdings" className="link" data-money="/holdings">Open My Holdings →</Link>}>
      {h === null ? <PanelSkel figs label="Adding up your holdings" />
        : h === "error" ? <p className="small muted">Your holdings couldn't be opened just now. <Link className="link" to="/holdings">Try the page</Link>.</p>
        : !h.rows.length ? (
          <div className="k-stack start">
            <p className="small muted">No holdings yet. Bring the holdings file your broker gives you, or add stocks by hand.</p>
            <Link to="/holdings" className="btn sm">Add your holdings</Link>
          </div>
        ) : (
          <div className="k-stack" data-testid="holdings-summary">
            <div className="k-stats">
              <Fig label={`Value · ${h.totals.count} stock${h.totals.count === 1 ? "" : "s"}`} value={money(h.totals.value, "INR")} />
              <Fig label="Gain or loss" tone={signCls(h.totals.pnl)} value={h.totals.pnl != null && money(h.totals.pnl, "INR")}
                note={h.totals.pnl_pct != null && pct(h.totals.pnl_pct)} noteTone={signCls(h.totals.pnl)} missing="Needs the buy prices" />
              {h.totals.day != null && <Fig label="Today" tone={signCls(h.totals.day)} value={money(h.totals.day, "INR")} />}
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
  // the Money pages' one rule for the year (lib/fy openFy): the year last picked, else the one being filed now, or the latest
  // year with sales when that has none (said in one line); the link to the tax report carries the year shown
  const ok = t && t !== "error" ? t : null;
  const open = ok ? openFy(ok.years.map((x) => x.fy), ok.current_fy, (fy) => ok.years.some((x) => x.fy === fy && yearHasTrades(x))) : null;
  const year = ok && open ? ok.years.find((y) => y.fy === open.fy) ?? null : null;
  return (
    <Panel title={year ? `Tax, ${year.label}` : "Tax this year"} right={<Link to={year ? fyLink("/tax-report", year.fy) : "/tax-report"} className="link" data-money="/tax-report">Open Tax report →</Link>}>
      {t === null ? <PanelSkel figs label="Working out this year's gains" />
        : t === "error" ? <p className="small muted">The tax report couldn't be opened just now. <Link className="link" to="/tax-report">Try the page</Link>.</p>
        : !t.trades ? (
          <div className="k-stack start">
            <p className="small muted">Upload your broker's tradebooks to see this financial year's capital gains and the tax on them.</p>
            <Link to="/tax-report" className="btn sm">Add your tradebooks</Link>
          </div>
        ) : (
          <div className="k-stack" data-testid="tax-summary">
            <div className="k-stats">
              {/* the tax report's own total (capital gains, F&O and intraday business income, slab, surcharge and cess), so the
                  two pages agree; the capital gains part alone said ₹0 beside a report of ₹77,61,298 */}
              <Fig label={`Total tax estimate, ${year?.label ?? "this year"}`} value={money(year?.total?.available ? year.total.total ?? 0 : year?.tax_with_cess ?? 0, "INR")} />
              <Fig label="Short-term gains" tone={signCls(year?.stcg.net)} value={money(year?.stcg.net ?? 0, "INR")} />
              <Fig label="Long-term gains" tone={signCls(year?.ltcg.net)} value={money(year?.ltcg.net ?? 0, "INR")} />
            </div>
            {year?.audit && <p className="small">{year.audit}</p>}
            <p className="tiny muted">{year?.total?.available ? "As the tax report works it out: the trades and other income in your files, at that year's slab and special rates, with surcharge and 4% cess." : "Assumes only the sales in the tradebooks you uploaded, matched first in, first out, at that year's rates after set-off and the yearly long-term exemption, with 4% cess and before any surcharge."} {year?.count ? `${year.count} sale${year.count === 1 ? "" : "s"} in ${year.label}.` : `No sales in ${year?.label ?? "this year"}.`}{year && open?.from != null ? ` ${movedYearNote(open.from, year.fy, ok!.current_fy, "sales")}` : ""} An estimate to check with your CA.</p>
            <AsOf parts={[["Trades", t.updated_at], ["Prices", t.prices_at]]} />
          </div>
        )}
    </Panel>
  );
}
