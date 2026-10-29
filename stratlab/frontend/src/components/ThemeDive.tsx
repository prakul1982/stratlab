import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Badge, BarList, Card, CardHead, DataTable, Spark, Signed, type Column } from "./kit";
import { LineChart } from "./Charts";
import { bizChange, bizValue, periodName } from "../lib/biz";
import { filedOn } from "./BizUpdates";
import { fmtDate, pct, safeHref } from "../lib/format";
import type { Region } from "../lib/research";
import {
  amount, layerLines, pc, points, span, times,
  type BizRow, type Business, type Dive, type DiveRow, type Layer, type LayerLine, type Listing, type NewsRow, type Prices, type Stat,
} from "../lib/theme";

/* The theme deep dive's cards (THEME-1). Every block that shows figures is a table with a header row and aligned columns; every figure is from
 * the stored company facts, with its year and basis said once under the chain table. The AI wrote none of them. */

const co = (r: Region, sym: string) => `/research/${r}/${encodeURIComponent(sym)}`;
const Name = ({ r, sym, name, wide }: { r: Region; sym: string; name: string; wide?: boolean }) => (
  <><Link className="link" to={co(r, sym)}><b>{name}</b></Link>{wide && <><sup aria-hidden="true"> †</sup><span className="sr-only"> (company-wide figures)</span></>}</>
);
const dash = <span className="k-muted">–</span>;
const chg = (v: number | null | undefined) => (v == null ? dash : <Signed value={v} fmt={(x) => pct(x, 1)} />);

/** The whole chain in one table, and the one comparison across layers: where the margin sits. */
export function ChainCard({ dive }: { dive: Dive }) {
  const r = dive.region;
  const top = Math.max(0, ...dive.chain.rows.map((x) => x.ebitda ?? 0));
  const cols: Column<(typeof dive.chain.rows)[number]>[] = [
    { key: "l", header: "Layer", rowHeader: true, wrap: true, cell: (x) => <>{x.layer}{x.layer === dive.chain.highest && <> <Badge tone="plain" dot={false}>Highest</Badge></>}{x.layer === dive.chain.lowest && <> <Badge tone="plain" dot={false}>Lowest</Badge></>}</> },
    { key: "n", header: "Companies", numeric: true, cell: (x) => x.n },
    { key: "rev", header: "Revenue", numeric: true, info: "The layer's companies' revenue added together, latest full year.", cell: (x) => amount(x.revenue, r) },
    { key: "e", header: "EBITDA margin", numeric: true, info: "Median of the layer's companies. Operating profit before depreciation as a share of revenue.", cell: (x) => pc(x.ebitda) },
    { key: "nm", header: "Net margin", numeric: true, cell: (x) => pc(x.net) },
    { key: "c", header: "ROCE", numeric: true, info: "Return on capital employed, median of the layer's companies.", cell: (x) => pc(x.roce) },
  ];
  return (
    <Card id="theme-chain" label="The whole chain in one table">
      <CardHead title="The whole chain in one table" info={dive.basis} />
      <DataTable label="The value chain by layer: companies, revenue and median margins" columns={cols} rows={dive.chain.rows} rowKey={(x) => x.layer} />
      {dive.chain.line && <p className="k-small">{dive.chain.line}</p>}
      {top > 0 && dive.chain.rows.some((x) => x.ebitda != null) && (
        <BarList label="Median EBITDA margin by layer" rows={dive.chain.rows.filter((x) => x.ebitda != null).map((x) => ({ key: x.layer, name: x.layer, value: pc(x.ebitda), pct: ((x.ebitda ?? 0) / top) * 100, note: `${x.ebitda_n} compan${x.ebitda_n === 1 ? "y" : "ies"}` }))} />
      )}
      <p className="k-note">{dive.basis}</p>
    </Card>
  );
}

function Spk({ row }: { row: BizRow }) {
  return <Spark values={row.points.map((p) => p.value)} label={`${row.name}, ${row.metric}, by month`} tone="neutral" height={24} />;
}

