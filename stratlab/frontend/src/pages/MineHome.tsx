import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { asOf, dayIn, firstName, inr, inrCompact, pct, signedInrCompact } from "../lib/format";
import { evWhen } from "../lib/marketEvents";
import { inWords, marketState } from "../lib/marketHours";
import { MARKET_TILES, goldInr10g, useComingUp, useMarketStrip, type Up } from "../lib/mine";
import { CARDS, DEFAULT_LAYOUT, cleanLayout, type CardId, type Layout } from "../lib/mineLayout";
import { usePersisted } from "../lib/persist";
import { researchApi, useWatchlist, type Quote, type Region } from "../lib/research";
import type { LiveRow } from "../lib/types";
import { Badge, Card, CardHead, Delta, EmptyState, PageHeader, Signed, Skeleton, Spark, Stat } from "../components/kit";
import { FirstSteps } from "../components/FirstSteps";
import { PromoCountdown } from "../components/PromoCountdown";
import { PlanInline } from "../components/PlanInterest";

/* /mine: "My space", the person's own home. Every figure is read from what the app already has (net worth, holdings, paper
 * sessions, the markets, the calendars, the watchlist); a card with nothing to show says so and offers the next step.
 * Cards can be hidden and reordered with "Customise"; the choice is kept on this device. */

const LAYOUT_KEY = "stratlab.mine.cards";

const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };
const dateLine = () => { const d = new Date(); return `${d.toLocaleDateString("en-GB", { weekday: "long" })}, ${d.getDate()} ${d.toLocaleDateString("en-GB", { month: "long" })}`; };
const dayNum = (iso: string) => { const [y, m, d] = iso.split("-").map(Number); const t = new Date(y, m - 1, d); return { d: t.getDate(), m: t.toLocaleDateString("en-GB", { month: "short" }), w: t.toLocaleDateString("en-GB", { weekday: "short" }) }; };

