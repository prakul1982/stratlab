import { NoBreak } from "../components/NoBreak";
import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../lib/api";
import { vixChange, type VixQuote } from "../lib/vix";
import { useApp } from "../lib/app";
import { useMarketRefresh } from "../lib/marketLive";
import { ago, fmtDate, istToday, money, pct, signCls } from "../lib/format";
import { uploadedLine } from "../lib/journalTax";
import { homeOf, startView } from "../lib/spaces";
import { homeRegion } from "../lib/homeMarket";
import { usTodayNote } from "../lib/marketHours";
import { pnlLabel, priceNote, type Closes } from "../lib/holdingsEdit";
import { NAV } from "../lib/nav";
import { PageTags } from "../components/PageTags";
import { evWhen, useEvents } from "../lib/marketEvents";
import { useWatchlist, REGION_NAME, type Region } from "../lib/research";
import type { LiveRow } from "../lib/types";
import { unreadLine, unreadSymbols } from "../lib/filingsText";
import { AsOf, Loading, PanelSkel, VerdictBadge } from "../components/ui";
import { Card, CardHead, Disclosure, FigureTable, PageHeader, Seg, Signed } from "../components/kit";
import { Panel, QuoteGrid } from "../components/Research";
import { SummaryLine, type FilingSummary } from "../components/Filings";
import { FirstSteps } from "../components/FirstSteps";
import { BreadthCard } from "../components/BreadthCard";
import { PromoCountdown } from "../components/PromoCountdown";
import { Explore } from "../components/Explore";
import { TileGrid } from "../components/TileGrid";
import { Book, Calendar, Compass, Layers, Library, Pulse, Search } from "../components/Icons";
import { resultDay, type ResultRow } from "./Research";
import { fyLink, movedYearNote, openFy, taxHasData, yearHasTrades } from "../lib/fy";
import { investStrip, withRegion } from "../lib/investUi";
import { notRunning } from "../lib/tradeUi";
import { PLAN_NAME, planOf } from "../lib/plans";

/* The three spaces' home pages: /trade, /invest and /money. `/` opens the one whose menu shows. Each reuses the
 * pages' own pieces; nothing here is new data, only what those pages already show, gathered.
 *
 * Every home has the same shape: a short heading, the one next step (start, or pick up where you left off), one row of
 * four equal tool cards, then one or two live panels and, last, the rest of the space's tools. */

/** `/`: the home of the space showing (for "All", of what the person came for). Waits for the account on a first visit. */
export function SpaceHome() {
  const { me, meError } = useApp();
  if (!me && !meError) return <Loading label="Opening StratLab" />;
  return <Navigate to={homeOf(startView(me?.prefs?.focus, me?.prefs?.space))} replace />;
}

/** The launch offer and the new-account checklist, right under every space home's heading. */
function Top({ onSteps, compact }: { onSteps?: (shown: boolean) => void; compact?: boolean }) {
  return <><PromoCountdown /><FirstSteps onShown={onSteps} compact={compact} /></>;
}

