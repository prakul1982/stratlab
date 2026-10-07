import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { dateOnly, inr, money, pctPlain, signed } from "../../lib/format";
import type { Instrument, Market } from "../../lib/types";
import { InstrumentSearch } from "../../components/InstrumentSearch";
import { LineChart } from "../../components/Charts";
import { Info } from "../../components/ui";
import { sipParams } from "../../lib/sip";
import { Card, CardHead, ChartFrame, DataTable, Disclosure, Field, FieldGroup, FormActions, FormGrid, PageHeader, PlanNote, Select, Seg, Stat, StatRow, type Column } from "../../components/kit";

/* /money/sip-test: test a stock or ETF SIP before setting one up: a fixed amount (or number of shares) every day, week or
 * month into one Indian stock or ETF or a split across up to 10, with a yearly step-up and an optional dip rule, on past
 * closes with real charges. The same money as a lump sum beside it, and (Basic) the same SIP from every start month.
 * History of the user's own rule: never a "best" setting. Built from the kit (components/kit). */

type Leg = { symbol: string; weight: number; units: number; buys: number; spent: number; avg_price: number | null; last: number | null; value: number; cash_waiting: number };
type Run = {
  start: string; end: string; instalments: number; invested: number; value: number; gain: number; gain_pct: number; xirr: number | null;
  deepest_fall_pct: number; underwater_days: number; underwater_from: string | null; underwater_to: string | null; charges: number; stamp: number;
  cash_waiting: number; legs?: Leg[]; series?: { d: string; invested: number; value: number }[];
};
type Lump = { invested: number; value: number; gain: number; xirr: number | null; deepest_fall_pct: number; charges: number; series: { d: string; value: number }[] };
type SpreadRun = { start: string; xirr: number; deepest_fall_pct: number; plain_xirr?: number | null };
type Spread = { years: number; count: number; every_months: number; worst: SpreadRun; best: SpreadRun; median: number; below_zero: number; runs: SpreadRun[];
  dip?: { compared: number; beat: number; median_diff_pp: number | null; worst_diff_pp: number | null; best_diff_pp: number | null } };
type Reply = {
  result: Run; lump_sum: Lump | null; plain: Run | null; full: boolean; plan: string; legs: { symbol: string; name: string; inst_id: string; weight: number }[];
  history: { from: string; to: string }; window: { from: string; to: string; years: number }; words: string; spread: Spread | null;
  assumptions: string[]; disclaimer: string;
};
type Pick = { id: string; symbol: string; name: string; weight: number };
type Rule = "plain" | "only_dips" | "extra_on_dips";
type Compare = { key: string; name: string; invested: number; value: number; xirr: number | null; fall: number; charges: number };

const INDIA = { id: "IN", name: "India" } as Market;
const rate = (v: number | null | undefined) => (v == null ? "–" : pctPlain(v * 100, 1));
const signedPts = (v: number | null | undefined) => (v == null ? "–" : `${signed(v, 1)} pts`);
const month = (m: string) => new Date(`${m.slice(0, 7)}-01T00:00:00`).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
const span = (days: number) => (days >= 365 ? `${(days / 365).toFixed(1)} years` : days >= 60 ? `${Math.round(days / 30)} months` : `${days} days`);
const FREQ = [{ value: "monthly", label: "Every month" }, { value: "weekly", label: "Every week" }, { value: "daily", label: "Every trading day" }];
const LOOKBACK = ["20", "60", "125", "252"].map((v) => ({ value: v, label: `${v} trading days` }));
const YEARS = Array.from({ length: 10 }, (_, i) => ({ value: i + 1, label: String(i + 1) }));