export function MineHome() {
  const { setSpace, session, markets } = useApp();
  useEffect(() => { setSpace("mine", false); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const [raw, setRaw] = usePersisted<Layout>(LAYOUT_KEY, DEFAULT_LAYOUT);
  const layout = useMemo(() => cleanLayout(raw), [raw]);
  const [customise, setCustomise] = useState(false);
  const coming = useComingUp(6);
  const first = firstName(session?.user?.user_metadata as Record<string, unknown> | undefined);
  const shown = layout.order.filter((id) => !layout.hidden.includes(id));

  // one line: when the market opens or closes, then the next two dates from the calendars
  const lede = useMemo(() => {
    const parts: string[] = [];
    const m = markets.find((x) => x.id === "IN");
    const st = m && m.status !== "soon" ? marketState(m) : null;
    if (st && !st.offline) {
      const mins = st.change ? (st.change.getTime() - Date.now()) / 60000 : null;
      if (st.open && mins !== null) parts.push(`Indian markets close in ${inWords(mins)}.`);
      else if (st.closedFor) parts.push(`Indian markets are closed ${st.closedFor === "weekend" ? "for the weekend" : "today for a holiday"}${mins !== null ? `, and open in ${inWords(mins)}` : ""}.`);
      else if (mins !== null) parts.push(`Indian markets open in ${inWords(mins)}.`);
    }
    if (coming && coming.length) {
      const [a, b] = coming;
      parts.push(`Next up: ${a.title} on ${evWhen(a)}${b ? `, then ${b.title} on ${evWhen(b)}` : ""}.`);
    } else if (coming) parts.push("Nothing dated is coming up yet.");
    return parts.join(" ") || "Your money, the markets and what is coming up, in one place.";
  }, [markets, coming]);

  const change = (next: Layout) => setRaw(next);
  const cardFor = (id: CardId) => ({
    networth: <NetWorthCard />, pnl: <PnlCard />, paper: <PaperCard />, markets: <MarketsCard />, coming: <ComingCard rows={coming} />, watch: <WatchCard />,
  })[id];

  return (
    <div className="space-home mine" data-testid="mine-home">
      <PageHeader eyebrow={dateLine()} title={`${greeting()}${first ? `, ${first}` : ""}`} lede={lede}
        actions={<button type="button" className="btn quiet sm" aria-expanded={customise} aria-controls="mine-customise" onClick={() => setCustomise(!customise)}>Customise</button>} />
      <PromoCountdown /><FirstSteps />
      {customise && <CustomisePanel layout={layout} onChange={change} onDone={() => setCustomise(false)} />}
      {shown.length === 0 ? (
        <EmptyState title="Every card is hidden" action={{ label: "Show the cards", onClick: () => { change(DEFAULT_LAYOUT); } }}>Use Customise to choose what My space shows.</EmptyState>
      ) : (
        <div className="mine-grid">
          {shown.map((id) => <div key={id} className="mine-slot" data-card={id}>{cardFor(id)}</div>)}
        </div>
      )}
    </div>
  );
}

/* ---------- customise ---------- */
function CustomisePanel({ layout, onChange, onDone }: { layout: Layout; onChange: (l: Layout) => void; onDone: () => void }) {
  const label = (id: CardId) => CARDS.find((c) => c.id === id)!.label;
  const move = (id: CardId, by: -1 | 1) => {
    const i = layout.order.indexOf(id), j = i + by;
    if (j < 0 || j >= layout.order.length) return;
    const order = [...layout.order];
    [order[i], order[j]] = [order[j], order[i]];
    onChange({ ...layout, order });
  };
  const toggle = (id: CardId) => onChange({ ...layout, hidden: layout.hidden.includes(id) ? layout.hidden.filter((x) => x !== id) : [...layout.hidden, id] });
  return (
    <Card id="mine-customise" label="Customise My space">
      <CardHead title="Customise My space" info="Choose which cards show and put them in your order. It is kept on this device."
        actions={<><button type="button" className="btn quiet sm" onClick={() => onChange(DEFAULT_LAYOUT)}>Reset</button><button type="button" className="btn sm" onClick={onDone}>Done</button></>} />
      <ul className="mine-custom">
        {layout.order.map((id, i) => (
          <li key={id}>
            <label><input type="checkbox" checked={!layout.hidden.includes(id)} onChange={() => toggle(id)} /> {label(id)}</label>
            <span className="mine-move">
              <button type="button" className="btn quiet sm" aria-label={`Move ${label(id)} up`} disabled={i === 0} onClick={() => move(id, -1)}>↑</button>
              <button type="button" className="btn quiet sm" aria-label={`Move ${label(id)} down`} disabled={i === layout.order.length - 1} onClick={() => move(id, 1)}>↓</button>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/* ---------- net worth ---------- */
type NwView = {
  as_of: string; totals: { assets: number; liabilities: number; net: number }; assets: unknown[]; liabilities: unknown[];
  history: { d: string; net: number }[] | null; history_allowed: boolean;
};

function NetWorthCard() {
  const [v, setV] = useState<NwView | null | "none">(null);
  useEffect(() => { api<NwView>("/money/net-worth").then(setV).catch(() => setV("none")); }, []);
  if (v === null) return <Card testId="mine-networth"><Skeleton label="Adding up what you own" lines={5} /></Card>;
  if (v === "none" || v.assets.length + v.liabilities.length === 0) {
    return (
      <Card testId="mine-networth">
        <EmptyState title="Net worth" action={{ label: "Add what you own", to: "/money/net-worth" }}>Your net worth shows here once you add your stocks, funds, deposits and loans.</EmptyState>
      </Card>
    );
  }
  const hist = v.history ?? [];
  // the change against the snapshot nearest a month ago (or the first one, if there is less than a month)
  const base = hist.length >= 2 ? (hist.find((h) => new Date(h.d).getTime() >= Date.now() - 31 * 86400_000) ?? hist[0]) : null;
  const diff = base && base.d !== hist[hist.length - 1]?.d ? v.totals.net - base.net : null;
  return (
    <Card testId="mine-networth">
      <CardHead title="Net worth" actions={<Link className="btn quiet sm" to="/money/net-worth" aria-label="Open net worth">Open</Link>} />
      <Stat label="What you own minus what you owe" value={inrCompact(v.totals.net)}
        delta={diff !== null ? <Delta value={diff}>{signedInrCompact(diff)}</Delta> : undefined}
        note={diff !== null && base ? `since ${asOf(base.d)}` : `As of ${asOf(v.as_of) ?? "today"}`} />
      {hist.length >= 2 ? <Spark values={hist.map((h) => h.net)} tone={diff !== null && diff < 0 ? "down" : "up"} area height={64} label="Net worth over time" />
        : <HistoryPlaceholder allowed={v.history_allowed} />}
    </Card>
  );
}

/** The space under the net worth figure while there is no history to draw: a dashed baseline with today's dot, and why. */
function HistoryPlaceholder({ allowed }: { allowed: boolean }) {
  return (
    <div className="mine-nw-ph" data-testid="mine-nw-placeholder">
      <svg viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
        <path className="grid" d="M0 5H100" />
        <path className="base" d="M2 12H96" />
        <circle cx="97" cy="12" r="2.2" />
      </svg>
      <span className="k-note k-muted">{allowed ? "History starts after your first month" : <>The history chart is on the Basic plan. <PlanInline /></>}</span>
    </div>
  );
}

/* ---------- today's P&L ---------- */
type Holdings = { rows: unknown[]; totals: { value: number; day: number | null; day_pct: number | null; count: number }; prices_at?: string | null; updated_at: string | null };

function PnlCard() {
  const [h, setH] = useState<Holdings | null | "none">(null);
  useEffect(() => { api<Holdings>("/holdings").then(setH).catch(() => setH("none")); }, []);
  if (h === null) return <Card testId="mine-pnl"><Skeleton label="Reading your holdings" lines={5} /></Card>;
  if (h === "none" || !h.rows.length) {
    return (
      <Card testId="mine-pnl">
        <EmptyState title="Today's P&L" action={{ label: "Add your holdings", to: "/holdings" }}>How your stocks moved today shows here once you bring in your holdings file.</EmptyState>
      </Card>
    );
  }
  const day = h.totals.day;
  // data from an earlier day is never titled "Today": out of hours the change is the last session's
  const fresh = !h.prices_at || dayIn(h.prices_at) === dayIn(new Date());
  return (
    <Card testId="mine-pnl">
      <CardHead title={fresh ? "Today's P&L" : "Last session's P&L"} actions={<Link className="btn quiet sm" to="/holdings" aria-label="Open holdings">Open</Link>} />
      <Stat label={`${h.totals.count} stock${h.totals.count === 1 ? "" : "s"}`} value={day == null ? "–" : signedInrCompact(day)} tone={day == null || day === 0 ? undefined : day > 0 ? "up" : "down"}
        note={day == null ? "The day's change needs prices, which are not in yet." : h.totals.day_pct != null ? <>Holdings <Signed value={day}>{pct(h.totals.day_pct, 2)}</Signed></> : undefined} />
      {h.prices_at && <div><Badge>Prices as of {asOf(h.prices_at)}</Badge></div>}
    </Card>
  );
}

/* ---------- paper sessions ---------- */
function PaperCard() {
  const [rows, setRows] = useState<LiveRow[] | null>(null);
  useEffect(() => { api<LiveRow[]>("/live/sessions").then(setRows).catch(() => setRows([])); }, []);
  if (rows === null) return <Card testId="mine-paper"><Skeleton label="Opening your paper sessions" lines={5} /></Card>;
  if (!rows.length) {
    return (
      <Card testId="mine-paper">
        <EmptyState title="Paper sessions" action={{ label: "Start paper trading", to: "/paper" }}>Rules running live on real prices with fake money show here.</EmptyState>
      </Card>
    );
  }
  const running = rows.filter((r) => r.status === "running");
  const names = [...new Set(running.map((r) => r.instrument?.symbol).filter(Boolean))].slice(0, 3).join(", ");
  return (
    <Card testId="mine-paper">
      <CardHead title="Paper sessions" actions={<Link className="btn quiet sm" to="/paper" aria-label="Open paper sessions">Open</Link>} />
      <Stat label="Running now" value={running.length ? `${running.length} running` : "None running"}
        note={[names, rows.length > running.length ? `${rows.length - running.length} stopped` : ""].filter(Boolean).join(" · ") || undefined} />
    </Card>
  );
}

/* ---------- the markets ---------- */
function MarketsCard() {
  const series = useMarketStrip();
  return (
    <Card testId="mine-markets" label="Markets">
      <CardHead title="Markets" info="Each line is the last month of daily closes; the change is today against the close before." actions={<Link className="btn quiet sm" to="/research/pulse">Market pulse</Link>} />
      <div className="mine-markets">
        {MARKET_TILES.map((t) => {
          const s = series[t.id];
          return (
            <div key={t.id} className="mine-mkt" data-market={t.id}>
              <span className="k-stat-k">{t.label}{t.unit ? <span className="muted"> · {t.unit}</span> : null}</span>
              {s === undefined ? <span className="k-skel w70" aria-hidden="true" />
                : s === null ? <span className="k-stat-d">Not available right now</span>
                : (
                  <>
                    <span className="mine-mkt-v">{t.fmt(s.last)}</span>
                    {t.id === "gold" && series.usdinr && <span className="k-note">≈ {inr(goldInr10g(s.last, series.usdinr.last))} per 10 g</span>}
                    <span className="k-stat-d">{s.changePct != null ? <Delta value={s.changePct} tone={t.neutral ? "neutral" : "auto"}>{pct(s.changePct, 2)}</Delta> : "No change to show"}</span>
                    <Spark values={s.values} tone={t.neutral ? "neutral" : s.changePct != null && s.changePct < 0 ? "down" : "up"} label={`${t.label}, last month`} />
                  </>
                )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

/* ---------- coming up ---------- */
function ComingCard({ rows }: { rows: Up[] | null }) {
  return (
    <Card testId="mine-coming">
      <CardHead title="Coming up" actions={<Link className="btn quiet sm" to="/money/calendar">Calendar</Link>} />
      {rows === null ? <Skeleton label="Reading your calendars" lines={3} />
        : !rows.length ? <EmptyState title="Nothing dated yet" action={{ label: "Open the money calendar", to: "/money/calendar" }}>Tax dates, results and dividends for your stocks and market events show here.</EmptyState>
        : (
          <ul className="mine-tl">
            {rows.map((u) => {
              const d = dayNum(u.date);
              return (
                <li key={u.key} className="mine-tl-i">
                  <span className="dt"><b>{d.d}</b>{d.m}</span>
                  <span className="body">{u.to ? <Link to={u.to}><b>{u.title}</b></Link> : <b>{u.title}</b>}{u.detail && <span className="k-stat-d">{u.detail}</span>}</span>
                  <Badge tone={u.tone === "warn" ? "warn" : "plain"} dot={false}>{u.tone === "warn" ? u.tag : d.w}</Badge>
                </li>
              );
            })}
          </ul>
        )}
    </Card>
  );
}

/* ---------- the watchlist today ---------- */
type Mover = { region: Region; symbol: string; name: string | null; q: Quote };

function WatchCard() {
  const { items } = useWatchlist();
  const [movers, setMovers] = useState<Mover[] | null>(null);
  useEffect(() => {
    if (items === null) return;
    if (!items.length) { setMovers([]); return; }
    let live = true;
    Promise.all((["IN", "US"] as Region[]).map(async (r) => {
      const mine = items.filter((w) => w.region === r).slice(0, 24);
      if (!mine.length) return [] as Mover[];
      const q = await researchApi.quotes(r, mine.map((w) => w.symbol)).catch(() => ({} as Record<string, Quote | null>));
      return mine.flatMap((w) => (q[w.symbol]?.price != null ? [{ region: r, symbol: w.symbol, name: w.name, q: q[w.symbol]! }] : []));
    })).then((parts) => {
      if (live) setMovers(parts.flat().sort((a, b) => Math.abs(b.q.change_pct ?? 0) - Math.abs(a.q.change_pct ?? 0)).slice(0, 6));
    });
    return () => { live = false; };
  }, [items]);
  return (
    <Card testId="mine-watch">
      <CardHead title="Your watchlist today" actions={<Link className="btn quiet sm" to="/research/watchlist">All</Link>} />
      {movers === null ? <Skeleton label="Reading your watchlist prices" lines={3} />
        : !movers.length ? (
          items && items.length
            ? <EmptyState title="No prices yet" action={{ label: "Open the watchlist", to: "/research/watchlist" }}>Today's prices for your watchlist are not available right now.</EmptyState>
            : <EmptyState title="Your watchlist is empty" action={{ label: "Find a company", to: "/research" }}>Press Watch on any company to follow it here, with the biggest movers first.</EmptyState>
        ) : (
          <ul className="mine-movers">
            {movers.map((m) => (
              <li key={`${m.region}-${m.symbol}`}>
                <Link to={`/research/${m.region}/${encodeURIComponent(m.symbol)}`}><b>{m.symbol}</b>{m.name && <span className="k-stat-d">{m.name}</span>}</Link>
                <span className="px">{m.region === "US" ? "$" : "₹"}{(m.q.price ?? 0).toLocaleString(m.region === "US" ? "en-US" : "en-IN", { maximumFractionDigits: 2 })}</span>
                <Delta value={m.q.change_pct}>{pct(m.q.change_pct, 2)}</Delta>
              </li>
            ))}
          </ul>
        )}
    </Card>
  );
}