/** A space home's heading: the space's name, one question or title, one line under it. */
function Head({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return <PageHeader eyebrow={eyebrow} title={title} lede={children} />;
}

/** One tool on a space's strip. `status`: a live line (e.g. "2 running"); null while it loads (a placeholder of the
 * same height); left out, the card's foot says where it goes instead. */
type Tool = { to: string; icon: ReactNode; title: string; line: string; status?: ReactNode; plain?: boolean; go?: string; lead?: boolean; testId?: string; data?: Record<string, string>;
  /** the plan feature it needs: a plan without it sees which plan has it on the card (DP1-020) */
  flag?: string };

/** Four tools in one row of equal cards (two by two when the column is narrow). The lead tool is marked by its
 * border and tint, not its size. Every card has the same three lines, so the row never jumps when a status loads. */
function ToolStrip({ label, tools }: { label: string; tools: Tool[] }) {
  const { me } = useApp();
  const lockedOn = (flag?: string) => (flag && me?.plan_info.features?.[flag] === false ? PLAN_NAME[planOf(flag)] : null);
  return (
    <nav className="space-strip" aria-label={label}>
      {tools.map((t) => (
        <Link key={t.to} to={t.to} className={`k-linkcard space-card${t.lead ? " space-card-lead" : ""}`} {...t.data}>
          <span className="space-card-title">{t.icon}<b>{t.title}</b></span>
          <span className="small muted space-card-line">{t.line}</span>
          {t.status === null ? <span className="space-card-foot" aria-hidden="true"><span className="skel" /></span>
            : <span className={`small space-card-foot${t.status && !t.plain ? " live" : ""}`} data-testid={t.testId}>{lockedOn(t.flag) ? `On the ${lockedOn(t.flag)} plan →` : t.status || t.go || "Open →"}</span>}
        </Link>
      ))}
    </nav>
  );
}

/* ---------- Trade: the strategy lab ---------- */
/** Tools the strip and the positioning panel already link to: "more you can do" leaves them out. */
const TRADE_LINKED = ["/options", "/trade/positioning", "/paper", "/library", "/new", "/trade/journal"];
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
  // paused and stopped apart, as Paper trading and the Options builder list them (R84-013: "1 stopped" for a paused one)
  const tools: Tool[] = [
    { ...TRADE_TOP[0], status: rows === null ? null : options.length ? `${options.length} running` : "", go: "Build a structure →" },
    { ...TRADE_TOP[1], testId: "paper-summary",
      status: rows === null ? null : running.length ? `${running.length} running` : rows.length ? ["None running", ...notRunning(rows)].join(" · ") : "" },
    { ...TRADE_TOP[2],
      // the journal and the tax report are two uploads of different trades: F&O lines kept in the tax report as totals are not round trips here (R10O carry-over of R7M-013)
      ...(journal !== null && journal !== "none" && journal.count ? { line: "Your real trades as round trips, after charges. F&O lines in your tax report are kept there as totals, not counted here." } : {}),
      // the figure named: the trades' total after charges, not a per-trade expectancy (R7O-012: "11 closed trades · ₹3")
      status: journal === null ? null : journal !== "none" && journal.count
        // the amount's minus stays with its number on a narrow card (R57-003)
        // one span: the footer is a flex box, and loose pieces wrapped as "net / after / charge / s" (R58-003)
        ? <span>{plural(journal.count, "closed trade")} · <span className="nowrap">{money(journal.net, "INR")}</span> net after charges</span> : "",
      // a net loss isn't shown with the green "live" dot
      plain: journal !== null && journal !== "none" && journal.net < 0 },
    { to: "/library", icon: <Library size={18} />, title: "Strategy library", line: "Published rules, each with the result of its checks." },
  ];
  return (
    <div className="space-home">
      <Head eyebrow="Trade · your strategy lab" title="Test an idea, then trade it on paper">
        Years of real prices, real costs and four checks for luck. Fake money, never real orders.
      </Head>
      {/* today's market first, above the first-steps and "pick up" cards (RC2A-038: the data began at y=830 of a 900 px screen) */}
      <MarketStrip />
      <Top onSteps={setSteps} />
      {/* the checklist's first step is a first test: one guide at a time, so "Start here" waits until it's gone */}
      <NextIdea hideStart={steps} />
      <ToolStrip label="Trade tools" tools={tools} />
      <p className="k-small k-muted" data-testid="positioning-link">FII and DII flows, futures positions, PCR and India VIX are on <Link className="link tap-link" to="/trade/positioning">Positioning</Link>.</p>
      <Explore title="More you can do" hide={TRADE_LINKED} space="trade" />
    </div>
  );
}

type Brief = { cash?: { as_of: string | null; fii?: { net: number | null } }; fo_ban?: string[] };
type VixBrief = { value: number | null; value_day?: string | null; quote?: VixQuote | null };

/** Trade home's market strip (DC-001: the page had no market data, only a sentence pointing to Positioning): India VIX, the
 * FIIs' cash market net, the next F&O expiry and the stocks in the F&O ban period, each linking to its page. Each figure
 * shows its own day; one that can't be read says so and the others stay. */
