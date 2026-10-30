import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useLiveRefresh } from "../lib/liveRefresh";
import { fmtDate, pct, safeHref } from "../lib/format";
import { newsWhen } from "../lib/researchFormat";
import { researchApi, type MoodBreadthRow, type NewsItem, type PulseAI, type PulseMood, type Region } from "../lib/research";
import { crore, moverRows, movedBy, pairable, riskLevel, sectorCount, signedPoints, signedPts, signedWhole, storyOf, whole } from "../lib/pulseMood";
import { Card, CardHead, DataTable, Delta, EmptyState, Skeleton, type Column } from "../components/kit";

/* The Market pulse's tables (MOOD-1). Every block that shows figures or records is a table with a header row, numbers
 * right-aligned and a ▲/▼ with a sign for a change; on a phone each row is a card (DataTable's stack). The words above them
 * come from the same payload (intel/mood.py), so a line and its table agree. Facts only: no advice, no forecast. */

const day = (iso: string | null | undefined) => (iso ? fmtDate(iso, { year: false }) : "");
const chg = (v: number | null | undefined) => (v == null ? "–" : <Delta value={v}>{pct(v, 2)}</Delta>);

/** The mood as the server read it, again each minute while the market trades; `pending` until its first read is back. */
export function usePulseMood(region: Region) {
  const [mood, setMood] = useState<PulseMood | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [again, setAgain] = useState(0);
  useEffect(() => {
    let live = true, tries = 0;
    let next: ReturnType<typeof setTimeout> | undefined;
    setMood(null); setError(null);
    const load = () => researchApi.pulseMood(region).then((d) => {
      if (!live) return;
      if (d.pending) { if (tries++ < 20) next = setTimeout(load, 3000); else setError("The market's figures are taking longer than usual."); return; }
      setMood(d);
    }).catch((e) => { if (live) setError((e as Error).message || "The market's figures couldn't be read."); });
    load();
    return () => { live = false; if (next) clearTimeout(next); };
  }, [region, again]);
  useLiveRefresh(!!mood?.is_open, () => { researchApi.pulseMood(region).then((d) => { if (!d.pending) setMood((cur) => (cur ? d : cur)); }).catch(() => undefined); });
  return { mood, error, retry: () => setAgain((n) => n + 1) };
}

/** The headline and its few lines, each from one of the tables below. */
export function MoodCard({ m, region }: { m: PulseMood; region: Region }) {
  return (
    <Card testId="pulse-mood-card">
      <CardHead title="The mood" info="One short headline and a few lines, each worked out from the tables below with one rounding, so a line and its table cannot disagree. Facts about today, not a forecast. The index levels are in the first table."
        actions={m.read_at ? <span className="k-note">Read {new Date(m.read_at).toLocaleTimeString(region === "IN" ? "en-IN" : "en-US", { hour: "2-digit", minute: "2-digit", timeZone: region === "IN" ? "Asia/Kolkata" : "America/New_York" })}</span> : undefined} />
      {m.headline ? <p className="inv-summary" data-testid="pulse-mood"><b>{m.headline}</b></p> : <p className="k-small k-muted">The tables below are the day's figures; their summary isn't available right now.</p>}
      {m.lines.length > 0 && <ul className="k-list" data-testid="pulse-mood-lines">{m.lines.map((l) => <li key={l}>{l}</li>)}</ul>}
    </Card>
  );
}

export function BreadthTable({ b }: { b: NonNullable<PulseMood["breadth"]> }) {
  const when = b.live ? "so far today" : `on ${day(b.day)}`;
  const cols: Column<MoodBreadthRow>[] = [
    { key: "m", header: "Measure", rowHeader: true, wrap: true, cell: (r) => <><b>{r.label}</b><span className="k-sub-line">{r.means}</span></> },
    { key: "now", header: b.live ? "Today" : day(b.day), numeric: true, cell: (r) => (r.now == null ? "–" : r.kind === "share" ? `${r.now.toFixed(1)}%` : whole(r.now)) },
    { key: "prev", header: day(b.prev_day) || "Day before", numeric: true, cell: (r) => (r.before == null ? "–" : r.kind === "share" ? `${r.before.toFixed(1)}%` : whole(r.before)) },
    { key: "chg", header: "Change", numeric: true, cell: (r) => (r.change == null ? "–" : <Delta value={r.change}>{r.kind === "share" ? signedPts(r.change) : signedWhole(r.change)}</Delta>) },
  ];
  return (
    <Card testId="pulse-breadth">
      <CardHead title={`How many stocks took part · ${b.group}`} info={`The stocks of ${b.group} counted ${when}${b.live ? " (a count every quarter hour from live prices; the 52-week highs and lows come with the close)" : ""}. Every stock counts once, whatever its size.`} />
      <DataTable stack label={`Breadth of ${b.group}`} columns={cols} rows={b.rows} rowKey={(r) => r.key} />
      {b.ratio != null && <p className="k-note">{whole(b.adv)} rose to {whole(b.dec)} fell: {b.ratio.toFixed(2)} to 1, of {whole(b.stocks)} stocks.</p>}
    </Card>
  );
}

