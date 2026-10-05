import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, money, pct, signClass } from "../lib/format";
import { homeOf, SPACES } from "../lib/spaces";
import { PLAN_NAME, planOf } from "../lib/plans";
import { NAV_GROUPS } from "../lib/navGroups";
import { evDay, useEvents } from "../lib/marketEvents";
import { useWatchlist, REGION_NAME, type Region } from "../lib/research";
import type { LiveRow } from "../lib/types";
import { AsOf, Fig, Loading, PanelSkel, VerdictBadge } from "../components/ui";
import { Panel, QuoteGrid } from "../components/Research";
import { SummaryLine, type FilingSummary } from "../components/Filings";
import { FirstSteps } from "../components/FirstSteps";
import { BreadthCard } from "../components/BreadthCard";
import { PromoCountdown } from "../components/PromoCountdown";
import { PositioningCard } from "../components/PositioningCard";
import { Explore } from "../components/Explore";
import { CompanySearch } from "../components/CompanySearch";
import { Book, Calendar, Compass, Layers, Library, Pulse, Receipt, Search, Wallet } from "../components/Icons";
import { resultDay, type ResultRow } from "./Research";

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

/** The new-account checklist and the launch offer sit on top of every space's home. */
function Top() {
  return <><PromoCountdown /><FirstSteps /></>;
}

/** A space home's heading: the space's name, one question or title, one line under it. */
function Head({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return (
    <header className="space-head">
      <span className="eyebrow">{eyebrow}</span>
      <h1 className="serif">{title}</h1>
      <p className="muted">{children}</p>
    </header>
  );
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
        <Link key={t.to} to={t.to} className={`card space-card${t.lead ? " space-card-lead" : ""}`} {...t.data}>
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
    { to: "/library", icon: <Library size={18} />, title: "Strategy library", line: "Rules others published, with the verdict they earned." },
  ];
  return (
    <div className="space-home">
      <Top />
      <Head eyebrow="Trade · your strategy lab" title="Test an idea, then trade it on paper">
        Years of real prices, real costs and four checks for luck. Fake money, never real orders.
      </Head>
      <NextIdea />
      <ToolStrip label="Trade tools" tools={tools} />
      <PositioningCard />
      <Explore title="More you can do" hide={TRADE_LINKED} order="trade" />
    </div>
  );
}

/** Trade's next step: for a new account, how a test goes and the button to start one; after that, the latest
 * notebooks to pick up again. */
