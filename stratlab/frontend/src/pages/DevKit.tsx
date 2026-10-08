import { useMemo, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { axisInr, CRORE, inr, inrCompact, pct, pctPlain, signed, signedInrCompact } from "../lib/format";
import { LineChart } from "../components/Charts";
import { Loading } from "../components/ui";
import {
  Badge, Breadcrumb, Card, CardHead, ChartFrame, ChipBar, DataTable, Delta, EmptyState, ErrorState, Field, FormActions, FormGrid, HealthGrid, HealthTile, LinkCard, Pager, StatusList, StatusRow, PageHeader, ResultBlock, Seg, Signed, Skeleton, Spark, Stat, StatRow, StockPicker, Suggest,
  Range, TilePicker, TimeInput, type TileGroup,
  Coachmark,
} from "../components/kit";

/* /dev/kit: every kit component in its states, for checking a change by eye in both themes. Only in dev builds and for
 * admins. The figures on this page are examples. */

const ICONS = {
  cash: <><path d="M3 7h18v10H3z" /><circle cx="12" cy="12" r="2.5" /></>,
  fd: <path d="M4 20V9l8-5 8 5v11M9 20v-6h6v6" />,
  ret: <path d="M12 3v18M5 10l7-7 7 7" />,
  gold: <path d="M4 18h16l-3-6H7zM8 12l2-5h4l2 5" />,
  loan: <><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M3 10h18" /></>,
};
const TILES: TileGroup[] = [
  { title: "Cash and deposits", tiles: [{ value: "cash", title: "Savings and cash", sub: "Bank balances", icon: ICONS.cash }, { value: "fd", title: "Fixed deposit", sub: "Works out today's value", icon: ICONS.fd }] },
  { title: "Retirement", tiles: [{ value: "epf", title: "EPF", sub: "From your passbook", icon: ICONS.ret }, { value: "ppf", title: "PPF", sub: "7.1% a year", icon: ICONS.ret }, { value: "nps", title: "NPS", sub: "Tier I and II", icon: ICONS.ret }] },
  { title: "Gold, property and other", tiles: [{ value: "gold", title: "Gold", sub: "Grams or value", icon: ICONS.gold }, { value: "loan", title: "Loan or card", sub: "Balance left", icon: ICONS.loan }] },
];
const HOLDERS = ["Life Insurance Corporation of India", "SBI Mutual Fund", "Vanguard Total International", "Nippon Life India"];
const DAYS = Array.from({ length: 30 }, (_, i) => new Date(Date.UTC(2026, 8, 1 + i)).toISOString().slice(0, 10));
const BOOK = DAYS.map((_, i) => 142.5e3 + i * 290 + Math.sin(i / 2.2) * 600);   // in crore: 1.42 to 1.51 lakh crore
const STOCKS = [{ s: "RELIANCE", n: "Reliance Industries", f: 2418, c: 42, p: 0.21 }, { s: "HDFCBANK", n: "HDFC Bank", f: 1906, c: -18, p: 0.17 }, { s: "TATAMOTORS", n: "Tata Motors", f: 1377, c: 61, p: 0.48 }];

function Spec({ name, rule, children }: { name: string; rule: string; children: ReactNode }) {
  return (
    <section className="k-page" aria-label={name}>
      <div><h2 className="k-card-title">{name}</h2><p className="k-small k-muted">{rule}</p></div>
      {children}
    </section>
  );
}
const Row = ({ children }: { children: ReactNode }) => <div className="k-card-actions" style={{ gap: "var(--s3)" }}>{children}</div>;

function Body() {
  const { theme, setTheme } = useApp();
  const [range, setRange] = useState("3m");
  const [freq, setFreq] = useState("daily");
  const [tf, setTf] = useState("1 day");
  const [tile, setTile] = useState<string | null>("fd");
  const [clock, setClock] = useState("09:30");
  const [trail, setTrail] = useState(4);
  const [pg, setPg] = useState(2);
  const [sym, setSym] = useState("");
  const [coach, setCoach] = useState(false);
  const series = useMemo(() => BOOK, []);
  return (
    <div className="k-page" style={{ gap: "var(--s6)" }}>
      <PageHeader eyebrow="Developer · Design kit" title="One look, everywhere" lede="Every kit component in its states. Figures here are examples; if a page needs something that is not on this page, add it here first."
        asOf="2026-09-30" info="A page's data date goes here, with where the numbers come from." actions={<Seg label="Theme" options={[{ value: "light", label: "Light" }, { value: "dark", label: "Dark" }, { value: "system", label: "System" }]} value={theme} onChange={(v) => setTheme(v as "light" | "dark" | "system")} />} />

      <Spec name="Page header" rule="Where you are, the title, one line on what it is for, and when the data is from.">
        <Card><PageHeader eyebrow="Invest · Market view" title="Margin funding" lede="How much of the market is bought with money brokers lend, and what your own position costs." asOf="2026-09-30" info="Source note." /></Card>
        <Card><PageHeader eyebrow="Money · Tax" title="Tax report" /></Card>
      </Spec>

      <Spec name="Card and card header" rule="Title and (i) on the left, the card's controls in the same row on the right. Compact when it has little to say.">
        <Card><CardHead title="The market's MTF book" info="What this card shows." actions={<><Seg label="Range" options={[{ value: "1m", label: "1M" }, { value: "3m", label: "3M" }]} value={range} onChange={setRange} /><button className="btn quiet sm">Table</button></>} /><p className="k-small k-muted">Body of the card.</p></Card>
        <Card compact><CardHead title="Your holdings and watchlist" /><p className="k-small k-muted">Add Indian stocks to My Holdings or your watchlist, or look one up above.</p></Card>
      </Spec>

      <Spec name="Signed" rule="Any change, gain or loss, return or net figure with a + / − sign is green above zero and red below it; zero stays plain. The sign or ▲/▼ is always printed too. Levels, prices, totals, counts and sizes stay plain.">
        <Card compact>
          <DataTable label="Signed figures" rowKey={(r) => r.name} rows={[
            { name: "Net futures", level: 3_55_766, chg: 5721 }, { name: "Net calls", level: 1_52_252, chg: -2579 }, { name: "Net puts", level: 0, chg: 0 }]}
            columns={[{ key: "n", header: "Participant", rowHeader: true, cell: (r) => r.name },
              { key: "l", header: "Open interest", numeric: true, cell: (r) => <>{r.level.toLocaleString("en-IN")}<span className="k-sub-line"><Signed value={r.chg} fmt={signed} /></span></> },
              { key: "c", header: "Change", numeric: true, cell: (r) => <Signed value={r.chg} fmt={signed} /> }]} />
          <p className="k-small">Today <Signed value={1.24}>{pct(1.24, 2)}</Signed>, last month <Signed value={-3.6}>{pct(-3.6)}</Signed>, unchanged <Signed value={0}>{pct(0)}</Signed>.</p>
        </Card>
      </Spec>

      <Spec name="Stat, StatRow and Delta" rule="Big number in the sans font. Delta shows direction in green or red with the sign printed; use neutral colour where a rise is not good news (the margin-funded book, volatility, a currency or gold).">
        <Card>
          <StatRow>
            <Stat label="Funded on 30 Sep" value="₹1.51 lakh cr" note="2,192 stocks" />
            <Stat label="That day" value="+₹296 cr" tone="up" delta={<Delta value={296}>₹296 cr</Delta>} note="that day" />
            <Stat label="Over 30 days" value="−₹5,209 cr" tone="down" delta={<Delta value={-3.6}>3.6%</Delta>} note="since 31 Aug" />
            <Stat label="Neutral change" value="+₹42 cr" delta={<Delta value={42} tone="neutral">0.1%</Delta>} note="direction only" />
            <Stat label="Not available" value="–" note="Needs 30 days of data" />
          </StatRow>
        </Card>
      </Spec>

      <Spec name="Badge" rule="Always a word, never colour alone. Live pulses unless the device asks for less motion.">
        <Row><Badge tone="live">Live</Badge><Badge tone="ok">Connected</Badge><Badge tone="warn">Needs attention</Badge><Badge tone="plain">Market closed</Badge><Badge tone="plain" dot={false}>No dot</Badge></Row>
      </Spec>

      <Spec name="Seg" rule="2 to 4 choices, as wide as its choices. A radio group: arrow keys move.">
        <Row><Seg label="Frequency" options={[{ value: "daily", label: "Daily" }, { value: "weekly", label: "Weekly" }, { value: "off", label: "Off" }]} value={freq} onChange={setFreq} />
          <Seg label="Two choices" options={[{ value: "a", label: "Table" }, { value: "b", label: "Chart" }]} value="a" onChange={() => undefined} />
          <Seg label="With one off" options={[{ value: "a", label: "1M" }, { value: "b", label: "1Y", disabled: true }]} value="a" onChange={() => undefined} /></Row>
      </Spec>

      <Spec name="LinkCard" rule="A whole card that is one link: title, one line, a small note such as when it was last updated.">
        <div className="k-linkcards"><LinkCard to="/holdings" title="My Holdings" note="Updated 2 days ago">Your shares, from a file or typed in.</LinkCard><LinkCard to="/money/mutual-funds" title="Mutual funds">Your statement.</LinkCard></div>
      </Spec>

      <Spec name="ChipBar" rule="Many choices in one scrolling row; + Custom adds a number and unit and remembers it on this device.">
        <Card>
          <ChipBar label="Timeframe" value={tf} onChange={setTf} options={["1 min", "3 min", "5 min", "10 min", "15 min", "30 min", "1 hour", "2 hours", "4 hours", "1 day", "1 week", "1 month"].map((v) => ({ value: v, label: v }))}
            custom={{ storageKey: "stratlab.kit.timeframes", units: [{ value: "min", label: "minute", plural: "minutes" }, { value: "hour", label: "hour", plural: "hours" }, { value: "day", label: "day", plural: "days" }, { value: "week", label: "week", plural: "weeks" }], defaultUnit: "min" }} />
          <ChipBar label="Without custom" value="a" onChange={() => undefined} options={[{ value: "a", label: "Nifty 50" }, { value: "b", label: "Bank Nifty" }, { value: "c", label: "Sensex" }]} />
        </Card>
      </Spec>

      <Spec name="Pager" rule="Previous and next under a long list that comes a page at a time; it says which page and how many rows. Not shown when one page holds everything.">
        <Card><Pager page={pg} pages={5} total={112} noun="filings" onPage={setPg} /><Pager page={1} pages={1} total={9} noun="filings" onPage={() => undefined} /></Card>
      </Spec>

      <Spec name="FormGrid, Field and FormActions" rule="One-line labels, the detail behind (i), units inside the box, optional says so, the main button on its own row.">
        <Card>
          <FormGrid label="Example form" onSubmit={(e) => e.preventDefault()}>
            <Field label="Buy price" unit="₹" defaultValue="1000" inputMode="decimal" />
            <Field label="Shares" defaultValue="100" inputMode="numeric" />
            <Field label="Your margin" unit="%" defaultValue="25" info="The part of the buy value you pay yourself. The broker funds the rest." />
            <Field label="Interest" unit="% / yr" defaultValue="15" info="The broker's yearly rate, charged daily." />
            <Field label="Charges" optional unit="₹" placeholder="0" />
            <Field label="A label that is much too long to fit on one line of its box" placeholder="Truncates, never wraps" />
            <Field label="Frequency">{(id) => <select id={id} className="k-input" defaultValue="m"><option value="m">Monthly</option><option value="q">Quarterly</option></select>}</Field>
            <Field label="Note" optional wide placeholder="Spans the row" />
            <Field label="Enter at" info="TimeInput: 24-hour, with the exchange's zone beside the box.">{(id) => <TimeInput id={id} zone="IST" value={clock} onChange={setClock} />}</Field>
            <Field label="Trail" info="Range: the kit's slider, its value in words beside it.">{(id) => <Range id={id} min={1} max={12} value={trail} onChange={setTrail} valueText={`${trail} week${trail === 1 ? "" : "s"}`} />}</Field>
            <FormActions><button className="btn">Work it out</button><span className="k-small k-muted">Arithmetic on the numbers you enter, not advice.</span></FormActions>
          </FormGrid>
          <ResultBlock label="Holding for 30 days costs" big="₹2,812" note="11.25% of your own money · ₹93.75 a day in interest"
            split={{ aLabel: "You pay", aValue: "₹25,000", aPct: 25, bLabel: "Broker funds", bValue: "₹75,000" }}
            rows={[{ label: "Interest", value: "₹2,812.50" }, { label: "Charges", value: "₹0.00" }, { label: "To break even, the price needs to reach", value: <>₹1,028.12 <span className="k-muted">(+2.81%)</span></>, highlight: true }]} />
        </Card>
      </Spec>

      <Spec name="StockPicker" rule="Every box where you type a stock. Type two letters to see suggestions (needs the API).">
        <div className="grid2">
          <Card><Field label="Stock (empty)">{(id) => <StockPicker id={id} value={sym} onPick={(s) => setSym(s)} />}</Field></Card>
          <Card><Field label="Stock (filled)">{(id) => <StockPicker id={id} value="RELIANCE" onPick={() => undefined} />}</Field></Card>
        </div>
      </Spec>

      <Spec name="Suggest" rule="A box for a name that is not a listed company (a fund, a person): suggestions after three letters, the same keys and look as StockPicker.">
        <Card><Field label="Holder">{(id) => <Suggest id={id} placeholder="Type three letters of a name" load={async (q) => HOLDERS.filter((h) => h.toLowerCase().includes(q.toLowerCase())).map((h) => ({ key: h, label: h, note: "12 companies" }))} onPick={() => undefined} />}</Field></Card>
      </Spec>

      <Spec name="TilePicker"rule="Replaces long dropdowns. One choice across the groups.">
        <Card><CardHead title="What are you adding?" /><TilePicker label="Asset type" groups={TILES} value={tile} onChange={setTile} /></Card>
      </Spec>

      <Spec name="Breadcrumb" rule="The trail at the top of every page: space, group, page. The last part opens the pages beside it and the pin switch.">
          <Card>
            <Breadcrumb trail={[{ label: "Invest", to: "/invest" }, { label: "Market view", to: "/invest/g/market-view" }]} page="Margin funding"
              siblings={[{ to: "/research/pulse", label: "Market pulse" }, { to: "/invest/breadth", label: "Market breadth" }, { to: "/invest/margin-funding", label: "Margin funding", current: true }]}
              seeAll={{ label: "All of Market view", to: "/invest/g/market-view" }} pinned={false} onTogglePin={() => undefined} />
            <Breadcrumb trail={[{ label: "Invest", to: "/invest" }, { label: "Market view", to: "/invest/g/market-view" }]} />
          </Card>
      </Spec>

      <Spec name="Spark" rule="A line of recent real values, no axes. Up and down colour it; neutral where a rise is not good news.">
        <Card>
          <StatRow>
            <Stat label="NIFTY 50" value="25,420" delta={<Delta value={0.4}>+0.40%</Delta>} />
            <Spark values={BOOK.slice(0, 20)} tone="up" label="Example, rising" area />
            <Spark values={[...BOOK.slice(0, 20)].reverse()} tone="down" label="Example, falling" />
            <Spark values={BOOK.slice(0, 20)} label="Example, neutral" />
          </StatRow>
        </Card>
      </Spec>

      <Spec name="HealthGrid and StatusList" rule="A light is green, amber or red and always carries its word. One tile per service or feed; a status list for a card's own rows.">
        <Card>
          <HealthGrid label="Example health">
            <HealthTile state="ok" label="Prices" detail="live · 4s ago" />
            <HealthTile state="ok" label="Broker login" detail="today 08:00" />
            <HealthTile state="warn" label="ETF NAV" detail="old format · Run now" to="/admin/data" />
            <HealthTile state="bad" label="Closing auction" detail="read failed 12 min ago" />
          </HealthGrid>
          <StatusList label="Example statuses">
            <StatusRow state="ok" label="Alerts to you" detail="Emailed to owner@example.com" />
            <StatusRow state="warn" label="Option chain recording" detail="Off" />
          </StatusList>
        </Card>
      </Spec>

      <Spec name="DataTable" rule="Numbers right-aligned, hover row, scrolls inside its own box, one message when empty.">
        <Card>
          <DataTable label="Example table" rows={STOCKS} rowKey={(r) => r.s} columns={[
            { key: "s", header: "Stock", rowHeader: true, cell: (r) => <><b>{r.s}</b> <span className="k-small k-muted">{r.n}</span></> },
            { key: "f", header: "Funded", numeric: true, cell: (r) => inrCompact(r.f * CRORE) },
            { key: "c", header: "Change", info: "Since the day before.", numeric: true, cell: (r) => signedInrCompact(r.c * CRORE) },
            { key: "p", header: "Of shares issued", numeric: true, cell: (r) => pctPlain(r.p, 2) }]} />
          <DataTable label="Long table, header stays in view" sticky rows={Array.from({ length: 24 }, (_, i) => ({ s: `STOCK${i + 1}`, f: 100 + i * 17 }))} rowKey={(r) => r.s}
            columns={[{ key: "s", header: "Stock", rowHeader: true, sortable: true, cell: (r) => <b>{r.s}</b> }, { key: "f", header: "Funded", numeric: true, sortable: true, cell: (r) => inrCompact(r.f * CRORE) }]}
            sort={{ key: "f", desc: true, onSort: () => undefined }} />
          <DataTable label="Empty table"rows={[] as typeof STOCKS} rowKey={(r) => r.s} empty="No stocks yet." columns={[{ key: "s", header: "Stock", cell: (r) => r.s }, { key: "f", header: "Funded", numeric: true, cell: (r) => r.f }]} />
        </Card>
      </Spec>

      <Spec name="EmptyState, ErrorState, Skeleton" rule="The same three everywhere. Each says what is going on and what to do next.">
        <div className="grid2">
          <EmptyState title="No holdings yet" action={{ label: "Connect an account", onClick: () => undefined }}>Connect your broker once and they will fill in by themselves.</EmptyState>
          <EmptyState title="Nothing here yet">No button when there is nothing to do.</EmptyState>
          <ErrorState title="The exchange has not published 1 Oct yet" action={{ label: "Try again", onClick: () => undefined }}>We check again every evening. Showing 30 Sep for now.</ErrorState>
          <Card><Skeleton label="Loading the last 30 days" /></Card>
        </div>
      </Spec>

      <Spec name="ChartFrame" rule="Title, range and Table switch in one header row. Drawn, then as a table; and while loading.">
        <ChartFrame title="The market's MTF book" info="Every stock's margin-funded amount added up." ranges={[{ value: "1m", label: "1M" }, { value: "3m", label: "3M" }, { value: "all", label: "All" }]} range={range === "1m" || range === "3m" ? range : "all"} onRange={setRange}
          stats={<StatRow><Stat label="Funded on 30 Sep" value="₹1.51 lakh cr" note="2,192 stocks" /><Stat label="That day" value="+₹296 cr" note="₹3,472 cr new · ₹3,177 cr closed" /></StatRow>}
          table={{ label: "The book by day", rows: DAYS.map((d, i) => ({ d, v: series[i] })).reverse(), rowKey: (r) => r.d, columns: [{ key: "d", header: "Day", rowHeader: true, cell: (r) => r.d }, { key: "v", header: "Funded", numeric: true, cell: (r) => `${inr(r.v, 2)} cr` }] }}>
          <LineChart lines={[{ values: series, color: "var(--pos-call)", width: 2, label: "MTF book" }]} labels={DAYS} times={DAYS} ranges={false} table={false} format={(v) => `${inr(v, 2)} cr`} axisFormat={(v) => axisInr(v * CRORE)} height={180} ariaLabel="Example book by day" />
        </ChartFrame>
        <ChartFrame title="While loading"><Skeleton label="Reading the margin trading disclosure" lines={3} /></ChartFrame>
      </Spec>

      <Spec name="Coachmark" rule="One tour step pointed at a real control, the rest dimmed. Short title, one line, Back and Next (Done on the last step). Esc closes; Tab stays inside.">
        <Card><button type="button" className="btn quiet sm" id="kit-coach-target" onClick={() => setCoach(true)}>Show a coachmark</button></Card>
        {coach && (
          <Coachmark anchor={["#kit-coach-target"]} label="Example step" onClose={() => setCoach(false)}>
            <span className="k-eyebrow">Step 1 of 1</span>
            <h2 className="tour-title">This button</h2>
            <p className="tour-body">A coachmark points at the thing it explains.</p>
            <div className="k-row tour-foot"><button type="button" className="btn sm" data-autofocus onClick={() => setCoach(false)}>Done</button></div>
          </Coachmark>
        )}
      </Spec>

      <Spec name="Numbers (lib/format.ts)" rule="Indian units everywhere. A minus is a real minus.">
        <Card><DataTable label="Number formats" rows={[
          ["inr(100000)", inr(100000)], ["inr(1849.3, 2)", inr(1849.3, 2)], ["inrCompact(925)", inrCompact(925)], ["inrCompact(3472 cr)", inrCompact(3472 * CRORE)], ["inrCompact(1.51 lakh cr)", inrCompact(1.51e5 * CRORE)],
          ["signedInrCompact(-18 cr)", signedInrCompact(-18 * CRORE)], ["axisInr(1.45 lakh cr)", axisInr(1.45e5 * CRORE)], ["pct(-1.234)", pct(-1.234)], ["pctPlain(0.213, 2)", pctPlain(0.213, 2)], ["signed(1234567)", signed(1234567)]]}
          rowKey={(r) => r[0]} columns={[{ key: "a", header: "Call", cell: (r) => <code>{r[0]}</code> }, { key: "b", header: "Shows", numeric: true, cell: (r) => r[1] }]} /></Card>
      </Spec>

      <Spec name="Colours" rule="Up and down have their own greens and reds, soft versions for pills. Orange is for warnings, never for a loss.">
        <Row>
          {["--up", "--up-soft", "--down", "--down-soft", "--blue", "--orange", "--ink", "--paper", "--card"].map((v) => (
            <span key={v} className="k-small" style={{ display: "inline-flex", gap: 8, alignItems: "center" }}><i style={{ width: 28, height: 28, borderRadius: 8, background: `var(${v})`, border: "1px solid var(--line-2)", display: "inline-block" }} />{v}</span>
          ))}
        </Row>
      </Spec>
    </div>
  );
}

export function DevKit() {
  const { me, ready } = useApp();
  if (!import.meta.env.DEV) {
    if (!ready || (me == null)) return <Loading label="Checking access" />;
    if (!me.is_admin) return <Navigate to="/" replace />;
  }
  return <Body />;
}

export default DevKit;