/** The operating figures companies file between results, as a table with a small trend in each row. */
export function BusinessTable({ rows, label }: { rows: BizRow[]; label: string }) {
  const cols: Column<BizRow>[] = [
    { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x) => <><b>{x.name}</b><span className="k-sub-line">{x.metric}</span></> },
    { key: "p", header: "Period", cell: (x) => periodName(x.period, x.span) },
    { key: "v", header: "Latest", numeric: true, cell: (x) => bizValue(x.value, x.unit) },
    { key: "pv", header: "Previous", numeric: true, cell: (x) => bizValue(x.prev, x.unit) },
    { key: "ya", header: "Year ago", numeric: true, cell: (x) => bizValue(x.year_ago, x.unit) },
    { key: "cp", header: "On previous", numeric: true, cell: (x) => <Signed value={x.change_prev}>{bizChange(x.change_prev, x.unit)}</Signed> },
    { key: "cy", header: "On the year", numeric: true, cell: (x) => <Signed value={x.change_year}>{bizChange(x.change_year, x.unit)}</Signed> },
    { key: "t", header: "Trend", cell: (x) => <Spk row={x} /> },
    { key: "f", header: "Filing", cell: (x) => (x.url ? <a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">{filedOn(x.filed)}{x.exchange ? ` · ${x.exchange}` : ""}{x.page ? `, p. ${x.page}` : ""} ↗</a> : dash) },
  ];
  return <DataTable label={label} columns={cols} rows={rows} rowKey={(x) => x.symbol} />;
}

function layerColumns(r: Region, wide: Set<string>): Column<LayerLine>[] {
  const f = (k: "ebitda" | "net" | "roce") => (x: LayerLine) => x.kind === "company" ? pc(x.row![k]) : x.kind === "median" ? <b>{pc(x.stats?.[k]?.median)}</b> : span(x.stats?.[k]);
  return [
    { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x) => x.kind !== "company" ? <b>{x.label}</b>
      : <><Name r={r} sym={x.row!.symbol} name={x.row!.name} wide={wide.has(x.row!.symbol)} />{x.row!.what && <span className="k-sub-line">In its own words: “{x.row!.what}”</span>}</> },
    { key: "rev", header: "Revenue", numeric: true, cell: (x) => x.kind === "company" ? amount(x.row!.revenue, r) : "" },
    { key: "e", header: "EBITDA margin", numeric: true, cell: f("ebitda") },
    { key: "n", header: "Net margin", numeric: true, cell: f("net") },
    { key: "roce", header: "ROCE", numeric: true, cell: f("roce") },
    { key: "y", header: "Year", cell: (x) => (x.kind === "company" ? x.row!.year ?? dash : "") },
  ];
}

/** One value-chain layer: what it does (general knowledge, no figures), its table of real figures with the median and range, and what they show. */
export function LayerCard({ layer, i, region, business }: { layer: Layer; i: number; region: Region; business?: BizRow[] }) {
  const wide = useMemo(() => new Set(layer.company_wide), [layer]);
  const lines = layerLines(layer);
  const hist = layer.history;
  return (
    <Card id={`layer-${i}`} label={`Layer ${i + 1}: ${layer.layer}`}>
      <CardHead title={<><span className="k-muted">Layer {i + 1} · </span>{layer.layer}</>} />
      {layer.description && <p className="k-small">{layer.description} <span className="k-muted">(Written by AI from general knowledge, with no figures.)</span></p>}
      {lines.length === 0
        ? <p className="k-small">No listed company is shown for this layer: none of the companies the map named has a description that shows it does this work.</p>
        : <>
          <DataTable label={`${layer.layer}: companies, revenue and margins`} columns={layerColumns(region, wide)} rows={lines} rowKey={(x) => x.key} rowAttrs={(x) => ({ "data-kind": x.kind })} />
          {layer.line && <p className="k-small">{layer.line}</p>}
          {wide.size > 0 && <p className="k-note">† The company runs other businesses too, so its figures are the whole company's, not this layer's own business.</p>}
        </>}
      {hist && hist.years.length >= 2 && (
        <DataTable label={`${layer.layer}: margin by year`} columns={[
          { key: "y", header: "Year", rowHeader: true, cell: (h: { y: string; e: number | null; n: number | null }) => h.y },
          { key: "e", header: "EBITDA margin", numeric: true, info: `The ${hist.n} companies that report every year here, added together.`, cell: (h) => pc(h.e) },
          { key: "n", header: "Net margin", numeric: true, cell: (h) => pc(h.n) },
        ]} rows={hist.years.map((y, k) => ({ y, e: hist.ebitda[k], n: hist.net[k] }))} rowKey={(h) => h.y} />
      )}
      {business && business.length > 0 && (
        <>
          <h3 className="k-sub">Operating figures filed between results</h3>
          <BusinessTable rows={business} label={`${layer.layer}: operating figures from business updates`} />
        </>
      )}
    </Card>
  );
}

/** Sub-themes, each with the listed companies that do it. */
export function SubThemesCard({ dive, business }: { dive: Dive; business?: Business | null }) {
  const r = dive.region;
  if (dive.subs.length === 0) return null;
  const cols: Column<(typeof dive.subs)[number]["companies"][number]>[] = [
    { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x) => <Name r={r} sym={x.symbol} name={x.name} wide={x.company_wide} /> },
    { key: "w", header: "What it does here, in its own words", wrap: true, cell: (x) => (x.what ? <>“{x.what}”</> : dash) },
    { key: "m", header: "Market value", numeric: true, cell: (x) => amount(x.cap, r) },
    { key: "g", header: "Revenue growth", numeric: true, info: "Latest full year against the year before.", cell: (x) => chg(x.sales_1y) },
    { key: "e", header: "EBITDA margin", numeric: true, cell: (x) => pc(x.ebitda) },
  ];
  return (
    <Card id="theme-subs" label="Sub-themes">
      <CardHead title="Sub-themes and the companies that do them" info="Each company is shown only where its own description says it does that work." />
      {dive.subs.map((s, k) => (
        <section key={s.name} className="k-stack">
          <h3 className="k-sub">{s.name}</h3>
          <p className="k-small k-muted">{s.detail}</p>
          {s.companies.length === 0
            ? <p className="k-small">No listed company is shown for this sub-theme.</p>
            : <DataTable label={`${s.name}: listed companies`} columns={cols} rows={s.companies} rowKey={(x) => x.symbol} />}
          {(business?.subs[k]?.rows.length ?? 0) > 0 && <BusinessTable rows={business!.subs[k].rows} label={`${s.name}: operating figures from business updates`} />}
        </section>
      ))}
    </Card>
  );
}