function NextIdea({ count = 3 }: { count?: number }) {
  const { notebooks } = useApp();
  if (notebooks === null) return <section className="card space-next" aria-busy="true"><PanelSkel lines={3} label="Opening your notebooks" /></section>;
  if (!notebooks.length) return (
    <section className="card space-next" aria-labelledby="next-h">
      <div className="spread" style={{ flexWrap: "wrap", gap: 12 }}>
        <h2 id="next-h" className="h3">Start here: your first notebook</h2>
        <Link to="/new" className="btn">Test your first idea</Link>
      </div>
      <ol className="how" aria-label="How a test goes">
        <li><b>1. Describe it</b><span>In plain words. It becomes rules you can read and edit.</span></li>
        <li><b>2. Test it honestly</b><span>On years of real prices, after costs, with four checks for luck.</span></li>
        <li><b>3. Trade it on paper</b><span>If the edge holds up, run it live with fake money.</span></li>
      </ol>
    </section>
  );
  const recent = [...notebooks].sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned)).slice(0, count);
  return (
    <section className="card space-next" aria-labelledby="next-h">
      <div className="spread" style={{ flexWrap: "wrap", gap: 12 }}>
        <h2 id="next-h" className="h3">Pick up where you left off</h2>
        <div className="row wrap" style={{ gap: 8 }}>
          <Link to="/notebooks" className="btn quiet sm">All {notebooks.length} notebook{notebooks.length === 1 ? "" : "s"}</Link>
          <Link to="/new" className="btn sm">Test a new idea</Link>
        </div>
      </div>
      <div className="space-recent">
        {recent.map((n) => (
          <Link key={n.id} to={`/n/${n.id}`} className="space-recent-row">
            <span className="stack" style={{ gap: 2, minWidth: 0 }}>
              <b className="space-recent-name">{n.name}</b>
              <span className="tiny muted">{n.instrument && "symbol" in n.instrument ? `${n.instrument.symbol} · ` : ""}{n.summary?.experiments ?? 0} run{n.summary?.experiments === 1 ? "" : "s"} · {ago(n.updated_at)}</span>
            </span>
            <VerdictBadge v={n.summary?.last_verdict} />
          </Link>
        ))}
      </div>
    </section>
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
      <Top />
      <Head eyebrow="Invest · your research desk" title="Which company do you want to look into?">
        The numbers, the business in its own words, red flags and whether management delivers. Facts, not tips.
      </Head>
      <section className="card stack space-next" aria-label="Find a company">
        <div className="seg" role="radiogroup" aria-label="Market" style={{ alignSelf: "flex-start" }}>
          {(["IN", "US"] as const).map((r) => <button key={r} role="radio" aria-checked={region === r} aria-pressed={region === r} onClick={() => setRegion(r)}>{r === "IN" ? "₹ India" : "$ United States"}</button>)}
        </div>
        <CompanySearch region={region} autoFocus />
        <div className="row wrap" style={{ gap: 8 }}>
          <span className="small muted">Popular:</span>
          {popular.map((p) => <button key={p} className="chip" onClick={() => nav(`/research/${region}/${p}`)}>{p}</button>)}
        </div>
      </section>
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
    <section className="card stack" style={{ gap: 8 }} aria-labelledby="inv-events-h" data-testid={testId}>
      <div className="spread" style={{ gap: 8 }}>
        <h2 id="inv-events-h" className="h3">Coming up</h2>
        <Link to="/trade/events" className="link small">Market events →</Link>
      </div>
      {next === null ? <PanelSkel label="Reading the market events" lines={1} /> : (
        <div className="space-events">
          {next.map((e) => <span key={e.id} className="small"><span className="muted">{evDay(e.date)}</span> {e.title}</span>)}
        </div>
      )}
    </section>
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
      {rows === null ? <PanelSkel label="Checking results dates" />
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
        : data === null ? <PanelSkel label="Reading your companies' filings" />
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

const MONEY_ICONS: Record<string, (p: { size?: number }) => ReactNode> = { book: Book, receipt: Receipt, wallet: Wallet, layers: Layers, calendar: Calendar, compass: Compass };

export function MoneyHome() {
  // the first four Money tools on the strip, the rest under the panels: each Money feature shows once
  const strip = NAV_GROUPS.Money.slice(0, 4), rest = NAV_GROUPS.Money.slice(4);
  const tools: Tool[] = strip.map((e, i) => {
    const Icon = MONEY_ICONS[e.icon ?? ""] ?? Compass;
    return { to: e.to, icon: <Icon size={18} />, title: e.label, line: e.title ?? e.blurb ?? "", lead: i === 0, data: { "data-money": e.to } };
  });
  return (
    <div className="space-home">
      <Top />
      <Head eyebrow="Money · seen only by you" title="Your money">
        What you own and what it means at tax time, from your own files. Facts and arithmetic.
      </Head>
      <ToolStrip label="Money tools" tools={tools} />
      <div className="grid2 space-panels">
        <HoldingsSummary />
        <TaxSummary />
      </div>
      {rest.length > 0 && (
        <section className="stack" style={{ gap: 10 }} aria-labelledby="money-tools">
          <h2 id="money-tools" className="h2">More in Money</h2>
          <div className="explore-grid">
            {rest.map((e) => (
              <Link key={e.to} to={e.to} className="card explore-card" data-money={e.to}><b>{e.label}</b><span className="small muted">{e.blurb ?? e.title}</span></Link>
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
    <Panel title="My Holdings" right={<Link to="/holdings" className="link">Open →</Link>}>
      {h === null ? <PanelSkel figs label="Adding up your holdings" />
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
      {t === null ? <PanelSkel figs label="Working out this year's gains" />
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


/* ---------- All: the newest features and each space's top tools ---------- */
type Fresh = { to: string; title: string; line: string; flag?: string };
/** What shipped on 5 Oct 2026, by space. A badge shows only where the feature is on a paid plan (plans.ts). */
const NEW_ON: { id: string; label: string; items: Fresh[] }[] = [
  { id: "trade", label: "Trade", items: [
    { to: "/trade/events", title: "Market events", line: "RBI policy, data releases, the Fed, index changes and expiries in one dated list." },
    { to: "/trade/closing-auction", title: "Closing auction", line: "Each F&O stock's reference, indicative and final price from 15:15 to 15:35." },
    { to: "/trade/replay", title: "Chart replay", line: "Practise on past candles with the future hidden; trades go to your journal.", flag: "chart_replay" },
    { to: "/trade/signals", title: "Signals", line: "Send TradingView or Chartink alerts into paper trading.", flag: "signal_webhooks" },
    { to: "/trade/positioning/stocks", title: "Stock futures", line: "Open interest buildup, rollover, basis and MWPL use, in the Positioning tab.", flag: "stock_futures" },
    { to: "/trade/positioning", title: "India VIX", line: "Today's level and history, and a VIX band for options sessions." },
    { to: "/options", title: "Strike picking", line: "In the options builder: strikes picked by delta or premium.", flag: "strike_rules" },
  ] },
  { id: "invest", label: "Invest", items: [
    { to: "/invest/business-updates", title: "Business updates", line: "Monthly and quarterly company updates read into numbers.", flag: "biz_updates" },
    { to: "/invest/holders", title: "Named holders", line: "Search a holder named above 1% across companies.", flag: "holders" },
    { to: "/invest/stock-lending", title: "Stock lending", line: "Lending fees that traded for the stocks you hold and watch." },
    { to: "/invest/margin-funding", title: "Margin funding", line: "Margin-funded amounts per stock and for the market.", flag: "mtf" },
    { to: "/money/sip-test", title: "SIP test", line: "What a SIP would have done on past prices, from every start month.", flag: "sip_luck" },
  ] },
  { id: "money", label: "Money", items: [
    { to: "/money/rates", title: "Rates", line: "Small savings, T-bills and bond yields, after your tax.", flag: "rates_slab" },
    { to: "/money/net-worth", title: "Loan check", line: "In Net worth: is a floating rate following its benchmark.", flag: "loan_check" },
    { to: "/money/mutual-funds", title: "Your return against the fund's", line: "In Mutual funds, in rupees.", flag: "mf_behaviour" },
  ] },
  { id: "account", label: "Account", items: [
    { to: "/account", title: "AI assistant", line: "StratLab's data and paper orders in your AI assistant.", flag: "assistant" },
  ] },
];
const NEW_FOLDED = 2;       // items per space while the list is folded

function PlanTag({ flag }: { flag?: string }) {
  const plan = flag ? planOf(flag) : "free";
  return plan === "free" ? null : <span className="badge fact all-plan" title={`${PLAN_NAME[plan]} plan`}>{PLAN_NAME[plan]}</span>;
}

function NewList() {
  const [all, setAll] = useState(false);
  const total = NEW_ON.reduce((n, g) => n + g.items.length, 0);
  return (
    <section className="card stack" style={{ gap: 12 }} aria-labelledby="all-new-h" data-testid="all-new">
      <div className="spread" style={{ gap: 8, flexWrap: "wrap" }}>
        <h2 id="all-new-h" className="h3">New <span className="small muted">· shipped 5 Oct 2026</span></h2>
        <button className="btn quiet sm" aria-expanded={all} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${total}`}</button>
      </div>
      <div className="all-new">
        {NEW_ON.filter((g) => all || g.id !== "account").map((g) => (
          <div key={g.id} className="stack" style={{ gap: 4, minWidth: 0 }}>
            <span className="eyebrow">{g.label}</span>
            {g.items.slice(0, all ? undefined : NEW_FOLDED).map((f) => (
              <Link key={f.to + f.title} to={f.to} className="all-new-row" data-new={f.title}>
                <span className="all-new-name"><b>{f.title}</b><PlanTag flag={f.flag} /></span>
                <span className="tiny muted">{f.line}</span>
              </Link>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

/** The next step on the All home. Their focus picks the space it points at (Trade when they asked for all of it). */
function AllNext() {
  const { focus } = useApp();
  const [rows, setRows] = useState<number | null>(null);
  useEffect(() => { api<Holdings>("/holdings").then((h) => setRows(h.rows.length)).catch(() => setRows(0)); }, []);
  const [region, setRegion] = useState<Region>("IN");
  if (focus === "invest") return (
    <section className="card stack space-next" aria-label="Find a company">
      <h2 className="h3">Which company do you want to look into?</h2>
      <div className="seg" role="radiogroup" aria-label="Market" style={{ alignSelf: "flex-start" }}>
        {(["IN", "US"] as const).map((r) => <button key={r} role="radio" aria-checked={region === r} aria-pressed={region === r} onClick={() => setRegion(r)}>{r === "IN" ? "₹ India" : "$ United States"}</button>)}
      </div>
      <CompanySearch region={region} />
    </section>
  );
  if (focus === "money") return (
    <section className="card space-next" aria-labelledby="next-h">
      <div className="spread" style={{ flexWrap: "wrap", gap: 12 }}>
        <h2 id="next-h" className="h3">{rows === 0 ? "Start here: add your holdings" : "Your money"}</h2>
        {rows === null ? <span className="skel" style={{ width: 120, height: 32 }} aria-hidden="true" />
          : rows === 0 ? <Link to="/holdings" className="btn">Add your holdings</Link>
          : <div className="row wrap" style={{ gap: 8 }}><Link to="/tax-report" className="btn quiet sm">Tax report</Link><Link to="/holdings" className="btn sm">Open My Holdings</Link></div>}
      </div>
    </section>
  );
  return <NextIdea count={1} />;
}

/** One space's row on the All home: its top three tools and the way into its home. */
function SpaceRow({ id, tools }: { id: "trade" | "invest" | "money"; tools: Tool[] }) {
  const label = SPACES[id].label;
  return (
    <section className="stack" style={{ gap: 8 }} aria-labelledby={`all-${id}-h`} data-space-row={id}>
      <div className="spread" style={{ gap: 8 }}>
        <h2 id={`all-${id}-h`} className="h3">{label}</h2>
        <Link to={SPACES[id].home} className="link small">Open {label} home →</Link>
      </div>
      <nav className="space-strip all-strip" aria-label={`${label} tools`}>
        {tools.map((t) => (
          <Link key={t.to} to={t.to} className="card space-card" {...t.data}>
            <span className="space-card-title">{t.icon}<b>{t.title}</b></span>
            <span className="small muted all-card-line">{t.line}</span>
          </Link>
        ))}
      </nav>
    </section>
  );
}

export function AllHome() {
  const { setSpace } = useApp();
  useEffect(() => { setSpace("all", false); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const money: Tool[] = NAV_GROUPS.Money.slice(0, 3).map((e) => {
    const Icon = MONEY_ICONS[e.icon ?? ""] ?? Compass;
    return { to: e.to, icon: <Icon size={18} />, title: e.label, line: e.title ?? e.blurb ?? "", data: { "data-money": e.to } };
  });
  return (
    <div className="space-home" data-testid="all-home">
      <Top />
      <Head eyebrow="All · Trade, Invest and Money" title="Everything in one place">
        What is new, and the top tools of each space.
      </Head>
      <AllNext />
      <NewList />
      <SpaceRow id="trade" tools={TRADE_TOP} />
      <SpaceRow id="invest" tools={INVEST_STRIP.slice(0, 3)} />
      <SpaceRow id="money" tools={money} />
      <NextEvents limit={2} testId="all-events" />
    </div>
  );
}