export function SipTestPage() {
  const { me, fail } = useApp();
  const [params] = useSearchParams();
  const [picks, setPicks] = useState<Pick[]>([]);
  const [mode, setMode] = useState<"amount" | "qty">("amount");
  const [amount, setAmount] = useState(() => sipParams(params).amount ?? "10000");
  const [qty, setQty] = useState("1");
  const [freq, setFreq] = useState<"daily" | "weekly" | "monthly">(() => sipParams(params).freq ?? "monthly");
  const [dom, setDom] = useState("1");
  const [weekday, setWeekday] = useState("0");
  const [stepUp, setStepUp] = useState("0");
  const [years, setYears] = useState(() => sipParams(params).years ?? "5");
  const [brokerage, setBrokerage] = useState("0");
  const [rule, setRule] = useState<Rule>("plain");
  const [dip, setDip] = useState("10");
  const [lookback, setLookback] = useState("252");
  const [extra, setExtra] = useState("50");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [res, setRes] = useState<Reply | null>(null);
  const [copied, setCopied] = useState(false);
  const canDip = me?.plan_info?.features?.sip_luck ?? true;

  // opened from a company or ETF page: that one, ready to test
  const wanted = (params.get("symbol") ?? "").toUpperCase();
  useEffect(() => {
    if (!wanted) return;
    api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(wanted)}&market=IN`).then((r) => {
      const hit = r.find((i) => i.symbol === wanted && (i.type === "EQ" || i.type === "ETF")) ?? null;
      if (hit) setPicks((p) => (p.length ? p : [{ id: hit.id, symbol: hit.symbol, name: hit.name ?? "", weight: 100 }]));
    }).catch(() => undefined);
  }, [wanted]);

  const add = (i: Instrument) => {
    if (i.type !== "EQ" && i.type !== "ETF") { setProblem(`${i.symbol} isn't a stock or ETF. A SIP test takes shares and ETFs only.`); return; }
    setProblem(null);
    setPicks((p) => {
      if (p.some((x) => x.id === i.id) || p.length >= 10) return p;
      const next = [...p, { id: i.id, symbol: i.symbol, name: i.name ?? "", weight: 0 }];
      const even = Math.floor(100 / next.length);
      return next.map((x, k) => ({ ...x, weight: k === 0 ? 100 - even * (next.length - 1) : even }));
    });
  };
  const total = picks.reduce((s, p) => s + (Number(p.weight) || 0), 0);

  const run = async () => {
    setBusy(true); setProblem(null); setCopied(false);
    try {
      const body = {
        legs: picks.map((p) => ({ inst_id: p.id, weight: picks.length > 1 ? Number(p.weight) : 100 })), mode, amount: Number(amount), qty: Number(qty), freq,
        dom: Number(dom), weekday: Number(weekday), step_up: Number(stepUp) || 0, years: Number(years), brokerage: Number(brokerage) || 0,
        rule, dip: Number(dip), lookback: Number(lookback), extra: Number(extra),
      };
      setRes(await api<Reply>("/invest/sip-test", { method: "POST", body }));
    } catch (e) {
      const msg = (e as { message?: string })?.message;
      if (msg) setProblem(msg); else fail(e);
    } finally { setBusy(false); }
  };

  const r = res?.result;
  const chart = useMemo(() => {
    if (!r?.series) return null;
    return { labels: r.series.map((p) => dateOnly(p.d)), times: r.series.map((p) => p.d), invested: r.series.map((p) => p.invested), value: r.series.map((p) => p.value), rows: r.series.map((p, i) => ({ ...p, i })) };
  }, [r]);
  const ready = picks.length > 0 && (picks.length === 1 || Math.abs(total - 100) < 0.5) && (mode === "amount" ? Number(amount) > 0 : Number(qty) >= 1);

  const sideBySide: Compare[] = [];
  if (res && r) {
    sideBySide.push({ key: "this", name: "This SIP", invested: r.invested, value: r.value, xirr: r.xirr, fall: r.deepest_fall_pct, charges: r.charges });
    if (res.plain) sideBySide.push({ key: "plain", name: "The same SIP, no dip rule", invested: res.plain.invested, value: res.plain.value, xirr: res.plain.xirr, fall: res.plain.deepest_fall_pct, charges: res.plain.charges });
    if (res.lump_sum) sideBySide.push({ key: "lump", name: `All of it on ${dateOnly(r.start)}`, invested: res.lump_sum.invested, value: res.lump_sum.value, xirr: res.lump_sum.xirr, fall: res.lump_sum.deepest_fall_pct, charges: res.lump_sum.charges });
  }
  const sideCols: Column<Compare>[] = [
    { key: "name", header: "", rowHeader: true, cell: (x) => x.name },
    { key: "in", header: "Put in", numeric: true, cell: (x) => inr(x.invested) },
    { key: "val", header: "Value", numeric: true, cell: (x) => inr(x.value) },
    { key: "xirr", header: "XIRR", numeric: true, cell: (x) => rate(x.xirr) },
    { key: "fall", header: "Deepest fall", numeric: true, cell: (x) => pctPlain(x.fall, 1) },
    { key: "ch", header: "Charges", numeric: true, cell: (x) => inr(x.charges) },
  ];
  const legCols: Column<Leg>[] = [
    { key: "sym", header: "Stock or ETF", rowHeader: true, cell: (l) => <><b>{l.symbol}</b>{r?.legs && r.legs.length > 1 && <span className="k-sub-line">{l.weight}% of each instalment</span>}</> },
    { key: "units", header: "Shares", numeric: true, cell: (l) => l.units.toLocaleString("en-IN") },
    { key: "buys", header: "Purchases", numeric: true, cell: (l) => l.buys },
    { key: "avg", header: "Average cost", numeric: true, cell: (l) => money(l.avg_price, "INR", 2) },
    { key: "last", header: "Last close", numeric: true, cell: (l) => money(l.last, "INR", 2) },
    { key: "val", header: "Value", numeric: true, cell: (l) => inr(l.value) },
  ];

  return (
    <div className="k-page sip-test">
      <PageHeader eyebrow="Money · Plan" title="Test a SIP"
        lede="What a stock or ETF SIP of your own would have done on past prices, with the charges on every purchase, beside the same money put in on day one."
        info="History of the rule you set, not a forecast or a suggestion." infoLabel="About the SIP test" />

      <Card label="Your SIP">
        <CardHead title="Your SIP" />
        <FieldGroup label="Stocks or ETFs" info="Up to 10. With more than one, the shares split evenly at first and must add up to 100%." wide><InstrumentSearch market={INDIA} compact onPick={add} /></FieldGroup>
        {picks.length > 0 && (
          <ul className="k-picks" aria-label="In this SIP">
            {picks.map((p) => (
              <li key={p.id} className="k-pick">
                <span className="k-pick-name"><b>{p.symbol}</b>{p.name !== p.symbol && p.name && <span className="k-sub-line">{p.name}</span>}</span>
                {picks.length > 1 && (
                  <div className="k-pick-share">
                    <Field label="Share" unit="%" type="number" min={1} max={100} value={p.weight} aria-label={`Share for ${p.symbol} (%)`}
                      onChange={(e) => setPicks((all) => all.map((x) => (x.id === p.id ? { ...x, weight: Number(e.target.value) } : x)))} />
                  </div>
                )}
                <button type="button" className="btn quiet sm" onClick={() => setPicks((all) => all.filter((x) => x.id !== p.id))} aria-label={`Remove ${p.symbol}`}>Remove</button>
              </li>
            ))}
          </ul>
        )}
        {picks.length > 1 && Math.abs(total - 100) >= 0.5 && <p className="k-small k-down" role="status">The shares add up to {total}%; make them 100%.</p>}

        <FormGrid label="SIP settings" onSubmit={(e) => { e.preventDefault(); if (ready && !busy) void run(); }}>
          <FieldGroup label="Each time" wide>
            <Seg label="Each time" options={[{ value: "amount", label: "An amount" }, { value: "qty", label: "Shares" }]} value={mode} onChange={(v) => { setMode(v as typeof mode); if (v === "qty") setRule("plain"); }} />
          </FieldGroup>
          {mode === "amount"
            ? <Field label="Amount each time" unit="₹" type="number" min={1} value={amount} onChange={(e) => setAmount(e.target.value)} />
            : <Field label="Shares each time" type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />}
          <Field label="How often">{(id) => <Select id={id} value={freq} onChange={(v) => setFreq(v as typeof freq)} options={FREQ} />}</Field>
          {freq === "monthly" && <Field label="Day of the month" type="number" min={1} max={28} value={dom} onChange={(e) => setDom(e.target.value)} />}
          {freq === "weekly" && <Field label="Day of the week">{(id) => <Select id={id} value={weekday} onChange={setWeekday} options={WEEKDAYS.map((d, i) => ({ value: String(i), label: d }))} />}</Field>}
          <Field label="Step-up a year" unit="%" type="number" min={0} max={50} value={stepUp} onChange={(e) => setStepUp(e.target.value)} info="Raises the amount by this much each year." />
          <Field label="Years">{(id) => <Select id={id} value={years} onChange={setYears} options={YEARS} />}</Field>
          <Field label="Brokerage an order" unit="₹" type="number" min={0} value={brokerage} onChange={(e) => setBrokerage(e.target.value)} />
          <Field label="Dip rule">{(id) => (
            <Select id={id} value={rule} onChange={(v) => setRule(v as Rule)} disabled={mode === "qty"} options={[
              { value: "plain", label: "None, on schedule" },
              { value: "only_dips", label: `Only on dips${canDip ? "" : " (Basic)"}`, disabled: !canDip },
              { value: "extra_on_dips", label: `Extra on dips${canDip ? "" : " (Basic)"}`, disabled: !canDip }]} />
          )}</Field>
          {rule !== "plain" && <>
            <Field label="Fall from the recent high" unit="%" type="number" min={1} max={60} value={dip} onChange={(e) => setDip(e.target.value)} />
            <Field label="Recent high over">{(id) => <Select id={id} value={lookback} onChange={setLookback} options={LOOKBACK} />}</Field>
            {rule === "extra_on_dips" && <Field label="Extra on a dip" unit="%" type="number" min={1} max={500} value={extra} onChange={(e) => setExtra(e.target.value)} />}
          </>}
          <FormActions>
            <button type="submit" className="btn" disabled={!ready || busy}>{busy ? "Running…" : "Run the test"}</button>
            {problem && <span className="k-small k-down" role="alert">{problem}</span>}
          </FormActions>
        </FormGrid>
        {!canDip && <PlanNote>Dip rules, and the same SIP run from every start month, are on the Basic plan.</PlanNote>}
      </Card>

      {res && r && (
        <section className="k-page" aria-label="What the SIP did">
          <Card>
            <CardHead title="What this SIP did" />
            <p className="k-small k-muted">{dateOnly(r.start)} to {dateOnly(r.end)}: {r.instalments} instalment{r.instalments === 1 ? "" : "s"}{res.legs.length > 1 ? ` into ${res.legs.map((l) => `${l.weight}% ${l.symbol}`).join(", ")}` : ` into ${res.legs[0].symbol}`}.</p>
            <StatRow>
              <Stat label="Put in" value={inr(r.invested)} />
              <Stat label="Value at the end" value={inr(r.value)} note={`${r.gain_pct > 0 ? "+" : ""}${r.gain_pct.toFixed(1)}% on the money put in`} />
              <Stat label="XIRR" value={rate(r.xirr)} />
              <Stat label={<>Deepest fall <Info label="What the deepest fall is">The largest drop of the pot from a high, leaving out the instalments themselves.</Info></>} value={pctPlain(r.deepest_fall_pct, 1)} />
              <Stat label="Longest below the money put in" value={r.underwater_days ? span(r.underwater_days) : "Never"} note={r.underwater_from ? `${dateOnly(r.underwater_from)} to ${dateOnly(r.underwater_to)}` : undefined} />
              <Stat label="Charges" value={inr(r.charges)} note={`${inr(r.stamp)} of it stamp duty`} />
            </StatRow>
            {r.cash_waiting > 1 && <p className="k-small">{inr(r.cash_waiting)} was still waiting as cash at the end{res.plain ? ", for a dip that hadn't come" : ", short of a whole share"}; it is counted in the value.</p>}
          </Card>

          {chart && (
            <ChartFrame title="The value and the money put in"
              table={{ label: "The SIP's value and the money put in, by date", rows: [...chart.rows].reverse(), rowKey: (x) => String(x.i),
                columns: [{ key: "d", header: "Day", rowHeader: true, cell: (x) => dateOnly(x.d) }, { key: "in", header: "Put in", numeric: true, cell: (x) => inr(x.invested) }, { key: "v", header: "Value", numeric: true, cell: (x) => inr(x.value) }] }}>
              <LineChart lines={[{ values: chart.value, color: "var(--series-1)", width: 2, label: "Value" }, { values: chart.invested, color: "var(--series-2)", width: 2, dash: "4 3", label: "Put in" }]}
                labels={chart.labels} times={chart.times} format={(v) => inr(v)} height={220} legend ranges={false} table={false} ariaLabel="The SIP's value and the money put in, over time" />
            </ChartFrame>
          )}

          <Card>
            <CardHead title="Side by side" />
            <DataTable label="Side by side" columns={sideCols} rows={sideBySide} rowKey={(x) => x.key} />
            {r.legs && r.legs.length > 0 && <DataTable label="Each stock or ETF" columns={legCols} rows={r.legs} rowKey={(l) => l.symbol} />}
          </Card>

          {res.spread && (
            <ChartFrame label="Every start month" title="The same SIP from every start month"
              info="How much the answer depends on when you began."
              stats={<>
                <p className="k-small k-muted">{res.spread.count} runs of {res.spread.years} year{res.spread.years === 1 ? "" : "s"} each, starting {res.spread.every_months > 1 ? `every ${res.spread.every_months} months` : "every month"} from {month(res.spread.runs[0].start)}.</p>
                <StatRow>
                  <Stat label="Lowest XIRR" value={rate(res.spread.worst.xirr)} note={`from ${month(res.spread.worst.start)}`} />
                  <Stat label="Middle XIRR" value={rate(res.spread.median)} />
                  <Stat label="Highest XIRR" value={rate(res.spread.best.xirr)} note={`from ${month(res.spread.best.start)}`} />
                  <Stat label="Runs below zero" value={`${res.spread.below_zero} of ${res.spread.count}`} />
                </StatRow>
              </>}
              table={{ label: "XIRR by start month", rows: res.spread.runs.map((x, i) => ({ ...x, i })), rowKey: (x) => String(x.i),
                columns: [{ key: "s", header: "Started", rowHeader: true, cell: (x) => month(x.start) }, { key: "x", header: "XIRR", numeric: true, cell: (x) => rate(x.xirr) },
                  ...(res.spread.dip ? [{ key: "p", header: "No dip rule", numeric: true, cell: (x: SpreadRun) => rate(x.plain_xirr) }] : [])] }}
              footer={res.spread.dip && (
                <p className="k-small">The dip rule's XIRR was above the plain SIP's in {res.spread.dip.beat} of {res.spread.dip.compared} start months;
                  the middle difference was {signedPts(res.spread.dip.median_diff_pp)} (from {signedPts(res.spread.dip.worst_diff_pp)} to {signedPts(res.spread.dip.best_diff_pp)}).</p>
              )}>
              <LineChart lines={[{ values: res.spread.runs.map((x) => x.xirr * 100), color: "var(--series-1)", width: 2, label: "XIRR" },
                ...(res.spread.dip ? [{ values: res.spread.runs.map((x) => (x.plain_xirr == null ? null : x.plain_xirr * 100)), color: "var(--series-2)", width: 2, dash: "4 3", label: "No dip rule" }] : [])]}
                labels={res.spread.runs.map((x) => `Started ${month(x.start)}`)} times={res.spread.runs.map((x) => `${x.start}-01`)} format={(v) => `${v.toFixed(1)}%`} baseline={0}
                height={200} legend={!!res.spread.dip} ranges={false} table={false} ariaLabel="XIRR by start month" />
            </ChartFrame>
          )}
          {!res.full && <PlanNote>The same SIP from every start month, and dip rules with their luck check, are on the {res.plan} plan.</PlanNote>}

          <Card>
            <CardHead title="Your rule in plain words" actions={<>
              {copied && <span className="k-note" role="status">Copied.</span>}
              <button type="button" className="btn quiet sm" onClick={() => { navigator.clipboard?.writeText(res.words).then(() => setCopied(true)).catch(() => setCopied(false)); }}>Copy the rule</button>
            </>} />
            <p className="k-small" data-testid="sip-words">{res.words}</p>
            <p className="k-note">Prices from {dateOnly(res.history.from)} to {dateOnly(res.history.to)}. {res.disclaimer}</p>
            <Disclosure summary="How this is worked out">
              <ul className="k-list muted">{res.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </Disclosure>
          </Card>
        </section>
      )}
    </div>
  );
}
