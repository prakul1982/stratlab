import { NoBreak } from "../components/NoBreak";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { IST, asOf, dayIn, firstName, fmtTime, inr, inrCompact, pct, price, signedInrCompact } from "../lib/format";
import { mergeLiveNetWorth, netWorthDelta, pricedMarkets, restatedNote, sinceNote } from "../lib/networth";
import { inWords, marketState, usSettling, usTodayNote } from "../lib/marketHours";
import { useMinute } from "../lib/clock";
import { useLiveRefresh } from "../lib/liveRefresh";
import { useMarketsLive } from "../lib/marketLive";
import { MARKET_TILES, STRIP_MARKETS, goldInr10g, moverDay, tileMarket, tileToday, tileWhen, useComingUpAll, useMarketStrip, type Up } from "../lib/mine";
import { goldLineParts, type IndiaGold } from "../lib/gold";
import { fmtDate, monthShort } from "../lib/format";
import { CARDS, DEFAULT_LAYOUT, cleanLayout, slotSpans, type CardId, type Layout } from "../lib/mineLayout";
import { usePersisted } from "../lib/persist";
import { useAfterPaint } from "../lib/defer";
import { researchApi, savedRegion, useWatchlist, type Quote, type Region } from "../lib/research";
import { greetingAt, greetingZone, hourIn } from "../lib/greeting";
import type { LiveRow } from "../lib/types";
import { Badge, Card, CardHead, Delta, EmptyState, ErrorState, PageHeader, Signed, Skeleton, Spark, Stat } from "../components/kit";
import { FirstSteps } from "../components/FirstSteps";
import { PromoCountdown } from "../components/PromoCountdown";
import { PlanInline } from "../components/PlanInterest";
import { notRunning } from "../lib/tradeUi";


/* /mine: "My space", the person's own home. Every figure is read from what the app already has (net worth, holdings, paper
 * sessions, the markets, the calendars, the watchlist); a card with nothing to show says so and offers the next step.
 * Cards can be hidden and reordered with "Customise"; the choice is kept on the account, so a phone and a laptop show the
 * same My space (DI-006), and the cards are drawn in that order (DI-005). */

const LAYOUT_KEY = "stratlab.mine.cards";

// in India's time for someone who follows the Indian market, else their own (lib/greeting) (R5O-031)
const zone = () => { let z: string | undefined; try { z = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { /* old browser */ } return greetingZone(savedRegion(), z); };
const greeting = () => greetingAt(hourIn(zone()));
const ownZone = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return undefined; } };
// the day in India for someone who follows the Indian market says so when their own clock is elsewhere, beside the banner's
// "your time" (DI-011: "Sunday, 25 October" over "Sat 21:00 your time")
const dateLine = () => new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: zone() }).replace(/^(\w+) /, "$1, ")
  + (zone() === "Asia/Kolkata" && ownZone() && ownZone() !== "Asia/Kolkata" && ownZone() !== "Asia/Calcutta" ? " in India" : "");
/** A long explanation shows its first sentence whole (the rest is in the tooltip and the calendar), not cut mid-sentence with "…" (VR1-003). */
const firstSentence = (t: string) => { const m = t.length > 110 ? t.match(/^.{20,}?[.!?](?=\s)/) : null; return m ? m[0] : t; };
const dayNum = (iso: string) => { const [y, m, d] = iso.split("-").map(Number); const t = new Date(y, m - 1, d); return { d: t.getDate(), m: monthShort(t), w: t.toLocaleDateString("en-GB", { weekday: "short" }) }; };