export function SectorsTable({ s }: { s: NonNullable<PulseMood["sectors"]> }) {
  type Row = (typeof s.rows)[number];
  const cols: Column<Row>[] = [
    { key: "n", header: "Sector index", rowHeader: true, cell: (r) => r.label },
    { key: "d", header: "Today", numeric: true, cell: (r) => chg(r.change_pct) },
    { key: "w", header: "1 week", numeric: true, cell: (r) => chg(r.w1) },
    { key: "m", header: "1 month", numeric: true, cell: (r) => chg(r.m1) },
    { key: "by", header: "Moved by", wrap: true, cell: (r) => (r.movers.length ? movedBy(r.movers, (v) => pct(v, 2)) : "–") },
  ];
  return (
    <Card testId="pulse-sectors">
      <CardHead title="Sectors" info="Each sector index's move today, over the last 5 and 21 sessions (against today's level), and the two of its largest companies that moved most, from their market value and today's move." />
      <p className="k-small" data-testid="pulse-sector-count">{sectorCount(s)}.</p>
      <DataTable stack label="Sector indices, best first" columns={cols} rows={s.rows} rowKey={(r) => r.name} />
    </Card>
  );
}

export function MoversTable({ m }: { m: NonNullable<PulseMood["movers"]>[number] }) {
  const rows = moverRows(m);
  const cols: Column<(typeof rows)[number]>[] = [
    { key: "n", header: "Company", rowHeader: true, cell: (r) => r.name ?? r.symbol },
    { key: "c", header: "Move today", numeric: true, cell: (r) => chg(r.change_pct) },
    { key: "p", header: "Points", numeric: true, cell: (r) => <Delta value={r.points}>{signedPoints(r.points)}</Delta> },
  ];
  return (
    <Card testId="pulse-movers" label={`What moved the ${m.index}`}>
      <CardHead title={`What moved the ${m.index}`} info="The companies adding the most points to the index and taking the most from it today. Points are estimated from each company's market value against the index's total, so they differ a little from the exchange's own free-float figures." />
      <DataTable stack label={`Companies that moved the ${m.index} most`} columns={cols} rows={rows} rowKey={(r) => r.symbol}
        foot={m.est_total != null && m.actual != null ? { n: "All its companies, estimated", c: "", p: <span>{signedPoints(m.est_total)}</span> } : undefined} />
      {m.actual != null && <p className="k-note" data-testid="pulse-movers-actual">The {m.index} itself moved {signedPoints(m.actual)} points.</p>}
    </Card>
  );
}

export function FlowsTable({ f }: { f: NonNullable<PulseMood["flows"]> }) {
  type Row = (typeof f.rows)[number];
  const net = (v: number) => <Delta value={v}>{crore(v)}</Delta>;
  const cols: Column<Row>[] = [
    { key: "d", header: "Day", rowHeader: true, cell: (r) => day(r.day) },
    { key: "f", header: "FII net", numeric: true, cell: (r) => net(r.fii) },
    { key: "i", header: "DII net", numeric: true, cell: (r) => net(r.dii) },
  ];
  return (
    <Card testId="pulse-flows">
      <CardHead title="FII and DII, cash market" info={f.note} />
      <DataTable stack label="FII and DII net buying, last five days" columns={cols} rows={[...f.rows].reverse()} rowKey={(r) => r.day}
        foot={{ d: `${f.rows.length}-day total`, f: net(f.fii_total), i: net(f.dii_total) }} />
    </Card>
  );
}

export function RiskTable({ r }: { r: NonNullable<PulseMood["risk"]> }) {
  const cols: Column<(typeof r.rows)[number]>[] = [
    { key: "n", header: "Measure", rowHeader: true, cell: (x) => x.label },
    { key: "p", header: "Level", numeric: true, cell: (x) => riskLevel(x) },
    { key: "c", header: "Change", numeric: true, cell: (x) => chg(x.change_pct) },
  ];
  return (
    <Card testId="pulse-risk">
      <CardHead title="Volatility, currencies and rates" info="The volatility index, the rupee, crude oil, gold, the US 10-year yield and the dollar index, with the move since the previous close." />
      <DataTable stack label="Volatility, currencies and rates" columns={cols} rows={r.rows} rowKey={(x) => x.symbol} />
    </Card>
  );
}

