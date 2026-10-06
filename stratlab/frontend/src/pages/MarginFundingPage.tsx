import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { axisInr, CRORE, inr, inrCompact, pct, pctPlain, signedInrCompact } from "../lib/format";
import { dayText, desksApi, sharesShort, type CostIn, type CostOut, type MtfChange, type MtfOne, type MtfPage } from "../lib/stockDesks";
import { LineChart } from "../components/Charts";
import { AlertButton } from "../components/AlertForm";
import { Info } from "../components/ui";
import { Card, CardHead, ChartFrame, DataTable, Delta, EmptyState, ErrorState, Field, FormActions, FormGrid, PageHeader, ResultBlock, Skeleton, Stat, StatRow, StockPicker, type Choice } from "../components/kit";

/* /invest/margin-funding: what brokers together had funded under the margin trading facility, for the whole market and
 * for each stock you hold or watch (the exchange's daily disclosure), and your own MTF position worked out. Dated facts
 * and arithmetic: no "risky" labels, no ranking, and the changes are drawn in neutral colours (a bigger book is not
 * good or bad news). Today's numbers and the calculator on every plan; history and the alert on a funded level on Basic.
 * Built from the kit (components/kit), amounts from lib/format. */

/** A change as "+₹296 cr (+0.2%)". The figures arrive in crore. */
const chg = (c: MtfChange | undefined) => (c ? `${signedInrCompact(c.crore * CRORE)} (${pct(c.pct, 1)})` : "–");
/** An exact figure in crore for tooltips and tables: ₹1,51,134.12 cr. */
const exact = (crore: number | null | undefined) => (crore == null ? "–" : `${inr(crore, 2)} cr`);
const cr = (crore: number | null | undefined) => (crore == null ? "–" : inrCompact(crore * CRORE));

const RANGE_DAYS: [string, string, number][] = [["1m", "1M", 31], ["3m", "3M", 93], ["1y", "1Y", 366]];

/** The range switch for a daily history: 1M / 3M / 1Y only where the stored days cover them, always "All". Slices by date. */
function useRange(days: string[]) {
  const [pick, setPick] = useState<string | null>(null);
  const span = days.length > 1 ? (Date.parse(days[days.length - 1]) - Date.parse(days[0])) / 86_400_000 : 0;
  const choices: Choice[] = useMemo(() => {
    const fit = RANGE_DAYS.filter(([, , d]) => span > d).map(([value, label]) => ({ value, label }));
    return fit.length ? [...fit, { value: "all", label: "All" }] : [];
  }, [span]);
  const range = choices.some((c) => c.value === pick) ? pick! : choices.some((c) => c.value === "3m") ? "3m" : "all";
  const keep = (day: string) => {
    const d = RANGE_DAYS.find(([v]) => v === range)?.[2];
    return d == null || days.length === 0 || (Date.parse(days[days.length - 1]) - Date.parse(day)) / 86_400_000 <= d;
  };
  return { choices, range, setPick, keep };
}

function Market({ p }: { p: MtfPage }) {
  const m = p.market;
  const h = useMemo(() => m.history ?? [], [m.history]);
  const { choices, range, setPick, keep } = useRange(h.map((x) => x.day));
  const shown = h.filter((x) => keep(x.day));
  const day = m.end != null && m.start != null ? m.end - m.start : null;
  const stats = m.as_of ? (
    <StatRow>
      <Stat label={`Funded on ${dayText(m.as_of).replace(/ \d{4}$/, "")}`} value={cr(m.end)} note={m.stocks != null ? `${m.stocks.toLocaleString("en-IN")} stocks` : undefined} />
      <Stat label="That day" value={day != null ? signedInrCompact(day * CRORE) : "–"} note={`${cr(m.fresh)} new · ${cr(m.liquidated)} closed`} />
      <Stat label="Over 30 days" value={m.d30 ? signedInrCompact(m.d30.crore * CRORE) : "–"}
        delta={m.d30 ? <Delta value={m.d30.crore} tone="neutral">{pct(m.d30.pct, 1)}</Delta> : undefined}
        note={m.d30 ? `since ${dayText(m.d30.from).replace(/ \d{4}$/, "")}` : "Needs 30 days of data"} />
    </StatRow>
  ) : null;
  let body;
  if (!m.as_of) body = <EmptyState title="No margin funding data yet">{p.status.reason ?? "The exchange's first disclosure will show here once it is published."}</EmptyState>;
  else if (!p.full) body = <p className="k-small k-muted">The book day by day is on the <Link className="link" to="/plans">{p.plan_needed} plan</Link>.</p>;
  else if (h.length < 2) body = <EmptyState title="Not enough days to draw yet">The chart appears once two days of the exchange's disclosure are in.</EmptyState>;
  else body = (
    <LineChart lines={[{ values: shown.map((x) => x.end), color: "var(--pos-call)", width: 2, label: "MTF book" }]} labels={shown.map((x) => dayText(x.day))} times={shown.map((x) => x.day)}
      ranges={false} table={false} format={exact} axisFormat={(v) => axisInr(v * CRORE)} height={180} ariaLabel="The market's margin-funded book by day, in rupees crore" />
  );
  const canTable = !!m.as_of && p.full && h.length >= 2;
  return (
    <ChartFrame title="The market's MTF book" info={p.about.book} stats={stats} ranges={canTable ? choices : undefined} range={range} onRange={setPick}
      table={canTable ? { label: "The market's margin-funded book by day", rows: [...shown].reverse(), rowKey: (r) => r.day,
        columns: [{ key: "day", header: "Day", rowHeader: true, cell: (r) => <b>{dayText(r.day)}</b> }, { key: "end", header: "Funded", numeric: true, cell: (r) => exact(r.end) },
          { key: "fresh", header: "New", numeric: true, cell: (r) => exact(r.fresh) }, { key: "liq", header: "Closed", numeric: true, cell: (r) => exact(r.liquidated) }] } : undefined}>
      {body}
    </ChartFrame>
  );
}