export function MineHome() {
  const { setSpace, session, markets, me, savePrefs } = useApp();
  useEffect(() => { setSpace("mine", false); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  // the account's layout; this browser's copy (kept from before, and while the account loads) until one is saved there
  const [raw, setRaw] = usePersisted<Layout>(LAYOUT_KEY, DEFAULT_LAYOUT);
  const saved = me?.prefs?.mine;
  const layout = useMemo(() => cleanLayout(saved ?? raw), [saved, raw]);
  const [customise, setCustomise] = useState(false);
  // the calendars (the money calendar, market events, results) are below the first screen: they are read once the page has
  // painted, so the net worth, holdings and prices at the top get the connections first (R9R-010)
  const later = useAfterPaint();
  const upAll = useComingUpAll(later);
  const coming = upAll ? upAll.slice(0, 6) : null;
  const first = firstName(session?.user?.user_metadata as Record<string, unknown> | undefined);
  const shown = layout.order.filter((id) => !layout.hidden.includes(id));

  const now = useMinute();
  // one line: when the market opens or closes. The next dates are the first rows of "Coming up" right below, so they are not said twice
  // (VR1-003: the heading line repeated the first two rows)
  const lede = useMemo(() => {
    const m = markets.find((x) => x.id === "IN");
    const st = m && m.status !== "soon" ? marketState(m, new Date(now)) : null;     // the same minute the line counts from
    if (st && !st.offline) {
      const mins = st.change ? (st.change.getTime() - now) / 60000 : null;
      if (st.open && mins !== null) return `Indian markets close in ${inWords(mins)}.`;
      if (st.closedFor) return `Indian markets are closed ${st.closedFor === "weekend" ? "for the weekend" : "today for a holiday"}${mins !== null ? `, and open in ${inWords(mins)}` : ""}.`;
      if (mins !== null) return `Indian markets open in ${inWords(mins)}.`;
    }
    return "Your money, the markets and what is coming up, in one place.";
  }, [markets, now]);

  const change = (next: Layout) => { setRaw(next); void savePrefs({ mine: next }, true); };
  const cardFor = (id: CardId) => ({
    networth: <NetWorthCard />, pnl: <PnlCard />, paper: <PaperCard />, markets: <MarketsCard later={later} />, coming: <ComingCard rows={coming} more={upAll ? upAll.length - (coming?.length ?? 0) : 0} />, watch: <WatchCard />,
  })[id];
  // each card's width from its place in the chosen order, so the grid keeps that order with no gaps (DI-005)
  // VR6-010: an empty watchlist is one short message: it takes its own row (Coming up widens to fill the one before), instead of standing
  // beside six dated rows with 230px of nothing under it. Until the list is read the two keep sharing the row.
  const { items: watchItems } = useWatchlist();
  const spans = slotSpans(shown, watchItems !== null && watchItems.length === 0 ? ["watch"] : []);

  return (
    <div className="space-home mine" data-testid="mine-home">
      <PageHeader eyebrow={dateLine()} title={`${greeting()}${first ? `, ${first}` : ""}`} lede={lede}
        actions={<button type="button" className="btn quiet sm" aria-expanded={customise} aria-controls="mine-customise" onClick={() => setCustomise(!customise)}>Customise</button>} />
      {/* right under the button that opens it, not below the first steps and out of sight on a laptop (DI-012) */}
      {customise && <CustomisePanel layout={layout} onChange={change} onDone={() => {
        // closed with Done or Escape: focus goes back to the Customise button, not to the top of the page
        setCustomise(false);
        requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('[aria-controls="mine-customise"]')?.focus());
      }} />}
      {/* one line with the next step, so the first screen holds the person's own numbers (LIVE1B-086: a 375px checklist came first); the whole list is on each space's home */}
      <PromoCountdown /><FirstSteps compact />
      {shown.length === 0 ? (
        <EmptyState title="Every card is hidden" action={{ label: "Show the cards", onClick: () => { change(DEFAULT_LAYOUT); } }}>Use Customise to choose what My space shows.</EmptyState>
      ) : (
        <div className="mine-grid">
          {shown.map((id) => <div key={id} className="mine-slot" data-card={id} data-span={spans[id]}>{cardFor(id)}</div>)}
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
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape" && !e.defaultPrevented) onDone(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onDone]);
  return (
    <Card id="mine-customise" label="Customise My space">
      <CardHead title="Customise My space" info="Choose which cards show and put them in your order. It is kept with your account, so your phone and laptop show the same My space. On a wide screen, cards share a row when they fit."
        actions={<><button type="button" className="btn quiet sm" onClick={() => onChange(DEFAULT_LAYOUT)}>Reset</button><button type="button" className="btn sm" onClick={onDone}>Done</button></>} />
      <ul className="mine-custom">
        {layout.order.map((id, i) => (
          <li key={id}>
            <label className="k-check"><input type="checkbox" checked={!layout.hidden.includes(id)} onChange={() => toggle(id)} /> {label(id)}</label>
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
  as_of: string; totals: { assets: number; liabilities: number; net: number; partial?: string[] | null }; assets: unknown[]; liabilities: unknown[];
  history: { d: string; net: number; partial?: string[]; added?: number; m?: number }[] | null; history_allowed: boolean; valuation?: number;
};

function NetWorthCard() {
  const [v, setV] = useState<NwView | null | "none">(null);
  useEffect(() => { api<NwView>("/money/net-worth").then(setV).catch(() => setV("none")); }, []);
  // the values again each minute while a market trades: only what moves with prices (the server leaves out the history and the
  // deposits' tax), merged into the page as it is; a read that fails changes nothing (LIVE-1)
  const live = useMarketsLive(v !== null && v !== "none" ? pricedMarkets(v.assets as { kind: string; basis?: string }[]) : []);
  useLiveRefresh(live, () => {
    api<Partial<NwView>>("/money/net-worth?live=true").then((x) => setV((cur) => (cur && cur !== "none" ? mergeLiveNetWorth(cur, x) : cur))).catch(() => undefined);
  });
  if (v === null) return <Card testId="mine-networth"><Skeleton label="Adding up what you own" lines={5} /></Card>;
  if (v === "none" || v.assets.length + v.liabilities.length === 0) {
    return (
      <Card testId="mine-networth">
        <EmptyState title="Net worth" action={{ label: "Add what you own", to: "/money/net-worth" }}>Your net worth shows here once you add your stocks, funds, deposits and loans.</EmptyState>
      </Card>
    );
  }
  const hist = v.history ?? [];
  // as on the Net worth page: the change is against the latest complete snapshot from before today, none while the live
  // total is partial; the chart leaves out partial snapshots, which read as falls
  const whole = hist.filter((h) => !h.partial?.length);
  // RC2B-001: the page's rule exactly: a snapshot valued another way is no start for the change, and the note says why
  const move = netWorthDelta(v.totals.net, v.totals.partial, hist, undefined, v.valuation);
  const diff = move ? move.change : null;
  const restated = move ? null : restatedNote(hist, v.valuation, (d) => asOf(d) ?? d);
  return (
    <Card testId="mine-networth">
      <CardHead title="Net worth" actions={<Link className="btn quiet sm" to="/money/net-worth" aria-label="Open net worth">Open</Link>} />
      <Stat label="What you own minus what you owe" value={inrCompact(v.totals.net)}
        delta={diff !== null ? <Delta value={diff}>{signedInrCompact(diff)}</Delta> : undefined}
        note={move ? sinceNote(move, (d) => asOf(d) ?? d, inrCompact) : restated ?? `As of ${asOf(v.as_of) ?? "today"}`} />
      {/* two snapshots joined by a line read as a trend: the chart waits for a third (DI-012); until then the card shows the number alone, not a
          boxed dashed line that reads as a broken chart (VR1-005) */}
      {whole.length >= 3 ? <Spark values={whole.map((h) => h.net)} tone={diff !== null && diff < 0 ? "down" : "up"} area height={64} label="Net worth over time" />
        : !v.history_allowed && <HistoryPlaceholder />}
    </Card>
  );
}

/** What stands in for the chart on a plan without the history: one line, no boxed baseline (VR1-005). */
function HistoryPlaceholder() {
  return <p className="k-note k-muted" data-testid="mine-nw-placeholder">The history chart is on the Basic plan. <PlanInline /></p>;
}

/* ---------- today's P&L ---------- */
type Holdings = { rows: unknown[]; totals: { value: number; day: number | null; day_pct: number | null; count: number; no_cost?: { count: number; symbols: string[] } | null }; prices_at?: string | null; updated_at: string | null;
  us?: { day: number | null; in_total?: boolean } | null; usd_inr?: number | null };

function PnlCard() {
  const { markets } = useApp();
  const [h, setH] = useState<Holdings | null | "none">(null);
  useEffect(() => { api<Holdings>("/holdings").then(setH).catch(() => setH("none")); }, []);
  // the day's change and the prices' time again each minute while the stocks' markets trade; a read that fails keeps the last (LIVE-1)
  const live = useMarketsLive(["IN", "US"]);
  useLiveRefresh(live && h !== null && h !== "none" && h.rows.length > 0, () => { api<Holdings>("/holdings").then(setH).catch(() => undefined); });
  if (h === null) return <Card testId="mine-pnl"><Skeleton label="Reading your holdings" lines={5} /></Card>;
  if (h === "none" || !h.rows.length) {
    return (
      <Card testId="mine-pnl">
        <EmptyState title="Your P&L" action={{ label: "Add your holdings", to: "/holdings" }}>How your stocks moved today shows here once you bring in your holdings file.</EmptyState>
      </Card>
    );
  }
  const day = h.totals.day;
  // data from an earlier day is never titled "Today": out of hours the change is the last session's
  const fresh = !h.prices_at || dayIn(h.prices_at) === dayIn(new Date());
  return (
    <Card testId="mine-pnl">
      {/* one short title, the day in the figure's label, as Net worth ("What you own…") and Paper sessions ("Running now") beside it: "Last
          session's P&L" wrapped at 1280 and pushed Open onto a line of its own, so this card stood 77px taller than both (CI UI checker R13) */}
      <CardHead title="Your P&L" actions={<Link className="btn quiet sm" to="/holdings" aria-label="Open holdings">Open</Link>} />
      <Stat label={`${fresh ? "Today" : "Last session"} · ${h.totals.count} stock${h.totals.count === 1 ? "" : "s"}`} value={day == null ? "–" : signedInrCompact(day)} tone={day == null || day === 0 ? undefined : day > 0 ? "up" : "down"}
        note={day == null ? "The day's change needs prices, which are not in yet." : h.totals.day_pct != null ? <>Holdings <Signed value={day}>{pct(h.totals.day_pct, 2)}</Signed></> : undefined} />
      {/* the US part of the day named, live or at its close, as Holdings and Money say it (R7O-012) */}
      {(() => { const note = usTodayNote(markets, h.us, h.usd_inr); return note && <p className="k-note" data-testid="mine-us-today"><NoBreak text={note} /></p>; })()}
      {/* a stock with a price but no buy price is in the day's change, not in the value and gain or loss (R3D) */}
      {h.totals.no_cost && <p className="k-note" data-testid="mine-no-cost">Not in these totals: {h.totals.no_cost.symbols.join(", ")} ({h.totals.no_cost.count === 1 ? "no buy price" : "no buy prices"}), except Today, which includes {h.totals.no_cost.count === 1 ? "its" : "their"} change.</p>}
      {/* a note line like the other two cards' "As of": the pill under it made this card 40px taller than its neighbours (VR1-001) */}
      {h.prices_at && <p className="k-note">Prices as of {asOf(h.prices_at)}</p>}
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
      // VR6-017: the same shape as its neighbours (a title, one figure and a line), not a centred icon and three lines: beside Net worth and Your P&L
      // it stood 100px taller than they are, leaving both with an empty lower half
      <Card testId="mine-paper">
        <CardHead title="Paper sessions" />
        <Stat label="Running now" value="None running" note="Rules running live on real prices with fake money show here." />
        <div><Link className="btn sm" to="/paper">Start paper trading</Link></div>
      </Card>
    );
  }
  const running = rows.filter((r) => r.status === "running");
  const names = [...new Set(running.map((r) => r.instrument?.symbol).filter(Boolean))].slice(0, 3).join(", ");
  return (
    <Card testId="mine-paper">
      <CardHead title="Paper sessions" actions={<Link className="btn quiet sm" to="/paper" aria-label="Open paper sessions">Open</Link>} />
      <Stat label="Running now" value={running.length ? `${running.length} running` : "None running"}
        note={[names, ...notRunning(rows)].filter(Boolean).join(" · ") || undefined} />
    </Card>
  );
}

/* ---------- the markets ---------- */
function MarketsCard({ later }: { later: boolean }) {
  // the six levels (and gold in rupees) are read again each minute while India, the US, the dollar or gold trades (LIVE-1)
  const live = useMarketsLive(STRIP_MARKETS);
  const series = useMarketStrip(later, live);
  const [gold, setGold] = useState<IndiaGold | null>(null);
  useEffect(() => { if (later) api<IndiaGold>("/money/gold").then(setGold).catch(() => setGold(null)); }, [later]);
  useLiveRefresh(later && live, () => { api<IndiaGold>("/money/gold").then(setGold).catch(() => undefined); });
  const { markets } = useApp();
  // when the levels were read, for the line under the tiles: the newest of the six
  const readAt = Math.max(0, ...Object.values(series).map((s) => s?.at ?? 0));
  const closed = (id: string | null) => { const m = id ? markets.find((x) => x.id === id) : null; return !!m && !marketState(m).open; };
  // the US closing prints settle about 50 minutes after the bell (the server's SETTLE_MIN): until then a tile's last value is the last trade
  const settling = (id: string | null) => usSettling(id === "US" ? markets.find((x) => x.id === id) : null);
  const gline = series.gold ? goldLineParts(gold, series.usdinr ? goldInr10g(series.gold.last, series.usdinr.last) : null, inr) : null;
  const goldShort = gline?.short ?? null, goldMore = gline?.more ?? null;
  return (
    <Card testId="mine-markets" label="Markets">
      <CardHead title="Markets" info={<>Each line is the last month of daily closes; the change is the latest session against the one before, with its day when that session is not today. Indices are green or red by the day's move; the dollar and gold stay blue, as a rise in either is neither good nor bad.{goldMore && ` Gold: ${goldMore}`}</>} actions={<Link className="btn quiet sm" to="/research/pulse" aria-label="Open market pulse">Open</Link>} />
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
                    <span className="k-stat-d">{s.changePct != null ? <Delta value={s.changePct}>{pct(s.changePct, 2)}</Delta> : "No change to show"}
                      {/* a move that isn't today's says its day (R7T-003) */}
                      {s.changePct != null && (() => { const w = tileWhen(s.day, tileToday(t), (d) => fmtDate(d, { year: false }), closed(tileMarket(t)), !!tileMarket(t), settling(tileMarket(t)), !tileMarket(t)); return w && <span className={w.includes("settling") ? "k-note" : "k-note nowrap"} data-testid="mine-mkt-when"> {w}</span> /* "on 16 Oct" stays together (R53-008); the long settling words wrap inside the tile (R89-003) */; })()}</span>
                    <Spark values={s.values} tone={s.changePct != null && s.changePct < 0 ? "down" : "up"} label={`${t.label}, last month`} />
                  </>
                )}
            </div>
          );
        })}
      </div>
      {/* gold's rupee price as one short line under the tiles (inside its tile it ran to ten lines and made every tile as tall, UI-FIX-1); the world
          price and the duty between them, and what the line colours mean, are behind the (i) (VR1-002: two paragraphs of small print on a home card) */}
      {goldShort && <p className="k-note k-muted" data-testid="mine-gold-inr">Gold: {goldShort}</p>}
      {/* when the levels were read: the time moves with them as they are read again (LIVE-1); the same words whether a market is open or not, so the card does not change height at the open */}
      {readAt > 0 && <p className="k-note k-muted" data-testid="mine-mkt-at">Levels read at {fmtTime(readAt, { tz: IST, zone: true })}, and again each minute while a market is open.</p>}
    </Card>
  );
}

/* ---------- coming up ---------- */
function ComingCard({ rows, more = 0 }: { rows: Up[] | null; more?: number }) {
  return (
    <Card testId="mine-coming">
      <CardHead title="Coming up" actions={<Link className="btn quiet sm" to="/money/calendar" aria-label="Open the money calendar">Open</Link>} />
      {rows === null ? <Skeleton label="Reading your calendars" lines={3} />
        : !rows.length ? <EmptyState title="Nothing dated yet" action={{ label: "Open the money calendar", to: "/money/calendar" }}>Tax dates, results and dividends for your stocks and market events show here.</EmptyState>
        : (
          <ul className="mine-tl">
            {rows.map((u) => {
              const d = dayNum(u.date);
              return (
                <li key={u.key} className="mine-tl-i">
                  <span className="dt"><b>{d.d}</b>{d.m}</span>
                  <span className="body">{u.to ? <Link to={u.to}><b>{u.title}</b></Link> : <b>{u.title}</b>}{u.detail && <span className="k-stat-d" title={u.detail}>{firstSentence(u.detail)}</span>}</span>
                  {/* every row gives its weekday; a tax date keeps its colour (and says so to a screen reader) (R48-011) */}
                  <Badge tone={u.tone === "warn" ? "warn" : "plain"} dot={false}>{d.w}{u.tone === "warn" && <span className="sr-only"> · {u.tag} date</span>}</Badge>
                </li>
              );
            })}
          </ul>
        )}
      {/* the list is the next six: the rest are named as a count, not dropped in silence (DI-009) */}
      {more > 0 && <Link className="link k-small" to="/money/calendar" data-testid="mine-coming-more">+{more} more in the calendar</Link>}
    </Card>
  );
}

/* ---------- the watchlist today ---------- */
type Mover = { region: Region; symbol: string; name: string | null; q: Quote };

function WatchCard() {
  const { items, failed, retry } = useWatchlist();
  const { markets } = useApp();
  const day = (m: Mover) => { const mk = markets.find((x) => x.id === m.region); return moverDay(m.region, m.q, new Date(), !!mk && mk.status !== "soon" && !marketState(mk).open); };
  const [movers, setMovers] = useState<Mover[] | null>(null);
  // the prices of the watchlist's first 24 in each market, biggest movers first: read when the list arrives and again each minute
  // while a market trades, the rows shown kept when a read fails or finds no price (LIVE-1)
  const read = useCallback((items: NonNullable<ReturnType<typeof useWatchlist>["items"]>) =>
    Promise.all((["IN", "US"] as Region[]).map(async (r) => {
      const mine = items.filter((w) => w.region === r).slice(0, 24);
      if (!mine.length) return [] as Mover[];
      const q = await researchApi.quotes(r, mine.map((w) => w.symbol)).catch(() => ({} as Record<string, Quote | null>));
      return mine.flatMap((w) => (q[w.symbol]?.price != null ? [{ region: r, symbol: w.symbol, name: w.name, q: q[w.symbol]! }] : []));
    })).then((parts) => parts.flat().sort((a, b) => Math.abs(b.q.change_pct ?? 0) - Math.abs(a.q.change_pct ?? 0)).slice(0, 6)), []);
  useEffect(() => {
    if (items === null) return;
    if (!items.length) { setMovers([]); return; }
    let live = true;
    read(items).then((m) => { if (live) setMovers(m); });
    return () => { live = false; };
  }, [items, read]);
  const on = useRef(true);
  useEffect(() => { on.current = true; return () => { on.current = false; }; }, []);
  const trading = useMarketsLive(["IN", "US"]);
  useLiveRefresh(trading && !!items?.length && movers !== null, () => { void read(items!).then((m) => { if (on.current && m.length) setMovers(m); }); });
  // VR2-004: six rows each said "Mon 26 Oct" under the name: when every row is from the same earlier day it is said once, under the list
  const days = (movers ?? []).map((m) => day(m));
  const sameDay = days.length > 1 && days[0] && days.every((d) => d === days[0]) ? days[0] : null;
  return (
    <Card testId="mine-watch">
      <CardHead title={movers?.length && movers.every((m) => day(m)) ? "Your watchlist" : "Your watchlist today"} actions={<Link className="btn quiet sm" to="/research/watchlist" aria-label="Open the watchlist">Open</Link>} />
      {failed ? <ErrorState title="Your watchlist couldn't be opened" action={{ label: "Try again", onClick: retry }}>Nothing was changed.</ErrorState>
        : movers === null ? <Skeleton label="Reading your watchlist prices" lines={3} />
        : !movers.length ? (
          items && items.length
            ? <EmptyState title="No prices yet" action={{ label: "Open the watchlist", to: "/research/watchlist" }}>Today's prices for your watchlist are not available right now.</EmptyState>
            : <EmptyState title="Your watchlist is empty" action={{ label: "Find a company", to: "/research" }}>Press Watch on any company to follow it here, with the biggest movers first.</EmptyState>
        ) : (
          <>
          <ul className="mine-movers">
            {movers.map((m) => (
              <li key={`${m.region}-${m.symbol}`}>
                <Link to={`/research/${m.region}/${encodeURIComponent(m.symbol)}`}><b>{m.symbol}</b>{m.name && <span className="k-stat-d">{m.name}</span>}</Link>
                <span className="px">{price(m.q.price, m.region === "US" ? "USD" : "INR")}</span>
                <Delta value={m.q.change_pct}>{pct(m.q.change_pct, 2)}</Delta>
                {/* VR2-004: a row names its day only when the rows' days differ (India and the US can be on different sessions) */}
                {!sameDay && (() => { const d = day(m); return d && <span className="k-note" data-testid="mine-mover-day"> {fmtDate(d, { weekday: true, year: false })}</span>; })()}
              </li>
            ))}
          </ul>
          {sameDay && <p className="k-note" data-testid="mine-mover-day">Prices from {fmtDate(sameDay, { weekday: true, year: false })}</p>}
          </>
        )}
    </Card>
  );
}