function MarketStrip() {
  const [b, setB] = useState<Brief | null | "none">(null);
  const [vix, setVix] = useState<VixBrief | null | "none" | "slow">(null);
  useEffect(() => { api<Brief>("/trade/positioning?brief=true&pcr=false").then(setB).catch(() => setB("none")); }, []);
  useEffect(() => { api<VixBrief>("/trade/vix").then(setVix).catch(() => setVix("none")); }, []);
  // the one read that goes to a live feed can be slower than its three neighbours: after a few seconds the tile says so instead of a grey bar that
  // never ends, and takes the figure when it comes (LIVE1C-070)
  useEffect(() => { const t = window.setTimeout(() => setVix((v) => (v === null ? "slow" : v)), 6000); return () => window.clearTimeout(t); }, []);
  // India VIX is the one live figure here (the rest are the exchange's daily files): read again each minute while India trades,
  // the tile keeping its last value when a read fails (LIVE-1)
  useMarketRefresh(["IN"], () => { api<VixBrief>("/trade/vix").then(setVix).catch(() => undefined); }, vix !== null && vix !== "none" && vix !== "slow");
  const ev = useEvents();
  const today = istToday();
  const expiry = ev?.events.find((e) => e.kind === "expiry" && e.date >= today && !e.title.startsWith("SENSEX"));
  const fii = b && b !== "none" ? b.cash?.fii?.net ?? null : null;
  const ban = b && b !== "none" ? b.fo_ban ?? [] : null;
  const crore = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })} cr`;
  const tiles: { to: string; k: string; v: ReactNode; note: string; id: string }[] = [
    { id: "vix", to: "/trade/positioning#india-vix", k: "India VIX", v: vix === null ? null : vix === "none" || vix === "slow" || vix.value == null ? "–" : vix.value.toFixed(2),
      // a live quote comes with no day (the value is now's): its change stands in the line, so the tile is as tall as its three neighbours (VR2-013)
      note: vix && vix !== "none" && vix !== "slow" && vix.value_day ? fmtDate(vix.value_day, { year: false }) : vix === "none" ? "couldn't be read" : vix === "slow" ? "taking longer than usual"
        : vixChange(vix ? vix.quote ?? null : null) ?? "" },
    { id: "fii", to: "/trade/positioning#pos-cash", k: "FII/FPI cash, net", v: b === null ? null : fii == null ? "–" : <span className={signCls(fii)}>{crore(fii)}</span>,
      note: b && b !== "none" && b.cash?.as_of ? fmtDate(b.cash.as_of, { year: false }) : b === "none" ? "couldn't be read" : "" },
    { id: "expiry", to: "/trade/events", k: "Next F&O expiry", v: ev === null ? null : expiry ? fmtDate(expiry.date, { weekday: true, year: false }) : "–",
      note: expiry ? expiry.title : "" },
    { id: "ban", to: "/trade/positioning/stocks", k: "In the F&O ban", v: ban === null ? (b === "none" ? "–" : null) : String(ban.length),
      note: ban && ban.length ? ban.slice(0, 3).join(", ") + (ban.length > 3 ? ` and ${ban.length - 3} more` : "") : ban ? "no stock" : "" },
  ];
  return (
    <nav className="trade-market" aria-label="Market today" data-testid="trade-market">
      {tiles.map((t) => (
        <Link key={t.id} to={t.to} className="k-linkcard space-card" data-tile={t.id}>
          <span className="small muted">{t.k}</span>
          {t.v === null ? <span className="space-card-foot" aria-hidden="true"><span className="skel" /></span> : <b className="num">{t.v}</b>}
          <span className="small muted space-card-line">{t.note}</span>
        </Link>
      ))}
    </nav>
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
            {n.summary?.last_legacy ? <span className="tiny muted">Last run's figures not shown</span> : <VerdictBadge v={n.summary?.last_verdict} label={n.summary?.last_verdict === "no_edge" && typeof n.summary.last_return === "number" && n.summary.last_return <= -100 ? "Capital lost" : undefined} />}
          </Link>
        ))}
      </div>
    </Card>
  );
}

/* ---------- Invest: research ---------- */
/** Tools the strip and the panels on the Invest home already link to. */
const INVEST_LINKED = ["/invest/breadth", "/research/filings", "/research/investor", "/research/watchlist", "/research/rotation", "/research/scan", "/research", "/research/screens", "/research/corporate-actions"];

/** The strip's cards; where each opens (on the market picked at the top) is lib/investUi investStrip's. */
const INVEST_STRIP: Record<string, Omit<Tool, "to">> = {
  screens: { icon: <Search size={18} />, title: "Screener", lead: true, line: "Filter companies by plain facts: growth, debt, returns." },
  rotation: { icon: <Compass size={18} />, title: "Sector rotation", line: "Which sectors lead or lag the market, with their stocks." },
  scan: { icon: <Pulse size={18} />, title: "Trend scan", line: "Stocks in a rising trend with the Supertrend up.", flag: "scans" },
  dividends: { icon: <Calendar size={18} />, title: "Dividends", line: "Dividends, bonuses and splits ahead, for your stocks and all." },
};

export function InvestHome() {
  const [region, setRegion] = useState<Region>(homeRegion);
  // every card and link opens its page on the market picked here (review 5c)
  const tools: Tool[] = investStrip(region).map((t) => ({ ...INVEST_STRIP[t.key], to: t.to }));
  const { items: watching } = useWatchlist();
  // with nothing watched in this market, or one or two stocks (VR6-011): one or two stocks make a card a third as wide as the two dated cards stacked beside it, with an empty half under it and beside the tiles: with so
  // few they stack across the page as with none (LIVE1C-090)
  const fewWatched = watching !== null && watching.filter((w) => w.region === region).length <= 2;
  // the one Invest home: what you follow and the market around it. Looking up a company is its own page (Look up a company,
  // the menu's main button), so this page has no second search box (DD-002)
  return (
    <div className="space-home">
      {/* VR5-001: the eyebrow says something the crumb and the title do not (it was "Invest" over "Invest home") */}
      <Head eyebrow="Invest · companies and markets" title="Invest home">
        What your watchlist, results days and red flags say today, and the market around them. Facts, not tips. To open any
        company, use <Link to={`/research?region=${region}`} className="link">Look up a company</Link>.
      </Head>
      <Top compact />
      <div className="k-toolbar" aria-label="Market">
        <Seg label="Market" value={region} onChange={(v) => setRegion(v as Region)} options={[{ value: "IN", label: "₹ India" }, { value: "US", label: "$ United States" }]} />
      </div>
      <ToolStrip label="Invest tools" tools={tools} />
      {/* the watchlist beside the two short dated cards stacked (their heights add up to about its), then the red flags across the page,
          each flag on one line, then breadth: two short cards side by side left one with 40% of it empty, and the red flags beside the
          watchlist ended 100px short of it (VR1-010, VR1-011; before: DF-023, UI-FIX-1 R1/R2) */}
      {/* VR6-011: with nothing watched in this market the watchlist is one line: beside the two dated cards it stood 225px short of them,
          so the three stack across the page instead */}
      <div className={fewWatched ? "space-col" : "grid2 space-panels"}>
        <WatchPanel region={region} />
        {fewWatched ? <><NextEvents region={region} /><ResultsToday region={region} /></> : (
          <div className="space-col">
            <NextEvents region={region} />
            <ResultsToday region={region} />
          </div>
        )}
      </div>
      <RedFlags region={region} />
      <BreadthCard region={region} />
      <Explore title="More you can do" hide={INVEST_LINKED} space="invest" />
    </div>
  );
}

/** The next few market events (RBI policy, data releases, the Fed, index changes) on one line each, from the Events page. */
function NextEvents({ limit = 3, testId = "invest-events", region }: { limit?: number; testId?: string; region?: Region }) {
  const v = useEvents();
  // the US tab lists the US's own (the Fed, US data), not India's RBI and IIP (R71-004); India's holidays count (R72-005: the
  // evening before Tuesday's holiday, "Coming up" started at Wednesday's RBI minutes)
  const rest = v ? v.events.filter((e) => e.date >= v.today && e.kind !== "expiry" && (region !== "US" || e.kind === "us")).slice(0, limit) : null;
  // India's next F&O expiry too, one line among the rest (DF-023: "Coming up" left out the 27 Oct expiry); never every expiry
  const expiry = v && region !== "US" ? v.events.find((e) => e.date >= v.today && e.kind === "expiry") : undefined;
  const next = rest ? [...rest, ...(expiry ? [expiry] : [])].sort((a, b) => a.date.localeCompare(b.date)) : null;
  if (next && !next.length) return null;
  return (
    <Card testId={testId} label="Coming up">
      <CardHead title="Coming up" actions={<Link to="/calendar" className="link small">Calendar →</Link>} />{/* IA-1: the one Calendar, every date */}
      {next === null ? <PanelSkel label="Reading the market events" lines={1} /> : (
        <div className="space-events">
          {next.map((e) => <span key={e.id} className="small"><span className="muted">{evWhen(e)}</span> {e.title}</span>)}
        </div>
      )}
    </Card>
  );
}

/** The watchlist's prices for the market picked at the top (R9R-008: the US tab left India's panels in place). */
/** How many watchlist stocks the Invest home's card shows: six (three rows of two); the rest are one tap away. */
export const WATCH_SHOWN = 6;

function WatchPanel({ region }: { region: Region }) {
  const { items, failed, retry } = useWatchlist();
  const by = (r: Region) => (items ?? []).filter((w) => w.region === r);
  const regions = ([region] as Region[]).filter((r) => by(r).length);
  return (
    // VR5-owner-1 (the owner's choice for VR4-016): the first six, and "See all" for the rest in the header beside "At a glance", so the
    // card does not grow with the list and takes no line of its own under the tiles
    <Panel title="Your watchlist" right={<span className="k-card-actions">
      {(by(region).length > WATCH_SHOWN) && <Link to="/research/watchlist" className="link" data-testid="watch-see-all">See all {by(region).length} →</Link>}
      <Link to={withRegion("/research/investor", region)} className="link">At a glance →</Link></span>}>
      {items === null ? (failed
        ? <p className="small muted" role="alert">Your watchlist couldn't be opened. <button type="button" className="btn quiet sm" onClick={retry}>Try again</button></p>
        : <PanelSkel label="Opening your watchlist" />)
        : !regions.length ? <p className="small muted">{(items ?? []).length ? `None of your watchlist is in ${REGION_NAME[region]}. Press Watch on a ${REGION_NAME[region]} company to keep it here, with live prices.` : "Press Watch on any company to keep it here, with live prices."}</p>
        : regions.map((r) => (
          <div key={r} className="k-stack snug">
            {/* no "INDIA" over the stocks: the market is the toggle at the top of the page (VR5-owner-1: one line less, so the card ends level with its neighbours) */}
            <QuoteGrid region={r} fill={by(r).length <= 2} symbols={by(r).slice(0, WATCH_SHOWN).map((w) => w.symbol)} names={Object.fromEntries(by(r).map((w) => [w.symbol, w.name]))} />
          </div>
        ))}
    </Panel>
  );
}

type ResultsView = { today: string; weeks: { rows: ResultRow[] }[] };

/** Results days for your stocks in the market picked at the top: today's, else the next one. */
function ResultsToday({ region }: { region: Region }) {
  const [rows, setRows] = useState<{ today: ResultRow[]; next: ResultRow | null } | null>(null);
  useEffect(() => {
    let live = true;
    setRows(null);
    Promise.all(([region] as Region[]).map((r) => api<ResultsView>(`/research/results?region=${r}&scope=mine`).catch(() => null)))
      .then((views) => {
        if (!live) return;
        const all = views.flatMap((v) => (v ? v.weeks.flatMap((w) => w.rows).map((r) => ({ ...r, today: v.today })) : []));
        const today = all.filter((r) => r.date === r.today);
        const next = all.filter((r) => r.date > r.today).sort((a, b) => a.date.localeCompare(b.date))[0] ?? null;
        setRows({ today, next });
      });
    return () => { live = false; };
  }, [region]);
  return (
    <Panel title={region === "US" ? "US results today" : "Results today"} right={<Link to={withRegion("/research/results", region)} className="link">Calendar →</Link>}>
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
          <p className="small muted">None of your {REGION_NAME[region]} stocks has results today.{rows.next ? ` Next: ${rows.next.symbol} on ${resultDay(rows.next.date)}.` : ""}</p>
        )}
    </Panel>
  );
}

type Filings = { rows: { symbol: string; summary: FilingSummary; stale?: boolean }[]; problems?: string[] };

/** Held and watched companies with red flags filed lately (India; Basic and up, as on the red flags page). */
function RedFlags({ region }: { region: Region }) {
  const { me } = useApp();
  // until `me` has loaded the plan isn't known: the card shows its skeleton, never the Basic-plan note to a paying reader (R13S-003)
  const known = !!me;
  const allowed = !!me?.plan_info?.features?.filings;
  const [data, setData] = useState<Filings | null>(null);
  const [failed, setFailed] = useState(false);
  const [tries, setTries] = useState(0);
  const us = region === "US";
  useEffect(() => {
    if (!allowed || us) return;
    setData(null); setFailed(false);
    api<Filings>("/research/filings").then(setData).catch(() => setFailed(true));
  }, [allowed, us, tries]);
  const flagged = data?.rows.filter((r) => r.summary.red > 0) ?? [];
  // the feed not answering is not "you hold nothing": say which companies couldn't be read, and offer another try (R13S-002)
  const unread = unreadSymbols(data?.problems);
  const retry = <button type="button" className="btn quiet sm" onClick={() => setTries((n) => n + 1)}>Try again</button>;
  // this card reads India's exchange filings; US red flags are the Form 8-K items S&P 500 companies file with the SEC, listed
  // on the filings page's US tab (R9R-008, review 5c: the card said a US company's own page lists them, which it doesn't)
  if (us) {
    return (
      <Panel title="Red flags" right={<Link to="/research/filings?region=US" className="link">US filings →</Link>}>
        <p className="small muted" data-testid="invest-us-redflags">US red flags are read from the Form 8-K items S&P 500 companies file with the SEC: bankruptcy, delisting, auditor and officer changes. <Link className="link" to="/research/filings?region=US">See them for your watchlist or every company</Link>.</p>
      </Panel>
    );
  }
  return (
    <Panel title="Red flags in your holdings and watchlist" right={<Link to="/research/filings?region=IN" className="link">All filings →</Link>}>
      {!known ? <PanelSkel label="Checking your plan" />
        : !allowed ? <p className="small muted">Red flags for all your holdings and watchlist are on the Basic plan. Each company's own page shows its red flags on every plan.</p>
        : failed ? <p className="small muted" data-testid="invest-redflags-failed">{unreadLine([])} {retry}</p>
        : data === null ? <PanelSkel label="Reading your companies' filings" />
        : !data.rows.length && unread.length ? <p className="small muted" data-testid="invest-redflags-failed">{unreadLine(unread)} {retry}</p>
        : !data.rows.length ? <p className="small muted">You hold or watch no India stocks yet: their filings show here.</p>
        : !flagged.length ? (
          <>
            <p className="small muted">No red flags filed lately by the {data.rows.length} India compan{data.rows.length === 1 ? "y" : "ies"} you hold or watch.</p>
            {unread.length > 0 && <p className="small muted" data-testid="invest-redflags-failed">{unreadLine(unread)} {retry}</p>}
          </>
        ) : (
          <div className="k-stack snug">
            {/* the window said once, not at the start of every line (VR2-021) */}
            <p className="small muted" data-testid="invest-redflags-window">Last {flagged[0].summary.days} days</p>
            {flagged.slice(0, 5).map((r) => (
              <div key={r.symbol} className="space-line space-flag">
                <Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}#filings`}><b>{r.symbol}</b></Link>
                <SummaryLine bare s={r.summary} to={`/research/IN/${encodeURIComponent(r.symbol)}#filings`} />
              </div>
            ))}
            {unread.length > 0 && <p className="small muted" data-testid="invest-redflags-failed">{unreadLine(unread)} {retry}</p>}
          </div>
        )}
    </Panel>
  );
}