function OneStock({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const [d, setD] = useState<MtfOne | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    desksApi.mtfOne(symbol).then((x) => live && setD(x)).catch((e) => live && setError(e instanceof ApiError ? e.message : "That stock couldn't be read."));
    return () => { live = false; };
  }, [symbol]);
  const h = useMemo(() => d?.history ?? [], [d?.history]);
  const { choices, range, setPick, keep } = useRange(h.map((x) => x.day));
  const shown = h.filter((x) => keep(x.day));
  const actions = <>
    {d?.full && d.funded && <AlertButton region="IN" symbol={symbol} condition="mtf_above" label="Alert on a level" />}
    <button className="btn quiet sm" onClick={onClose}>Close</button>
  </>;
  const title = `${symbol}: margin funded`;
  if (error || !d || !d.funded) {
    return (
      <Card id="mtf-one">
        <CardHead title={title} actions={actions} />
        {error ? <ErrorState title="That stock couldn't be read">{error}</ErrorState>
          : !d ? <Skeleton label={`Reading ${symbol}`} lines={3} />
          : <EmptyState title={`No margin funding in ${d.as_of ? dayText(d.as_of) : "the newest disclosure"}`}>
              {d.as_of ? `${symbol} had no margin funding in the exchange's disclosure of ${dayText(d.as_of)}.` : "Nothing stored yet."}</EmptyState>}
      </Card>
    );
  }
  const canDraw = d.full && h.length >= 2;
  return (
    <ChartFrame id="mtf-one" title={title} actions={actions} ranges={canDraw ? choices : undefined} range={range} onRange={setPick}
      stats={
        <StatRow>
          <Stat label={`Funded on ${dayText(d.as_of).replace(/ \d{4}$/, "")}`} value={cr(d.crore)} note={d.pct_shares != null ? <>{pctPlain(d.pct_shares, 2)} of shares issued<Info label="Of shares issued">{d.about.pct_shares}</Info></> : undefined} />
          <Stat label="Shares funded" value={sharesShort(d.shares)} />
          <Stat label="Of market value" value={pctPlain(d.pct_mcap, 2)} note={<>at the close of {inr(d.close, 2)}<Info label="Of market value">{d.about.pct_mcap}</Info></>} />
          <Stat label="That day" value={d.day ? signedInrCompact(d.day.crore * CRORE) : "–"} delta={d.day ? <Delta value={d.day.crore} tone="neutral">{pct(d.day.pct, 1)}</Delta> : undefined} note={`30 days: ${chg(d.d30)}`} />
        </StatRow>
      }
      table={canDraw ? { label: `${symbol}'s margin funding by day`, rows: [...shown].reverse(), rowKey: (r) => r.day,
        columns: [{ key: "day", header: "Day", rowHeader: true, cell: (r) => <b>{dayText(r.day)}</b> }, { key: "crore", header: "Funded", numeric: true, cell: (r) => exact(r.crore) },
          { key: "shares", header: "Shares funded", numeric: true, cell: (r) => sharesShort(r.shares) }, { key: "pct", header: "Of shares issued", numeric: true, cell: (r) => pctPlain(r.pct_shares, 2) }] } : undefined}>
      {!d.full ? <p className="k-small k-muted" data-testid="mtf-locked">A year of {symbol}'s margin funding, and an alert when it crosses a level, are on the <Link className="link" to="/plans">{d.plan_needed} plan</Link>.</p>
        : h.length < 2 ? <EmptyState title="Not enough days to draw yet">The chart appears once two days of the exchange's disclosure are in.</EmptyState>
        : <LineChart lines={[{ values: shown.map((x) => x.crore), color: "var(--pos-call)", width: 2, label: "Funded" }]} labels={shown.map((x) => dayText(x.day))} times={shown.map((x) => x.day)}
            ranges={false} table={false} format={exact} axisFormat={(v) => axisInr(v * CRORE)} height={180} ariaLabel={`${symbol}'s margin-funded amount by day, in rupees crore`} />}
    </ChartFrame>
  );
}