export interface Claim { text: string; status: "current" | "general"; source: { headline: string; at: string; outlet: string; url: string } | null }
/** Tailwinds and risks in one table: a claim is "Checked" only when a dated headline still shows what it rests on. */
export function ClaimsCard({ tailwinds, risks }: { tailwinds: Claim[]; risks: Claim[] }) {
  type Row = Claim & { kind: string; key: string };
  const rows: Row[] = [...tailwinds.map((c, i) => ({ ...c, kind: "Tailwind", key: `t${i}` })), ...risks.map((c, i) => ({ ...c, kind: "Risk", key: `r${i}` }))];
  if (rows.length === 0) return null;
  const cols: Column<Row>[] = [
    { key: "k", header: "Kind", rowHeader: true, cell: (x) => x.kind },
    { key: "t", header: "What", wrap: true, cell: (x) => x.text },
    { key: "s", header: "Checked against", wrap: true, cell: (x) => (x.status === "current" && x.source
      ? <><Badge tone="ok" dot={false}>Checked</Badge> <a className="link" href={safeHref(x.source.url)} target="_blank" rel="noopener noreferrer">{x.source.headline}</a><span className="k-sub-line">{fmtDate(x.source.at)} · {x.source.outlet}</span></>
      : <><Badge tone="plain" dot={false}>General background</Badge><span className="k-sub-line">No dated source found for it.</span></>) },
  ];
  return (
    <Card id="theme-claims" label="Tailwinds and risks">
      <CardHead title="Tailwinds and risks" info="Checked: a headline dated within the last 18 months shows the programme or event is still current. A claim a dated headline showed had ended or been replaced is left out. General background: written by AI from general knowledge, with no figures, and no dated source was found for it." />
      <DataTable label="Tailwinds and risks, with the dated headline that supports each" columns={cols} rows={rows} rowKey={(x) => x.key} />
    </Card>
  );
}