/* ---------- Money: what you own ---------- */
type Totals = { value: number; invested: number; pnl: number | null; pnl_pct: number | null; day: number | null; day_pct: number | null; count: number; priced?: number;
  pnl_partial?: { priced: number; lines: number } | null;
  no_cost?: { count: number; symbols: string[]; value: number } | null; other_session?: string[]; session?: string | null };
type Holdings = { rows: { value: number | null; market?: string }[]; totals: Totals; prices?: boolean; closes?: Closes; us?: (Totals & { in_total: boolean }) | null; usd_inr?: number | null; updated_at: string | null; prices_at?: string | null };
type TaxYear = { fy: number; label: string; count: number; intraday: { count: number }; business: { segments: unknown[] }; units?: unknown; tax_with_cess: number; stcg: { net: number }; ltcg: { net: number }; exemption: { left: number };
  total?: { available: boolean; total?: number; income?: { business?: number; intraday?: number } }; audit?: string | null };
type Tax = { years: TaxYear[]; current_fy: number; updated_at: string | null; last_trade?: string | null; prices_at: string | null; trades: number; business_lines?: number; mf?: { count: number } | null; us_trades?: number };


export function MoneyHome() {
  // the two summaries (holdings and tax) stand for their tools; every other Money tool is one card below, under the menu entry it
  // is a tab of (IA-1), so each feature shows once; of the shared Calendar, Money's own dates and the one list of every date
  const PANELS = ["/holdings", "/tax-report"];
  const entries = NAV.money.groups.map((g) => ({ g, pages: g.pages.filter((p) => !PANELS.includes(p.to) && ((p.space ?? "money") === "money" || p.to === "/calendar")) })).filter((x) => x.pages.length);
  return (
    <div className="space-home">
      <Head eyebrow="Money · seen only by you" title="Your money">
        What you own and what it means at tax time, from your own files. Facts and arithmetic.
      </Head>
      {/* DG-051: the first-steps list is about trading (a backtest, paper trading, a deep dive), so Money home leaves it to Home */}
      <PromoCountdown />
      {/* CK-2: each card its own height, notes directly under its figures: the tax card's explanation is behind its (i), so the two end near each other
          without one being stretched into a blank band (RC2B-040 had stretched them) */}
      <div className="grid2 space-panels money-panels">
        <HoldingsSummary />
        <TaxSummary />
      </div>
      {entries.length > 0 && (
        <section className="k-stack" aria-labelledby="money-tools">
          <h2 id="money-tools" className="k-card-title">More in Money</h2>
          {entries.map(({ g, pages }) => (
            <div key={g.id} className="k-stack" data-entry={g.id}>
              <div className="k-stack k-tight"><b>{g.label}</b><span className="small muted">{g.blurb}</span></div>
              {/* each card with its plan tag, as on the entry pages ("Basic for part"), and its line in full on a phone (DP2-014) */}
              <TileGrid className="explore-grid money-cards">
                {pages.map((p) => <Link key={p.to} to={p.to} className="k-linkcard explore-card" data-money={p.to}><b>{p.label}</b><span className="small muted">{p.blurb}</span><PageTags page={p} /></Link>)}
              </TileGrid>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

/** Why the gain or loss is missing: the prices not in yet (the feed off at a weekend), or no buy prices in the file. The
 * buy prices were there and the tile sent people to fix their file (DI-007). */
export function gainMissing(t: { count: number; priced?: number; no_cost?: { count: number } | null }): string {
  const noCost = t.no_cost?.count ?? 0;
  if (t.priced === 0 && noCost < t.count) return "Needs today's prices, not in yet";
  return "Needs the buy prices";
}

function HoldingsSummary() {
  const [h, setH] = useState<Holdings | null | "error">(null);
  const { markets } = useApp();
  useEffect(() => { api<Holdings>("/holdings").then(setH).catch(() => setH("error")); }, []);
  // value, gain or loss and Today again each minute while the stocks' markets trade; the tax card beside it is not read again (LIVE-1)
  useMarketRefresh(["IN", "US"], () => { api<Holdings>("/holdings").then(setH).catch(() => undefined); }, h !== null && h !== "error" && h.rows.length > 0);
  const usNote = h && h !== "error" ? usTodayNote(markets, h.us, h.usd_inr) : null;
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
            {(() => {
              const n = h.totals.count - (h.totals.no_cost?.count ?? 0);   // the lines the value is of
              const gone = h.totals.pnl == null;
              return (
                <FigureTable label="My Holdings totals" header="Holdings" valueHeader="Now" noteHeader="Change" rows={[
                  { key: "value", label: `Value · ${n} stock${n === 1 ? "" : "s"}`, value: money(h.totals.value, "INR") },
                  // DG-050: of the lines with a price only, said so, as My Holdings says it (DG-001)
                  { key: "pnl", label: pnlLabel("Gain or loss", h.totals.pnl_partial), tone: signCls(h.totals.pnl), value: gone ? <span className="k-muted">{gainMissing(h.totals)}</span> : money(h.totals.pnl!, "INR"),
                    note: h.totals.pnl_pct != null ? <Signed value={h.totals.pnl_pct}>{pct(h.totals.pnl_pct)}</Signed> : undefined },
                  // "Today" only of today's session: the session the change belongs to is named when it is an earlier day (R41A)
                  ...(h.totals.day != null ? [{ key: "day", label: h.totals.session && h.totals.session < istToday() ? "Last session" : "Today", tone: signCls(h.totals.day), value: money(h.totals.day, "INR") }] : []),
                  ...(h.us && h.us.count > 0 ? [{ key: "us", label: "US stocks", value: money(h.us.value, "USD"),
                    note: h.us.in_total && h.usd_inr ? `at ₹${h.usd_inr.toFixed(2)} a dollar` : undefined }] : []),
                ]} />);
            })()}
            {/* the same lines as My Holdings: one with a price but no buy price is named, not half counted (R5O-004) */}
            {h.totals.no_cost && <p className="small muted">Not in these totals: {h.totals.no_cost.symbols.join(", ")} ({h.totals.no_cost.count === 1 ? "no buy price" : "no buy prices"}), except Today, which includes {h.totals.no_cost.count === 1 ? "its" : "their"} change.</p>}
            {(() => { const n = priceNote(h.prices ?? true, h.closes, h.rows, (d) => fmtDate(d, { weekday: true, year: false })); return n && <p className="small muted" data-testid="holdings-prices">{n}{h.totals.pnl_partial ? " The gain or loss is of the lines with a price." : ""}</p>; })()}
            {usNote && <p className="small muted" data-testid="us-today"><NoBreak text={usNote} /></p>}
            {(h.totals.other_session?.length ?? 0) > 0 && <p className="small muted">Today leaves out {h.totals.other_session!.join(", ")}: {h.totals.other_session!.length === 1 ? "its" : "their"} last change is from an earlier session.</p>}
            <AsOf parts={[["Prices", h.prices_at], ["Holdings", h.updated_at]]} />
          </div>
        )}
    </Panel>
  );
}

function TaxSummary() {
  const [t, setT] = useState<Tax | null | "error">(null);
  useEffect(() => { api<Tax>("/tax").then(setT).catch(() => setT("error")); }, []);
  // the Money pages' one rule for the year (lib/fy openFy): the one being filed now, or the latest
  // year with sales when that has none (said in one line); the link to the tax report carries the year shown
  const ok = t && t !== "error" ? t : null;
  const open = ok ? openFy(ok.years.map((x) => x.fy), ok.current_fy, (fy) => ok.years.some((x) => x.fy === fy && yearHasTrades(x))) : null;
  const year = ok && open ? ok.years.find((y) => y.fy === open.fy) ?? null : null;
  // CK-2 (R1/R13): what the estimate assumes is behind the card's (i), not a three-line paragraph that made this card taller than My Holdings beside it
  const how = year?.total?.available ? "As the tax report works it out: the trades and other income in your files, at that year's slab and special rates, with surcharge and 4% cess." : "Assumes only the sales in the tradebooks you uploaded, matched first in, first out, at that year's rates after set-off and the yearly long-term exemption, with 4% cess and before any surcharge.";
  return (
    <Panel title={year ? `Tax, ${year.label}` : "Tax this year"} info={how} right={<Link to={year ? fyLink("/tax-report", year.fy) : "/tax-report"} className="link" data-money="/tax-report">Tax report →</Link>}>
      {t === null ? <PanelSkel figs label="Working out this year's gains" />
        : t === "error" ? <p className="small muted">The tax report couldn't be opened just now. <Link className="link" to="/tax-report">Try the page</Link>.</p>
        : !taxHasData(t) ? (
          <div className="k-stack start">
            <p className="small muted">Upload your broker's tradebooks to see each financial year's capital gains and the tax on them.</p>
            <Link to="/tax-report" className="btn sm">Add your tradebooks</Link>
          </div>
        ) : (
          <div className="k-stack" data-testid="tax-summary">
            <FigureTable label="Tax estimate" header="Tax" valueHeader="Amount" noteHeader={null} rows={[
              // the tax report's own total (capital gains, F&O and intraday business income, slab, surcharge and cess), so the
              // two pages agree; the capital gains part alone said ₹0 beside a report of ₹77,61,298
              { key: "total", label: "Total tax estimate", value: money(year?.total?.available ? year.total.total ?? 0 : year?.tax_with_cess ?? 0, "INR") },
              // where the tax comes from: the F&O and intraday income beside the gains (R6O-014: ₹77,61,298 beside −₹59 and ₹0)
              ...(year?.total?.income?.business ? [{ key: "biz", label: "F&O and other business income", tone: signCls(year.total.income.business), value: money(year.total.income.business, "INR") }] : []),
              ...(year?.total?.income?.intraday ? [{ key: "intra", label: "Intraday income", tone: signCls(year.total.income.intraday), value: money(year.total.income.intraday, "INR") }] : []),
              { key: "stcg", label: "Short-term gains", tone: signCls(year?.stcg.net), value: money(year?.stcg.net ?? 0, "INR") },
              { key: "ltcg", label: "Long-term gains", tone: signCls(year?.ltcg.net), value: money(year?.ltcg.net ?? 0, "INR") },
            ]} />
            {/* the tax audit fact (turnover, the report's date, the penalty) is seven lines: behind a fold, so this card is not twice My Holdings' height (LIVE1C-051) */}
            {year?.audit && <Disclosure summary="Tax audit (section 44AB)" testId="tax-audit"><p className="small">{year.audit}</p></Disclosure>}
            <p className="tiny muted">{year?.count ? `${year.count} sale${year.count === 1 ? "" : "s"} in ${year.label}.` : `No sales in ${year?.label ?? "this year"}.`}{year && open?.from != null ? ` ${movedYearNote(open.from, year.fy, ok!.current_fy, "sales")}` : ""} An estimate to check with your CA.</p>
            {(t.updated_at || t.last_trade) && <p className="tiny muted" data-testid="tax-uploaded">{uploadedLine(t.updated_at, t.last_trade, (iso) => fmtDate(iso, { tz: "Asia/Kolkata" }))}</p>}
            {/* no "Prices as of": nothing on this card is at today's price, only sales already made (R66-008) */}
          </div>
        )}
    </Panel>
  );
}