const START: Record<keyof CostIn, string> = { buy: "1000", qty: "100", margin_pct: "25", rate_pct: "15", days: "30", charges: "", price: "", maint_pct: "" };

function Calculator() {
  const { fail } = useApp();
  const [f, setF] = useState(START);
  const [out, setOut] = useState<CostOut | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof CostIn) => (e: React.ChangeEvent<HTMLInputElement>) => setF((x) => ({ ...x, [k]: e.target.value }));
  const run = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const quiet = !e;
    const n = (k: keyof CostIn) => (f[k].trim() === "" ? null : Number(f[k]));
    const body = { buy: n("buy"), qty: n("qty"), margin_pct: n("margin_pct"), rate_pct: n("rate_pct"), days: n("days"), charges: n("charges") ?? 0,
      price: n("price"), maint_pct: n("maint_pct") ?? 0 } as CostIn;
    setBusy(true);
    try { setOut(await desksApi.cost(body)); } catch (err) { if (!quiet) fail(err); } finally { setBusy(false); }
  };
  // the example position is worked out on arrival, so the card opens with an answer rather than an empty form
  useEffect(() => { void run(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const days = Number(f.days) || 0;
  return (
    <Card id="mtf-cost">
      <CardHead title="What your MTF position costs" info="Enter your own position. Interest is worked out daily on the funded amount, as most brokers charge it. Check your broker's contract note for the exact figures." />
      <FormGrid onSubmit={run} label="Your MTF position">
        <Field label="Buy price" unit="₹" inputMode="decimal" placeholder="1000" value={f.buy} onChange={set("buy")} info="The price you pay for each share." />
        <Field label="Shares" inputMode="numeric" placeholder="100" value={f.qty} onChange={set("qty")} />
        <Field label="Your margin" unit="%" inputMode="decimal" value={f.margin_pct} onChange={set("margin_pct")} info="The part of the buy value you pay yourself. The broker funds the rest." />
        <Field label="Interest" unit="% / yr" inputMode="decimal" value={f.rate_pct} onChange={set("rate_pct")} info="The broker's yearly interest rate on the funded amount, charged daily." />
        <Field label="Days held" inputMode="numeric" value={f.days} onChange={set("days")} info="How many days the funding stays open." />
        <Field label="Charges" optional unit="₹" inputMode="decimal" placeholder="0" value={f.charges} onChange={set("charges")} info="Pledge charges, brokerage and anything else, all told for the whole holding period." />
        <Field label="Price now" optional unit="₹" inputMode="decimal" value={f.price} onChange={set("price")} info="Add today's price to see the position's profit or loss after interest and charges, and the margin left." />
        <Field label="Margin to keep" optional unit="%" inputMode="decimal" value={f.maint_pct} onChange={set("maint_pct")} info="The margin your broker asks you to keep, as a percent of the position's value. Add it to see the price where your margin falls under it." />
        <FormActions>
          <button className="btn" disabled={busy}>{busy ? "Working it out…" : "Work it out"}</button>
          <span className="k-small k-muted">Arithmetic on the numbers you enter, not advice.</span>
        </FormActions>
      </FormGrid>
      {out && (
        <ResultBlock testId="mtf-cost-out" label={`Holding for ${days} day${days === 1 ? "" : "s"} costs`} big={inr(out.costs, 2)}
          note={`${out.cost_pct_own != null ? `${pctPlain(out.cost_pct_own, 2)} of your own money · ` : ""}${inr(out.interest_day, 2)} a day in interest`}
          split={{ aLabel: "You pay", aValue: inr(out.own), aPct: out.value ? (out.own / out.value) * 100 : 0, bLabel: "Broker funds", bValue: inr(out.funded) }}
          rows={[
            { label: "Interest", value: inr(out.interest, 2) },
            { label: "Charges", value: inr(out.costs - out.interest, 2) },
            { label: "To break even, the price needs to reach", value: <>{inr(out.breakeven, 2)} <span className="k-muted">({pct(out.breakeven_pct, 2)})</span></>, highlight: true },
            ...(out.breach_price != null ? [{ label: "Price where the margin falls under your broker's %",
              value: <>{inr(out.breach_price, 2)} <span className="k-muted">({(out.breach_fall_pct ?? 0) > 0 ? `${pctPlain(out.breach_fall_pct, 2)} under ${inr(out.breach_from, 2)}` : `already at or under it at ${inr(out.breach_from, 2)}`})</span></> }] : []),
            ...(out.pnl != null ? [
              { label: `At ${inr(out.price, 2)}, the position is ${out.pnl >= 0 ? "up" : "down"}`, value: <>{inr(Math.abs(out.pnl), 2)} <span className="k-muted">({pct(out.pnl_pct_own, 1)} of your part)</span></> },
              { label: "Margin left at that price", value: pctPlain(out.margin_now_pct, 1) }] : []),
          ]} />
      )}
    </Card>
  );
}

export function MarginFundingPage() {
  const [params, setParams] = useSearchParams();
  const pick = (params.get("s") ?? "").toUpperCase();
  const [p, setP] = useState<MtfPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    setError(null);
    desksApi.mtf().then(setP).catch((e) => setError(e instanceof ApiError ? e.message : "The margin funding numbers couldn't be read."));
  }, []);
  useEffect(load, [load]);
  const open = (s: string | null) => { const x = new URLSearchParams(params); if (s) x.set("s", s); else x.delete("s"); setParams(x); };
  const reason = p && p.status.reason && p.status.status !== "ok" ? p.status.reason : null;
  return (
    <div className="k-page">
      <PageHeader eyebrow="Invest · Research" title="Margin funding"
        lede="How much of the market is bought with money brokers lend under the margin trading facility (MTF), and what your own position costs."
        asOf={p?.status.as_of} info={p ? <>{p.note} Source: {p.source}.</> : undefined} infoLabel="Where the numbers come from" />
      {error ? <ErrorState title="The margin funding numbers couldn't be read" action={{ label: "Try again", onClick: load }}>{error}</ErrorState>
        : !p ? <Card><Skeleton label="Reading the margin trading disclosure" /></Card> : (
        <>
          {reason && <p className="k-small k-muted" data-testid="mtf-status">{reason}</p>}
          <Market p={p} />
          <Card id="mtf-lookup">
            <CardHead title="Look up a stock" info="Any company listed in India. Shows how much of it the exchange's disclosure lists as margin funded, and its history on paid plans." />
            <Field label="Stock">{(id) => <StockPicker id={id} value={pick} onPick={(s) => open(s)} />}</Field>
          </Card>
          {pick && <OneStock key={pick} symbol={pick} onClose={() => open(null)} />}
          {!p.rows.length ? (
            <Card compact>
              <CardHead title="Your holdings and watchlist" />
              <p className="k-small k-muted">Add Indian stocks to <Link className="link" to="/holdings">My Holdings</Link> or your <Link className="link" to="/research/watchlist">watchlist</Link>, or look one up above.</p>
            </Card>
          ) : (
            <Card>
              <CardHead title="Your holdings and watchlist" />
              <DataTable label="Margin funding for your stocks" rows={p.rows} rowKey={(r) => r.symbol} rowAttrs={(r) => ({ "data-stock": r.symbol })}
                rowNote={(r) => (r.funded ? undefined : "No margin funding in the newest disclosure")}
                columns={[
                  { key: "stock", header: "Stock", rowHeader: true, cell: (r) => (
                    <>
                      <a className="link" href={`?s=${r.symbol}`} onClick={(e) => { e.preventDefault(); open(r.symbol); window.scrollTo({ top: 0 }); }}><b>{r.symbol}</b></a>
                      <div className="k-small k-muted">{r.held ? "You hold it" : "Watchlist"}</div>
                    </>) },
                  { key: "funded", header: "Funded", numeric: true, cell: (r) => cr(r.crore) },
                  { key: "pct", header: "Of shares issued", info: p.about.pct_shares, numeric: true, cell: (r) => pctPlain(r.pct_shares, 2) },
                  { key: "day", header: "Day", numeric: true, cell: (r) => chg(r.day) },
                  { key: "d30", header: "30 days", numeric: true, cell: (r) => chg(r.d30) },
                ]} />
              {!p.full && <p className="k-small k-muted">A year of each stock's funding and alerts on a funded level are on the <Link className="link" to="/plans">{p.plan_needed} plan</Link>.</p>}
            </Card>
          )}
        </>
      )}
      <Calculator />
    </div>
  );
}

export default MarginFundingPage;