export function NewsCard({ items, loading }: { items: NewsRow[] | null; loading: boolean }) {
  const cols: Column<NewsRow>[] = [
    { key: "d", header: "Date", rowHeader: true, cell: (x) => fmtDate(x.at) },
    { key: "h", header: "Headline", wrap: true, cell: (x) => (x.url ? <a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">{x.headline} ↗</a> : x.headline) },
    { key: "c", header: "Company", wrap: true, cell: (x) => x.company ?? <span className="k-muted">The theme</span> },
    { key: "s", header: "Source", cell: (x) => x.source },
  ];
  return (
    <Card id="theme-news" label="Latest on this theme">
      <CardHead title="Latest on this theme" info="The most recent dated headlines and exchange filings for the theme's companies, as published. No view is added." />
      {items == null ? (loading ? <p className="k-note">Loading the latest headlines…</p> : <p className="k-note">The latest headlines couldn't be loaded.</p>)
        : <DataTable label="Latest dated headlines and filings for the theme" columns={cols} rows={items} rowKey={(x) => `${x.at}${x.headline}`} empty="No recent headlines or filings were found for this theme's companies." />}
    </Card>
  );
}

// ---------- the theme in numbers ----------
interface KV { key: string; measure: ReactNode; a: ReactNode; b?: ReactNode; c?: ReactNode; d?: ReactNode }
const kv = (label: string, heads: [string, string?, string?, string?], rows: KV[], measureHead = "Measure"): { label: string; columns: Column<KV>[]; rows: KV[] } => ({
  label, rows, columns: [
    { key: "m", header: measureHead, rowHeader: true, wrap: true, cell: (x) => x.measure },
    { key: "a", header: heads[0], numeric: true, cell: (x) => x.a },
    ...(heads[1] ? [{ key: "b", header: heads[1], numeric: true, cell: (x: KV) => x.b ?? dash }] : []),
    ...(heads[2] ? [{ key: "c", header: heads[2], numeric: true, cell: (x: KV) => x.c ?? dash }] : []),
    ...(heads[3] ? [{ key: "d", header: heads[3], numeric: true, cell: (x: KV) => x.d ?? dash }] : []),
  ],
});
const KVTable = ({ t }: { t: ReturnType<typeof kv> }) => <DataTable label={t.label} columns={t.columns} rows={t.rows} rowKey={(x) => x.key} />;
const med = (s: Stat | null | undefined, f: (v: number) => string = (v) => pc(v)) => (s ? f(s.median) : dash);

export function NumbersCards({ dive, prices, pricesBusy }: { dive: Dive; prices: Prices | null; pricesBusy: boolean }) {
  const r = dive.region, s = dive.sections;
  const gm = s.growth;
  const growthRows: KV[] = (["revenue", "profit"] as const).map((k) => ({
    key: k, measure: k === "revenue" ? "Revenue" : "Net profit",
    a: gm.aggregate[`${k}_1y`] ? chg(gm.aggregate[`${k}_1y`].value) : dash, b: gm.aggregate[`${k}_3y`] ? chg(gm.aggregate[`${k}_3y`].value) : dash,
    c: gm.median[`${k}_1y`] ? chg(gm.median[`${k}_1y`].median) : dash, d: gm.median[`${k}_3y`] ? chg(gm.median[`${k}_3y`].median) : dash,
  }));
  const p5 = (["revenue", "profit"] as const).some((k) => gm.median[`${k}_5y`]);
  const m = s.margins;
  const val = s.valuation, bal = s.balance, own = s.ownership, ev = s.events, mg = s.management;
  const medianPe = val.pe?.median, marketPe = val.market_pe?.median;
  return (
    <>
      <Card id="numbers-size" label="Size and shape">
        <CardHead title="Size and shape" info={`Companies in the theme with a stored company page. Market value is price times shares in issue, as each company's page shows it.`} />
        <DataTable label="The theme's biggest companies by market value" columns={[
          { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x: (typeof s.size.biggest)[number]) => <Name r={r} sym={x.symbol} name={x.name} wide={dive.company_wide.includes(x.symbol)} /> },
          { key: "m", header: "Market value", numeric: true, cell: (x) => amount(x.cap, r) },
          { key: "s", header: "Share of the theme", numeric: true, cell: (x) => pc(x.share) },
        ]} rows={s.size.biggest} rowKey={(x) => x.symbol} foot={{ c: `All ${s.size.companies} listed companies (${s.size.with_value} with a market value)`, m: amount(s.size.total_cap, r), s: "100.0%" }} />
        {s.size.top3_share != null && <p className="k-note">The three largest make up {pc(s.size.top3_share)} of the theme's market value.</p>}
      </Card>

      <Card id="numbers-growth" label="Growth and profitability">
        <CardHead title="Growth and profitability" info="Together: the companies' figures added up, for the companies that report both ends of the period (growth a year for three years). Median: the middle company's own rate. Companies that run other businesses too are left out." />
        <KVTable t={kv("Revenue and profit growth", ["Together, 1 year", "Together, 3 years a year", "Median company, 1 year", "Median company, 3 years a year"], growthRows)} />
        {p5 && <p className="k-note">Median company, 5 years a year: revenue {med(gm.median.revenue_5y, (v) => pct(v))}, profit {med(gm.median.profit_5y, (v) => pct(v))}.</p>}
        {m && m.years.length >= 2 ? (
          <>
            <h3 className="k-sub">Margins over time, the {m.n} companies that report every year</h3>
            <LineChart ariaLabel="Aggregate EBITDA margin and net margin of the theme's companies, by year" height={200} format={(v) => pc(v)} labels={m.years}
              lines={[{ label: "EBITDA margin", color: "var(--blue)", values: m.ebitda }, { label: "Net margin", color: "var(--orange)", values: m.net }]} legend />
            <DataTable label="The theme's margins by year" columns={[
              { key: "y", header: "Year", rowHeader: true, cell: (h: { y: string; e: number | null; n: number | null }) => h.y },
              { key: "e", header: "EBITDA margin", numeric: true, cell: (h) => pc(h.e) }, { key: "n", header: "Net margin", numeric: true, cell: (h) => pc(h.n) },
            ]} rows={m.years.map((y, i) => ({ y, e: m.ebitda[i], n: m.net[i] }))} rowKey={(h) => h.y} />
          </>
        ) : <p className="k-note">Too few companies report the same years to draw the margins over time.</p>}
        <DataTable label="Margins and returns: the theme against all listed companies" columns={[
          { key: "m", header: "Median", rowHeader: true, cell: (x: KV) => x.measure }, { key: "a", header: "Theme", numeric: true, cell: (x) => x.a }, { key: "b", header: "Companies", numeric: true, cell: (x) => x.b },
          { key: "c", header: "All listed", numeric: true, info: "The middle company among all those StratLab holds figures for.", cell: (x) => x.c },
        ]} rowKey={(x) => x.key} rows={[
          { key: "e", measure: "EBITDA margin", a: med(s.medians.ebitda), b: s.medians.ebitda?.n ?? dash, c: med(s.market.opm) },
          { key: "n", measure: "Net margin", a: med(s.medians.net), b: s.medians.net?.n ?? dash, c: med(s.market.net_margin) },
          { key: "r", measure: "ROCE", a: med(s.medians.roce), b: s.medians.roce?.n ?? dash, c: med(s.market.roce) },
          { key: "g", measure: "Revenue growth, 3 years a year", a: med(gm.median.revenue_3y, (v) => pct(v)), b: gm.median.revenue_3y?.n ?? dash, c: med(s.market.sales_cagr_3y, (v) => pct(v)) },
        ]} />
      </Card>

      <Card id="numbers-valuation" label="Valuation">
        <CardHead title="Valuation" info="P/E is the price over the last four reported quarters' earnings per share. P/B is the price over book value per share. EV/EBITDA is market value plus debt less cash, over the latest year's EBITDA. Each is left out for a company where a figure it needs is missing, and for a loss." />
        <DataTable label="Valuation: the theme against all listed companies" columns={[
          { key: "m", header: "Measure", rowHeader: true, cell: (x: KV) => x.measure }, { key: "a", header: "Theme median", numeric: true, cell: (x) => x.a }, { key: "b", header: "Range", numeric: true, cell: (x) => x.b },
          { key: "c", header: "Companies", numeric: true, cell: (x) => x.c }, { key: "d", header: "All listed, median", numeric: true, cell: (x) => x.d },
        ]} rowKey={(x) => x.key} rows={[
          { key: "pe", measure: "P/E", a: med(val.pe, (v) => times(v)), b: span(val.pe, (v) => times(v)), c: val.pe?.n ?? dash, d: med(val.market_pe, (v) => times(v)) },
          { key: "pb", measure: "P/B", a: med(val.pb, (v) => times(v)), b: span(val.pb, (v) => times(v)), c: val.pb?.n ?? dash, d: med(val.market_pb, (v) => times(v)) },
          { key: "ev", measure: "EV/EBITDA", a: med(val.ev_ebitda, (v) => times(v)), b: span(val.ev_ebitda, (v) => times(v)), c: val.ev_ebitda?.n ?? dash, d: dash },
        ]} />
        {medianPe != null && marketPe != null && <p className="k-small">The theme's median P/E is {times(medianPe)} against {times(marketPe)} for all {val.market_n.toLocaleString("en-IN")} listed companies with one.</p>}
        {val.ev_missing > 0 && <p className="k-note">EV/EBITDA is n/a for {val.ev_missing} compan{val.ev_missing === 1 ? "y" : "ies"} where debt, cash or EBITDA isn't stored. The all-listed comparison is not worked out for it.</p>}
        {val.history.length >= 2
          ? <DataTable label="The theme's median P/E over time" columns={[
            { key: "d", header: "Week of", rowHeader: true, cell: (h: (typeof val.history)[number]) => fmtDate(h.d) }, { key: "p", header: "Median P/E", numeric: true, cell: (h) => times(h.pe) }, { key: "n", header: "Companies", numeric: true, cell: (h) => h.n },
          ]} rows={val.history.slice(-26).reverse()} rowKey={(h) => h.d} />
          : <p className="k-note">The theme's own P/E history builds forward from this page: it keeps the median once a week from now.</p>}
      </Card>

      <Card id="numbers-quarter" label="The latest quarter">
        <CardHead title="The latest quarter against a year earlier" info="Each company's latest reported quarter against the same quarter a year before, as its company page gives it. It compares a company with its own past, not with anyone's estimate." />
        <DataTable label="Latest reported quarter against the same quarter a year before" columns={[
          { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x: (typeof s.quarter.companies)[number]) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "q", header: "Quarter", cell: (x) => x.of }, { key: "s", header: "Revenue", numeric: true, cell: (x) => chg(x.sales) }, { key: "p", header: "Net profit", numeric: true, cell: (x) => chg(x.profit) },
        ]} rows={s.quarter.companies} rowKey={(x) => x.symbol} empty="No company in the theme has a latest quarter stored against a year before."
          foot={s.quarter.companies.length ? { c: `${s.quarter.sales_up} up, ${s.quarter.sales_down} down on revenue; ${s.quarter.profit_up} up, ${s.quarter.profit_down} down on profit`, q: "Median", s: chg(s.quarter.sales?.median), p: chg(s.quarter.profit?.median) } : undefined} />
      </Card>

      <Card id="numbers-balance" label="Balance sheet and cash">
        <CardHead title="Balance sheet and cash" info="Debt to equity is borrowings over shareholders' equity (not for lenders). Cash from operations over profit is the latest year's." />
        <KVTable t={kv("Balance sheet and cash of the theme's companies", ["Median", "Range", "Companies"], [
          { key: "de", measure: "Debt to equity", a: med(bal.debt_equity, (v) => times(v, 2)), b: span(bal.debt_equity, (v) => times(v, 2)), c: bal.with_debt_equity },
          { key: "ic", measure: "Interest cover (profit before interest and tax over interest)", a: med(bal.interest_cover, (v) => times(v)), b: span(bal.interest_cover, (v) => times(v)), c: bal.interest_cover?.n ?? dash },
          { key: "cfo", measure: "Cash from operations as a multiple of net profit", a: med(bal.cfo_to_profit, (v) => times(v, 2)), b: span(bal.cfo_to_profit, (v) => times(v, 2)), c: bal.cfo_n || dash },
        ])} />
        <p className="k-note">{bal.with_debt_equity > 0 ? `${bal.above_1} of ${bal.with_debt_equity} companies have borrowings above their equity. ` : ""}{bal.interest_cover ? `${bal.cover_under_2} of ${bal.interest_cover.n} cover their interest less than twice. ` : ""}A company with no interest cost has no interest cover.</p>
      </Card>

      <PriceCards dive={dive} prices={prices} busy={pricesBusy} />

      <Card id="numbers-ownership" label="Ownership">
        <CardHead title="Ownership" info="From each company's latest shareholding filing with the exchange: the promoter group's named holders added up, and the funds, insurers and foreign investors the filing names above 1%. Change is against the quarter before, in percentage points." />
        <DataTable label="Promoter and named institutional holdings" columns={[
          { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x: (typeof own.holdings)[number]) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "p", header: "Promoters", numeric: true, cell: (x) => pc(x.promoter) }, { key: "pc", header: "Change", numeric: true, cell: (x) => <Signed value={x.promoter_change}>{points(x.promoter_change)}</Signed> },
          { key: "i", header: "Named institutions", numeric: true, cell: (x) => pc(x.institutions) }, { key: "ic", header: "Change", numeric: true, cell: (x) => <Signed value={x.institutions_change}>{points(x.institutions_change)}</Signed> },
          { key: "q", header: "Quarter", cell: (x) => x.quarter },
        ]} rows={own.holdings} rowKey={(x) => x.symbol} empty="No shareholding filings are stored for these companies yet." />
        <DataTable label="Promoter and insider purchases, last 90 days, and pledges" columns={[
          { key: "k", header: "What", rowHeader: true, cell: (x: { key: string; what: string; name: string; sym: string; at: string; url?: string | null }) => x.what },
          { key: "c", header: "Company", wrap: true, cell: (x) => <Name r={r} sym={x.sym} name={x.name} /> }, { key: "d", header: "Filed", cell: (x) => fmtDate(x.at) },
          { key: "f", header: "Filing", cell: (x) => (x.url ? <a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">Open ↗</a> : dash) },
        ]} rows={[
          ...own.insider_buys.map((b) => ({ key: `b${b.symbol}`, what: "Promoter or insider bought", name: b.name, sym: b.symbol, at: b.at, url: null as string | null })),
          ...own.pledges.map((p, i) => ({ key: `p${i}${p.symbol}`, what: p.label, name: p.name, sym: p.symbol, at: p.at, url: p.url ?? null })),
        ]} rowKey={(x) => x.key} empty="No promoter or insider purchases and no pledge filings in the last 90 days." />
        {own.holdings.length > 0 && <p className="k-note">Promoters' stake rose at {own.promoter_up} and fell at {own.promoter_down} of the {own.holdings.length} companies with a filing stored.</p>}
      </Card>

      <Card id="numbers-events" label="Events">
        <CardHead title="Events" info="Results dates as the companies announced them, results filings with the numbers as filed, ex-dates of dividends and other corporate actions, and red-flag filings of the last 90 days." />
        <DataTable label="Results due in the next four weeks" columns={[
          { key: "d", header: "Date", rowHeader: true, cell: (x: (typeof ev.results_due)[number]) => fmtDate(x.date) }, { key: "c", header: "Company", wrap: true, cell: (x) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "p", header: "Purpose", wrap: true, cell: (x) => x.purpose ?? dash },
        ]} rows={ev.results_due} rowKey={(x) => x.symbol + x.date} empty="No results dates are announced for these companies in the next four weeks." />
        <DataTable label="Results filed in the last 30 days" columns={[
          { key: "d", header: "Filed", rowHeader: true, cell: (x: (typeof ev.results_filed)[number]) => fmtDate(x.date) }, { key: "c", header: "Company", wrap: true, cell: (x) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "n", header: "Numbers as filed", wrap: true, cell: (x) => (x.numbers.length ? x.numbers.map((n) => `${n.label} ${n.value}`).join(" · ") : dash) },
          { key: "f", header: "Filing", cell: (x) => (x.url ? <a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">Open ↗</a> : dash) },
        ]} rows={ev.results_filed} rowKey={(x) => x.symbol + x.date} empty="No results were filed by these companies in the last 30 days." />
        <DataTable label="Dividends, splits and other corporate actions, from 30 days ago to 60 days ahead" columns={[
          { key: "d", header: "Ex-date", rowHeader: true, cell: (x: (typeof ev.actions)[number]) => fmtDate(x.date) }, { key: "c", header: "Company", wrap: true, cell: (x) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "a", header: "Action", wrap: true, cell: (x) => (x.text ? `${x.label}: ${x.text}` : x.label) },
        ]} rows={ev.actions} rowKey={(x) => x.symbol + x.date + x.label} empty="No dividends, splits or other corporate actions in that window." />
        <DataTable label="Red-flag filings, last 90 days" columns={[
          { key: "d", header: "Filed", rowHeader: true, cell: (x: (typeof own.red_flags)[number]) => fmtDate(x.at) }, { key: "c", header: "Company", wrap: true, cell: (x) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "l", header: "Kind", wrap: true, cell: (x) => x.label }, { key: "f", header: "Filing", cell: (x) => (x.url ? <a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">Open ↗</a> : dash) },
        ]} rows={own.red_flags} rowKey={(x) => x.symbol + x.at + x.label} empty="No red-flag filings for these companies in the last 90 days." />
      </Card>

      <Card id="numbers-management" label="Management">
        <CardHead title="Management report cards" info="What management said it would deliver on earnings calls, set against the reported years. Only annual targets are settled here; each company's own page has the rest." />
        <DataTable label="Management targets met and missed" columns={[
          { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x: (typeof mg.companies)[number]) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "m", header: "Targets met", numeric: true, cell: (x) => x.met }, { key: "x", header: "Missed", numeric: true, cell: (x) => x.missed },
        ]} rows={mg.companies} rowKey={(x) => x.symbol} foot={{ c: `${mg.with_card} compan${mg.with_card === 1 ? "y" : "ies"} with a stored report card`, m: mg.met, x: mg.missed }}
          empty="No stored management report cards for these companies yet." />
      </Card>

      <LeadersCard dive={dive} prices={prices} />
    </>
  );
}

/** New issues in the IPO tracker that belong in the theme, each with the words from its own offer that show the work. */
export function ListingsCard({ items, checked, region }: { items: Listing[] | null; checked: boolean; region: Region }) {
  const cols: Column<Listing>[] = [
    { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x) => <><Link className="link" to={`/invest/ipos/${encodeURIComponent(x.id)}`}><b>{x.name}</b></Link>{x.symbol && <span className="k-sub-line">{x.symbol}</span>}</> },
    { key: "s", header: "Stage", cell: (x) => ({ upcoming: "Coming", open: "Open for bids", closed: "Awaiting listing", listed: "Listed" } as Record<string, string>)[x.stage] ?? x.stage },
    { key: "d", header: "Date", cell: (x) => (x.stage === "listed" || x.stage === "closed" ? (x.listing ? fmtDate(x.listing) : x.close ? fmtDate(x.close) : "–") : x.open ? fmtDate(x.open) : "–") },
    { key: "g", header: "In the theme as", wrap: true, cell: (x) => x.groups.join(", ") },
    { key: "w", header: "In its own words", wrap: true, cell: (x) => <>“{x.what}”</> },
  ];
  return (
    <Card id="numbers-listings" label="New listings">
      <CardHead title="New listings in the theme" info={`Issues in StratLab's IPO list that are open, coming, awaiting listing or listed in the last year, kept only where the issuer's own offer says it does the work of a layer or sub-theme (${region === "IN" ? "India" : "US"}).`} />
      {items == null ? <p className="k-note">{checked ? "Loading the issues…" : "The issues couldn't be checked just now."}</p>
        : <DataTable label="New issues that belong in the theme" columns={cols} rows={items} rowKey={(x) => x.id} empty="No open, coming or recently listed issue in the IPO list shows it does this theme's work." />}
    </Card>
  );
}

function PriceCards({ dive, prices, busy }: { dive: Dive; prices: Prices | null; busy: boolean }) {
  const s = dive.sections.price;
  const rows: KV[] = [
    { key: "stage2", measure: "In Stage 2 (advancing)", a: s.stage2.n ? `${s.stage2.count} of ${s.stage2.n}` : dash, b: s.stage2.share != null ? `${s.stage2.share}%` : dash },
    { key: "st", measure: "Supertrend is up", a: s.supertrend_up.n ? `${s.supertrend_up.count} of ${s.supertrend_up.n}` : dash, b: s.supertrend_up.share != null ? `${s.supertrend_up.share}%` : dash },
    { key: "hi", measure: "Within 5% of the 52-week high", a: s.near_high.n ? `${s.near_high.count} of ${s.near_high.n}` : dash, b: s.near_high.share != null ? `${s.near_high.share}%` : dash },
    { key: "lo", measure: "Within 10% of the 52-week low", a: s.near_low.n ? `${s.near_low.count} of ${s.near_low.n}` : dash, b: s.near_low.share != null ? `${s.near_low.share}%` : dash },
    ...(prices ? [{ key: "200", measure: "Above the 200-day average", a: prices.above200.n ? `${prices.above200.count} of ${prices.above200.n}` : dash, b: prices.above200.share != null ? `${prices.above200.share}%` : dash }] : []),
  ];
  const ret = prices?.returns;
  const periods = ["1M", "3M", "1Y", "3Y"] as const;
  const retRows: KV[] = periods.map((p) => ({
    key: p, measure: p === "1M" ? "1 month" : p === "3M" ? "3 months" : p === "1Y" ? "1 year" : "3 years",
    a: prices?.median[p] ? chg(prices.median[p]!.median) : dash, b: ret?.[p]?.theme != null ? chg(ret[p].theme) : dash, c: ret?.[p]?.bench != null ? chg(ret[p].bench) : dash, d: prices?.median[p]?.n ?? dash,
  }));
  return (
    <Card id="numbers-price" label="Price">
      <CardHead title="Price" info="Price change from daily closes. Median: the middle company. Equal-weighted: the companies' weekly changes averaged, so each counts the same. Stage and Supertrend are from each company's stored page." />
      <DataTable label="The theme's price change against the market's index" columns={[
        { key: "m", header: "Over", rowHeader: true, cell: (x: KV) => x.measure }, { key: "a", header: "Median company", numeric: true, cell: (x) => x.a },
        { key: "b", header: "Theme, equal-weighted", numeric: true, cell: (x) => x.b }, { key: "c", header: prices?.benchmark || "Index", numeric: true, cell: (x) => x.c },
        { key: "d", header: "Companies", numeric: true, cell: (x) => x.d },
      ]} rows={retRows} rowKey={(x) => x.key} empty={busy ? "Reading prices…" : "No prices yet."} />
      {busy && !prices && <p className="k-note">Reading the companies' prices (this takes a moment the first time)…</p>}
      {prices && prices.pending > 0 && <p className="k-note">{prices.pending} companies' prices are still being read; the figures above cover the rest.</p>}
      {prices?.line && (
        <>
          <h3 className="k-sub">The theme against {prices.benchmark}, weekly, rebased to 100</h3>
          <LineChart ariaLabel={`The theme's equal-weighted price line and relative strength against ${prices.benchmark}`} height={220} format={(v) => v.toFixed(1)} labels={prices.line.weeks.map((w) => fmtDate(w))}
            lines={[{ label: "Theme", color: "var(--blue)", values: prices.line.theme }, { label: prices.benchmark, color: "var(--muted)", values: prices.line.bench },
              { label: "Relative strength (theme over index)", color: "var(--orange)", values: prices.line.rs, dash: "4 3" }]} legend baseline={100} />
        </>
      )}
      <DataTable label="Breadth inside the theme" columns={[
        { key: "m", header: "Companies that are", rowHeader: true, cell: (x: KV) => x.measure }, { key: "a", header: "Count", numeric: true, cell: (x) => x.a }, { key: "b", header: "Share", numeric: true, cell: (x) => x.b },
      ]} rows={rows} rowKey={(x) => x.key} />
    </Card>
  );
}

type Sort = { key: string; desc: boolean };
function LeadersCard({ dive, prices }: { dive: Dive; prices: Prices | null }) {
  const r = dive.region;
  const [sort, setSort] = useState<Sort>({ key: "cap", desc: true });
  const ret = useMemo(() => Object.fromEntries((prices?.companies ?? []).map((p) => [p.symbol, p.ret["1Y"]])), [prices]);
  type L = DiveRow & { r1y: number | null };
  const rows: L[] = dive.sections.leaders.map((x) => ({ ...x, r1y: ret[x.symbol] ?? null }));
  const val = (x: L): number | string | null => (sort.key === "name" ? x.name : (x as unknown as Record<string, number | null>)[sort.key] ?? null);
  const sorted = [...rows].sort((a, b) => {
    const va = val(a), vb = val(b);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    const d = typeof va === "string" ? va.localeCompare(String(vb)) : (va as number) - (vb as number);
    return sort.desc ? -d : d;
  });
  const onSort = (key: string) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : key !== "name" }));
  const cols: Column<L>[] = [
    { key: "name", header: "Company", rowHeader: true, wrap: true, sortable: true, cell: (x) => <Name r={r} sym={x.symbol} name={x.name} wide={dive.company_wide.includes(x.symbol)} /> },
    { key: "cap", header: "Market value", numeric: true, sortable: true, cell: (x) => amount(x.cap, r) },
    { key: "sales_1y", header: "Revenue growth", numeric: true, sortable: true, info: "Latest full year against the year before.", cell: (x) => chg(x.sales_1y) },
    { key: "ebitda", header: "EBITDA margin", numeric: true, sortable: true, cell: (x) => pc(x.ebitda) },
    { key: "net", header: "Net margin", numeric: true, sortable: true, cell: (x) => pc(x.net) },
    { key: "roce", header: "ROCE", numeric: true, sortable: true, cell: (x) => pc(x.roce) },
    { key: "pe", header: "P/E", numeric: true, sortable: true, cell: (x) => times(x.pe) },
    { key: "pb", header: "P/B", numeric: true, sortable: true, cell: (x) => times(x.pb) },
    { key: "ev_ebitda", header: "EV/EBITDA", numeric: true, sortable: true, cell: (x) => times(x.ev_ebitda) },
    { key: "r1y", header: "Price, 1 year", numeric: true, sortable: true, cell: (x) => chg(x.r1y) },
  ];
  return (
    <Card id="numbers-leaders" label="Leaders and laggards">
      <CardHead title="Every company, sortable" info="Click a column to sort. Sorted by the figure you pick, not ranked: nothing here says which to own." />
      <DataTable label="Every company in the theme with its figures" columns={cols} rows={sorted} rowKey={(x) => x.symbol} sort={{ ...sort, onSort }} />
    </Card>
  );
}