export function GlobalTable({ g, region }: { g: NonNullable<PulseMood["global"]>; region: Region }) {
  const cols: Column<(typeof g.rows)[number]>[] = [
    { key: "n", header: "Market", rowHeader: true, cell: (x) => x.label },
    { key: "a", header: "Area", cell: (x) => x.tag },
    { key: "c", header: "Move", numeric: true, cell: (x) => chg(x.change_pct) },
    { key: "s", header: "Session", cell: (x) => (x.same_day === false && x.day ? `on ${day(x.day)}` : "today") },
  ];
  return (
    <Card testId="pulse-global">
      <CardHead title={region === "IN" ? "Other markets" : "Markets overseas"} info={region === "IN" ? "Asian and European markets and US futures: their latest session's move." : "The latest session of the Asian and European markets, and India's."} />
      <DataTable stack label="Other markets" columns={cols} rows={g.rows} rowKey={(x) => x.symbol} />
    </Card>
  );
}

export function CalendarTable({ c }: { c: NonNullable<PulseMood["calendar"]> }) {
  type Row = { key: string; when: string; kind: string; what: ReactNode };
  const rows: Row[] = [
    ...c.results.map((r) => ({ key: `r-${r.symbol}-${r.date}`, when: day(r.date), kind: "Results", what: <>{r.name}{r.purpose ? <span className="k-sub-line">{r.purpose}</span> : null}</> })),
    ...c.ipos.map((i) => ({ key: `i-${i.name}`, when: i.close ? `closes ${day(i.close)}` : "open", kind: "IPO open", what: <>{i.name}{i.low != null && i.high != null ? <span className="k-sub-line">Price band {i.low}–{i.high}</span> : null}</> })),
    ...c.events.map((e) => ({ key: `e-${e.date}-${e.title}`, when: `${day(e.date)}${e.time ? `, ${e.time}` : ""}`, kind: "Event", what: e.title })),
  ];
  const cols: Column<Row>[] = [
    { key: "w", header: "When", rowHeader: true, cell: (r) => r.when },
    { key: "k", header: "Type", cell: (r) => r.kind },
    { key: "d", header: "Details", wrap: true, cell: (r) => r.what },
  ];
  return (
    <Card testId="pulse-calendar">
      <CardHead title="Coming up" info="Results due from the largest companies in the next seven days, IPOs open now, and the economic events on the app's calendar." />
      <DataTable stack label="Results, IPOs and events this week" columns={cols} rows={rows} rowKey={(r) => r.key} />
    </Card>
  );
}

/** Two tables side by side only when their rows are as many; otherwise one above the other. */
export function Pair({ left, right, nl, nr }: { left: ReactNode; right: ReactNode; nl: number; nr: number }) {
  if (pairable(nl, nr)) return <div className="k-cols">{left}{right}</div>;
  return <>{left}{right}</>;
}

/** The index levels, as a table (they were four tiles each with its own small line). */
export function IndexTable({ indices, missing, dayText, whenOf }: { indices: { name: string; price: number; change_pct: number | null; from_high_pct: number | null; stale?: boolean; day?: string | null; live?: boolean; settling?: boolean }[]; missing?: string[];
  dayText: (iso: string) => string; whenOf: (i: { name: string; price: number; change_pct: number | null; from_high_pct: number | null; stale?: boolean; day?: string | null; live?: boolean; settling?: boolean }) => string }) {
  type Row = (typeof indices)[number];
  const level = (i: Row) => i.price.toLocaleString(i.name.includes("NIFTY") || i.name === "SENSEX" ? "en-IN" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const cols: Column<Row>[] = [
    { key: "n", header: "Index", rowHeader: true, cell: (i) => i.name },
    { key: "l", header: "Level", numeric: true, cell: level },
    { key: "c", header: "Change", numeric: true, cell: (i) => (i.change_pct == null ? "–" : <Delta value={i.change_pct}>{pct(i.change_pct, 2)}</Delta>) },
    { key: "h", header: "Against 52-week high", numeric: true, cell: (i) => (i.from_high_pct == null ? "–" : i.from_high_pct > -0.5 ? "near its high" : `${Math.abs(i.from_high_pct).toFixed(1)}% below`) },
    { key: "w", header: "As of", cell: (i) => <span data-testid="index-when" data-stale={i.stale ? "1" : undefined}>{whenOf(i)}</span> },
  ];
  void dayText;
  return (
    <>
      <DataTable stack label="Index levels" columns={cols} rows={indices} rowKey={(i) => i.name} />
      {!!missing?.length && <p className="k-small k-muted" data-testid="index-missing">{missing.join(", ")} couldn't load.</p>}
    </>
  );
}

/* ---------- the AI's read: only lines that stand on a headline or a figure ---------- */
export function HotTable({ ai, region }: { ai: PulseAI; region: Region }) {
  type Row = PulseAI["hot"][number];
  const cols: Column<Row>[] = [
    { key: "n", header: "Company", rowHeader: true, cell: (h) => <b>{h.name}</b> },
    { key: "t", header: "Symbol", cell: (h) => (h.ticker ? <Link className="link" to={`/research/${region}/${encodeURIComponent(h.ticker)}`}>{h.ticker} →</Link> : "–") },
    { key: "w", header: "In the headlines", wrap: true, cell: (h) => h.why },
  ];
  return (
    <Card testId="pulse-hot">
      <CardHead title="Companies in today's headlines" />
      <DataTable stack label="Companies named in today's headlines" columns={cols} rows={ai.hot} rowKey={(h) => h.ticker + h.name} />
    </Card>
  );
}

export function TopicsTable({ ai }: { ai: PulseAI }) {
  type Row = PulseAI["flows"][number];
  const directed = ai.flows.some((f) => f.direction);
  const cols: Column<Row>[] = [
    { key: "t", header: "Topic", rowHeader: true, wrap: true, cell: (f) => <b>{f.title}</b> },
    ...(directed ? [{ key: "d", header: "Direction", cell: (f: Row) => (f.direction ? f.direction.toLowerCase() : "–") } as Column<Row>] : []),
    { key: "w", header: "In the headlines", wrap: true, cell: (f) => f.detail },
  ];
  return (
    <Card testId="pulse-topics">
      <CardHead title="Money and markets in the headlines" />
      <DataTable stack label="Money and markets in the headlines" columns={cols} rows={ai.flows} rowKey={(f) => f.title} />
    </Card>
  );
}

export function ThemesTable({ ai, region }: { ai: PulseAI; region: Region }) {
  type Row = PulseAI["themes"][number];
  const cols: Column<Row>[] = [
    { key: "t", header: "Theme", rowHeader: true, wrap: true, cell: (t) => <Link className="link" to={`/research/themes?region=${region}&q=${encodeURIComponent(t.theme)}`}>{t.theme}</Link> },
    { key: "d", header: "In the headlines", wrap: true, cell: (t) => t.detail },
    { key: "e", header: "Example", cell: (t) => t.example || "–" },
  ];
  return (
    <Card testId="pulse-themes">
      <CardHead title="Themes in play" />
      <DataTable stack label="Themes in play" columns={cols} rows={ai.themes} rowKey={(t) => t.theme} />
    </Card>
  );
}

/** The headlines the main story counts, marked, so "3 of 8" can be counted by eye. */
export function HeadlinesTable({ items, ai }: { items: NewsItem[]; ai: PulseAI | null }) {
  const sorted = [...items].sort((a, b) => (b.at ? Date.parse(b.at) : -Infinity) - (a.at ? Date.parse(a.at) : -Infinity));
  const story = ai?.story ?? null;
  const cols: Column<NewsItem>[] = [
    { key: "h", header: "Headline", rowHeader: true, wrap: true, cell: (n) => <a className="link" href={safeHref(n.url)} target="_blank" rel="noopener noreferrer">{n.headline} ↗</a> },
    ...(story ? [{ key: "s", header: "Main story", cell: (n: NewsItem) => storyOf(story, n.headline) ?? "–" } as Column<NewsItem>] : []),
    { key: "src", header: "Source", cell: (n) => n.source ?? "–" },
    { key: "w", header: "When", cell: (n) => newsWhen(n.at) ?? "–" },
  ];
  if (!items.length) return <EmptyState title="No headlines yet today">They are read again every few minutes.</EmptyState>;
  return (
    <>
      <DataTable stack label="Today's headlines" columns={cols} rows={sorted} rowKey={(n, i) => `${i}-${n.headline}`} />
      {story && <p className="k-note" data-testid="pulse-story">The main story in today's headlines: {story.label}, {story.n} of {story.of} (marked above).</p>}
    </>
  );
}

export function MoodSkeleton() { return <Card><Skeleton label="Reading the tape" lines={3} /></Card>; }
