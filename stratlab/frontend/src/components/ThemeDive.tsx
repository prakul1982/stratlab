import { useMemo, useState, type ReactNode } from "react";
import { deckFileName } from "../lib/deckName";
import { deckWhenReady } from "../lib/deckReady";
import { REGION_NAME } from "../lib/research";
import { Link } from "react-router-dom";
import { Badge, Card, CardHead, CsvButton, DataTable, ShowLess, Select, Spark, Signed, Meter, usePhone, Working, type Column } from "./kit";
import { Download } from "./Icons";
import { useApp } from "../lib/app";
import { download } from "../lib/share";
import { LineChart } from "./Charts";
import { bizChange, bizValue, periodName } from "../lib/biz";
import { filedOn } from "./BizUpdates";
import { fmtDate, pct, ratio, safeHref } from "../lib/format";
import type { Co, Region, SectorAI } from "../lib/research";
import {
  amount, calcOf, CALC_WORDS, layerLines, medCell, MIN_BASE, NO_WORDS, ownWords, pc, points, span, times,
  themeApi,
  type BizRow, type Business, type Dive, type DiveRow, type Layer, type LayerLine, type Listing, type NewsRow, type Prices, type Stat,
} from "../lib/theme";

/* The theme deep dive's cards (THEME-1). Every block that shows figures is a table with a header row and aligned columns; every figure is from
 * the stored company facts, with its year and basis said once under the chain table. The AI wrote none of them. */

const co = (r: Region, sym: string) => `/research/${r}/${encodeURIComponent(sym)}`;
const Name = ({ r, sym, name, wide }: { r: Region; sym: string; name: string; wide?: boolean }) => (
  // a company that runs other businesses too says so in words under its name, not with a † to look up (owner, 5 Nov: "why is there a sign on it?")
  <><Link className="link" to={co(r, sym)}><b>{name}</b></Link>{wide && <span className="k-sub-line">Whole-company figures</span>}</>
);
const dash = <span className="k-muted">–</span>;

const chg = (v: number | null | undefined) => (v == null ? dash : <Signed value={v} fmt={(x) => pct(x, 1)} />);

/** The basis line without "in $ million": the page writes each amount with its own unit ($14.2B), so a unit note under it would contradict
 *  the figures (LIVE6-017). */
const basisWords = (b: string) => b.replace(/, in (?:₹ crore|\$ million)\./, ".");

/** The whole chain in one table, and the one comparison across layers: where the margin sits. */
export function ChainCard({ dive }: { dive: Dive }) {
  const r = dive.region;
  const top = Math.max(0, ...dive.chain.rows.map((x) => (x.ebitda_n >= MIN_BASE ? x.ebitda ?? 0 : 0)));
  const cols: Column<(typeof dive.chain.rows)[number]>[] = [
    { key: "l", header: "Layer", rowHeader: true, wrap: true, cell: (x) => <>{x.layer}{x.layer === dive.chain.highest && <> <Badge tone="plain" dot={false}>Highest</Badge></>}{x.layer === dive.chain.lowest && <> <Badge tone="plain" dot={false}>Lowest</Badge></>}</> },
    { key: "n", header: "Companies", numeric: true, info: "In the layer's calculations, of the companies it lists.", cell: (x) => (x.listed && x.listed > x.n ? `${x.n} of ${x.listed}` : x.n) },
    { key: "rev", header: "Revenue", numeric: true, info: "The layer's companies' revenue added together, latest full year.", cell: (x) => amount(x.revenue, r) },
    { key: "e", header: "EBITDA margin", numeric: true, info: "Median of the layer's companies. Operating profit before depreciation as a share of revenue. The bar compares the layers.", cell: (x) => (x.ebitda_n < MIN_BASE ? dash : <>{pc(x.ebitda)}{x.ebitda != null && top > 0 && <Meter pct={(x.ebitda / top) * 100} />}</>) },
    { key: "nm", header: "Net margin", numeric: true, cell: (x) => ((x.net_n ?? MIN_BASE) < MIN_BASE ? dash : pc(x.net)) },
    { key: "c", header: "ROCE", numeric: true, info: "Return on capital employed, median of the layer's companies.", cell: (x) => ((x.roce_n ?? MIN_BASE) < MIN_BASE ? dash : pc(x.roce)) },
  ];
  return (
    <Card id="theme-chain" label="The whole chain in one table">
      <CardHead title="The whole chain in one table" info={basisWords(dive.basis)} />
      <DataTable label="The value chain by layer: companies, revenue and median margins" columns={cols} rows={dive.chain.rows} rowKey={(x) => x.layer} />
      {dive.chain.line && <p className="k-small">{dive.chain.line}</p>}
      {dive.chain.rows.some((x) => x.ebitda_n > 0 && x.ebitda_n < MIN_BASE) && <p className="k-note">A median is shown on {MIN_BASE} companies or more in a layer's calculations; each company's own figures are on its layer's table.</p>}
      <p className="k-note">{basisWords(dive.basis)}</p>
    </Card>
  );
}

function Spk({ row }: { row: BizRow }) {
  return <Spark values={row.points.map((p) => p.value)} label={`${row.name}, ${row.metric}, by month`} tone="neutral" height={24} />;
}

/** LIVE6-017: a long table shows its first rows and the rest a press away ("Show all N"), so the page isn't 16,000 px tall. */
function Fold<T>({ rows, n = 10, what = "rows", children }: { rows: T[]; n?: number; what?: string; children: (shown: T[]) => ReactNode }) {
  const [all, setAll] = useState(false);
  return (
    <>
      {children(all || rows.length <= n + 2 ? rows : rows.slice(0, n))}
      {rows.length > n + 2 && (all ? <ShowLess onLess={() => setAll(false)} /> : <button type="button" className="btn quiet sm" data-testid="show-all" onClick={() => setAll(true)}>{`Show all ${rows.length} ${what}`}</button>)}
    </>
  );
}
/** a row whose every figure is a dash says nothing: it is left out (LIVE6-017) */
const isDash = (v: ReactNode) => v == null || v === "–" || v === "" || (typeof v === "object" && v !== null && (v as { props?: { children?: unknown } }).props?.children === "–");
const said = (rows: KV[]) => rows.filter((x) => ![x.a, x.b].every(isDash));

const MEMBERS_SHOWN = 12;     // a group's first rows; the rest a press away (a theme of 500 drug makers is listed in full)

/** Every company in the theme, by layer (THEMES): the base is every listed company the exchange classifies in the theme's industries,
 * which the AI can sort into its layers but never removes; the AI's additions from other industries are marked, confirmed in their own
 * words or not yet. Counts said once, honestly. */
export function MembersCard({ r, region, dive }: { r: SectorAI; region: Region; dive?: Dive | null }) {
  const p = r.placements;
  // LIVE6-006: one market value per company on the page: the dive's (its stated price date) wherever it has the company
  const caps = useMemo(() => {
    const m = new Map<string, number>();
    for (const x of [...(dive?.layers ?? []).flatMap((l) => l.companies), ...(dive?.subs ?? []).flatMap((s) => s.companies), ...(dive?.sections.leaders ?? [])])
      if (x.cap != null && !m.has(x.symbol)) m.set(x.symbol, x.cap);
    return m;
  }, [dive]);
  const inLayer = new Set(r.value_chain.flatMap((v) => v.companies.map((c) => c.ticker)));
  const subOnly = [...new Map(r.sub_themes.flatMap((s) => s.companies).filter((c) => !inLayer.has(c.ticker)).map((c) => [c.ticker, c])).values()];
  const groups = [...r.value_chain.map((v) => ({ name: v.layer, official: !!v.official && v.basis !== "list", rows: v.companies })),
    ...(subOnly.length ? [{ name: "Named in a sub-theme only", official: false, rows: subOnly }] : [])].filter((g) => g.rows.length > 0);
  if (groups.length === 0) return null;
  const total = p?.total ?? new Set(groups.flatMap((g) => g.rows.map((c) => c.ticker))).size;
  const named = p?.named ?? 0, base = (p?.base ?? 0) - named, added = p?.added ?? 0, inds = p?.industries ?? [];
  const cols: Column<Co>[] = [
    { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (c) => <><Name r={region} sym={c.ticker} name={c.name} /><span className="k-sub-line k-muted">{c.ticker}</span></> },
    { key: "i", header: "Industry", wrap: true, cell: (c) => c.industry || dash },
    { key: "m", header: "Market value", numeric: true, cell: (c) => amount(caps.get(c.ticker) ?? c.cap ?? null, region) },
    { key: "w", header: "What it does, in its own words", wrap: true, cell: (c) => { const w = ownWords(c.what, c.name); return w ? <>“{w}”</> : <span className="k-muted">{NO_WORDS}</span>; } },
    { key: "f", header: "In the theme by", cell: (c) => (c.base ? (c.basis === "list" ? "Named in the theme's list" : "Official industry")
      : <><Badge tone="plain" dot={false}>Added</Badge><span className="k-sub-line">{c.verified ? "Confirmed by its own words" : "Not yet confirmed"}</span></>) },
  ];
  return (
    <Card id="theme-members" label="Every company in this theme">
      <CardHead title="Every company in this theme" info="The base is every listed company the exchange's own industry classification puts in the theme's industries: it is in the theme whatever the AI says. The AI sorts companies into layers and adds companies from other industries; an added company stays only while its own description doesn't show otherwise, marked confirmed when its words show the work." />
      <p className="k-small" data-testid="theme-counts">
        <b>{total.toLocaleString("en-IN")} compan{total === 1 ? "y" : "ies"}</b>: {base.toLocaleString("en-IN")} from the official industry list, {named > 0 && `${named.toLocaleString("en-IN")} named in the theme's list, `}{added.toLocaleString("en-IN")} added
        {added > 0 && ` (${p?.confirmed ?? 0} confirmed from ${added === 1 ? "its" : "their"} own description)`}.
      </p>
      {inds.length > 0
        ? <p className="k-small k-muted">Official industries{p?.industries_by === "words" ? ", matched by the theme's own words" : p?.industries_by === "ai" ? ", picked by AI from the exchange's own list" : ""}: {inds.join(" · ")}.</p>
        : named > 0 ? <p className="k-small k-muted">No official industry is this theme's core on its own, so its companies are the theme's named list and the ones the map names.</p>
        : <p className="k-small k-muted">{p?.industries_by === "pending" ? "Until the theme's official industries are picked, its companies are the ones the map names." : "No official industry is this theme's core, so every company here is one the map names, checked against its own description."}</p>}
      {(p?.unclassified ?? 0) > 0 && <p className="k-note">{p!.unclassified!.toLocaleString("en-IN")} US-listed companies have no industry on file yet, so they can't join a theme by industry until their SEC record is read; a few are read each time a theme is checked.</p>}
      {groups.map((g) => <MemberGroup key={g.name} name={g.name} official={g.official} rows={g.rows} cols={cols} />)}
    </Card>
  );
}

function MemberGroup({ name, official, rows, cols }: { name: string; official: boolean; rows: Co[]; cols: Column<Co>[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, MEMBERS_SHOWN);
  return (
    <section className="k-stack">
      <h3 className="k-sub">{name}{official && <span className="k-muted"> · official industry</span>}</h3>
      <DataTable label={`${name}: companies in the theme`} columns={cols} rows={shown} rowKey={(c) => c.ticker} />
      {rows.length > MEMBERS_SHOWN && (all ? <ShowLess onLess={() => setAll(false)} /> : <button type="button" className="btn quiet sm" onClick={() => setAll(true)}>{`Show all ${rows.length} companies`}</button>)}
    </section>
  );
}

/** EXPORT: how a company is in the theme, in the words of the deck and the CSV (theme_routes.by_of says the same). */
export const memberBy = (c: Co) => (c.base ? (c.basis === "list" ? "Named in the theme's list" : "Official industry")
  : c.verified ? "Added, confirmed by its own words" : "Added, not yet confirmed");

export type MemberRow = { co: Co; layer: string; fig: Partial<DiveRow> | null };
/** EXPORT: every company in the theme as the page lists it (each layer's companies, then those named in a sub-theme only), with the
 * figures the dive worked out for it where it has them: the rows of the members CSV and of the deck's company slides (theme_routes.members_of). */
export function memberRows(r: SectorAI, dive: Dive | null): MemberRow[] {
  const figs = new Map<string, Partial<DiveRow>>();
  for (const l of dive?.layers ?? []) for (const c of l.companies) if (!figs.has(c.symbol)) figs.set(c.symbol, c);
  for (const s of dive?.subs ?? []) for (const c of s.companies) if (!figs.has(c.symbol)) figs.set(c.symbol, c);
  const inLayer = new Set(r.value_chain.flatMap((v) => v.companies.map((c) => c.ticker)));
  const only = [...new Map(r.sub_themes.flatMap((s) => s.companies).filter((c) => !inLayer.has(c.ticker)).map((c) => [c.ticker, c])).values()];
  const groups: [string, Co[]][] = [...r.value_chain.map((v) => [v.layer, v.companies] as [string, Co[]]), ...(only.length ? [["Named in a sub-theme only", only] as [string, Co[]]] : [])];
  return groups.flatMap(([layer, cos]) => cos.map((co) => ({ co, layer, fig: figs.get(co.ticker) ?? null })));
}

/** EXPORT: the members CSV's columns: raw figures, each with its unit in the column's name. */
export function memberColumns(region: Region, unit: string | null): Column<MemberRow>[] {
  const u = unit ?? (region === "IN" ? "₹ crore" : "$ million");
  const cap = region === "IN" ? "₹ crore" : "$ million";
  const cell = () => null;
  return [
    { key: "c", header: "Company", cell, csv: (x) => x.co.name },
    { key: "s", header: "Symbol", cell, csv: (x) => x.co.ticker },
    { key: "l", header: "Layer", cell, csv: (x) => x.layer },
    { key: "i", header: "Industry", cell, csv: (x) => x.co.industry || null },
    { key: "m", header: `Market value (${cap})`, cell, csv: (x) => x.fig?.cap ?? x.co.cap ?? null },
    { key: "rev", header: `Revenue (${u})`, cell, csv: (x) => x.fig?.revenue ?? null },
    { key: "e", header: "EBITDA margin (%)", cell, csv: (x) => x.fig?.ebitda ?? null },
    { key: "n", header: "Net margin (%)", cell, csv: (x) => x.fig?.net ?? null },
    { key: "roce", header: "ROCE (%)", cell, csv: (x) => x.fig?.roce ?? null },
    { key: "y", header: "Year of the figures", cell, csv: (x) => x.fig?.year ?? null },
    { key: "b", header: "In the theme by", cell, csv: (x) => memberBy(x.co) },
    { key: "w", header: "What it does, in its own words", cell, csv: (x) => ownWords(x.co.what, x.co.name) || null },
  ];
}

/** EXPORT (owner, 4 Nov: "you forgot to put an export PDF or slides option in themes"): the theme as slides, PDF or PowerPoint, made by the
 * deep dive's deck builder and counted against the same monthly decks; and every company as a CSV. Each file goes through lib/share.ts. */
export function ThemeDownloads({ r, dive, region, theme }: { r: SectorAI; dive: Dive | null; region: Region; theme: string }) {
  const { fail, refreshMe } = useApp();
  const [making, setMaking] = useState<"pptx" | "pdf" | null>(null);
  const [preparing, setPreparing] = useState<string | null>(null);
  const rows = useMemo(() => memberRows(r, dive), [r, dive]);
  const deck = async (format: "pptx" | "pdf") => {
    setMaking(format);
    try {
      // R21: while the theme's AI map is being written the server answers "preparing"; the kit's bar shows and the page asks again
      const blob = await deckWhenReady(() => themeApi.deck(region, theme, format), { onWait: setPreparing });
      download(blob, deckFileName(`${theme} theme (${REGION_NAME[region]})`, format));
      void refreshMe();                               // the deck count in Account
    } catch (e) { fail(e); } finally { setMaking(null); setPreparing(null); }
  };
  return (
    <div className="k-row" role="group" aria-label="Download this theme" data-testid="theme-downloads">
      <span className="k-small k-muted">Download</span>
      <button type="button" className="btn quiet sm" disabled={!!making || !dive} onClick={() => deck("pdf")} title="The whole theme as slides in a PDF: the chain and each layer, every company with its figures, the tailwinds and risks with their sources, the news and the theme in numbers"><Download size={16} />{making === "pdf" ? "Making the PDF…" : "Slides (PDF)"}</button>
      <button type="button" className="btn quiet sm" disabled={!!making || !dive} onClick={() => deck("pptx")} title="The same slides as PowerPoint"><Download size={16} />{making === "pptx" ? "Making the deck…" : "Slides (PowerPoint)"}</button>
      {preparing && <Working small label={preparing} />}
      {rows.length > 0 && <CsvButton name={`theme ${theme} ${region} companies`} label="every company in this theme" columns={memberColumns(region, dive?.unit ?? null)} rows={rows} text="CSV" />}
    </div>
  );
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

const MedianCell = ({ c }: { c: { text: string; base: string } }) => <><b>{c.text}</b>{c.base && <span className="k-sub-line k-muted">{c.base}</span>}</>;

function layerColumns(r: Region, wide: Set<string>, wideOut: boolean): Column<LayerLine>[] {
  const f = (k: "ebitda" | "net" | "roce") => (x: LayerLine) => {
    if (x.kind === "company") return <>{pc(x.row![k])}{k === "net" && x.row!.one_off && x.row![k] != null ? " †" : ""}</>;
    if (x.kind === "median") return <MedianCell c={medCell(x.stats?.[k], x.of ?? 0)} />;
    return (x.stats?.[k]?.n ?? 0) >= MIN_BASE ? span(x.stats?.[k]) : "";
  };
  // LIVE6-001: a company left out of the layer's calculations says so on its row, with why, as the deck's rows do
  const mark = (row: DiveRow) => {
    const c = calcOf(row);
    if (!c.in) return <span className="k-sub-line" data-testid="calc-out">Left out of the layer's calculations: {CALC_WORDS[c.why] ?? c.why}</span>;
    if (wideOut && wide.has(row.symbol)) return <span className="k-sub-line" data-testid="calc-out">Left out of the medians: its figures are the whole company's</span>;
    return null;
  };
  return [
    { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x) => x.kind !== "company" ? <b>{x.label}</b>
      : <><Name r={r} sym={x.row!.symbol} name={x.row!.name} wide={wide.has(x.row!.symbol)} />{mark(x.row!)}{ownWords(x.row!.what, x.row!.name) ? <span className="k-sub-line">In its own words: “{ownWords(x.row!.what, x.row!.name)}”</span> : <span className="k-sub-line k-muted">{NO_WORDS}</span>}</> },
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
  const listed = layer.listed ?? layer.companies.length, inCalc = layer.n ?? layer.companies.filter((c) => calcOf(c).in).length;
  return (
    <Card id={`layer-${i}`} label={`Layer ${i + 1}: ${layer.layer}`}>
      <CardHead title={<><span className="k-muted">Layer {i + 1} · </span>{layer.layer}</>} />
      {layer.description && <p className="k-small">{layer.description} <span className="k-muted">(Written by AI from general knowledge, with no figures.)</span></p>}
      {layer.official && <p className="k-small k-muted">{layer.basis === "list" ? "The theme's own named companies that the layers above don't place." : "Companies the exchange classifies under this industry that the layers above don't place."}</p>}
      {lines.length === 0
        ? <p className="k-small">No listed company is shown for this layer: none of the companies the map named has a description that shows it does this work.</p>
        : <>
          <p className="k-small k-muted" data-testid="layer-count">{listed} compan{listed === 1 ? "y" : "ies"} listed, {inCalc} in the layer's calculations{inCalc < MIN_BASE ? `: a median needs ${MIN_BASE}, so each company's own figures are shown` : ""}.</p>
          <Fold rows={lines.filter((x) => x.kind === "company")} n={10} what="companies">{(shown) => (
            <DataTable label={`${layer.layer}: companies, revenue and margins`} columns={layerColumns(region, wide, layer.left_out > 0)} rows={[...shown, ...lines.filter((x) => x.kind !== "company")]} rowKey={(x) => x.key} rowAttrs={(x) => ({ "data-kind": x.kind })} />
          )}</Fold>
          {layer.line && <p className="k-small">{layer.line}</p>}
          {wide.size > 0 && <p className="k-note">"Whole-company figures": the company runs other businesses too, so its figures are the whole company's, not this layer's own.</p>}
          {layer.companies.some((c) => c.one_off && c.net != null) && <p className="k-note">†: net margin above the EBITDA margin (a one-off gain in the year), left out of the net margin's median.</p>}
        </>}
      {hist && hist.years.length >= 2 && hist.n >= MIN_BASE && (
        <>
        <h3 className="k-sub">Margins by year, the same {hist.n} companies added together</h3>
        <DataTable label={`${layer.layer}: margin by year`} columns={[
          { key: "y", header: "Year", rowHeader: true, cell: (h: { y: string; e: number | null; n: number | null }) => h.y },
          { key: "e", header: "EBITDA margin", numeric: true, info: `The ${hist.n} companies that report every year here, added together.`, cell: (h) => pc(h.e) },
          { key: "n", header: "Net margin", numeric: true, cell: (h) => pc(h.n) },
        ]} rows={hist.years.map((y, k) => ({ y, e: hist.ebitda[k], n: hist.net[k] }))} rowKey={(h) => h.y} />
        </>
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
    { key: "w", header: "What it does here, in its own words", wrap: true, cell: (x) => { const w = ownWords(x.what, x.name); return w ? <>“{w}”</> : <span className="k-muted">{NO_WORDS}</span>; } },
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
            : <Fold rows={s.companies} n={10} what="companies">{(shown) => <DataTable label={`${s.name}: listed companies`} columns={cols} rows={shown} rowKey={(x) => x.symbol} />}</Fold>}
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
      : <Badge tone="plain" dot={false}>General background</Badge>) },
  ];
  return (
    <Card id="theme-claims" label="Tailwinds and risks">
      <CardHead title="Tailwinds and risks" info="Checked: a headline dated within the last 18 months shows the programme or event is still current. A claim a dated headline showed had ended or been replaced is left out. General background: written by AI from general knowledge, with no figures, and no dated source was found for it." />
      <DataTable label="Tailwinds and risks, with the dated headline that supports each" columns={cols} rows={rows} rowKey={(x) => x.key} />
      {/* said once under the table, not under every row (LIVE3-017) */}
      {rows.some((x) => !(x.status === "current" && x.source)) && <p className="k-note">General background: no dated headline was found that shows it is still current.</p>}
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
        : <Fold rows={items.filter((x) => x.headline && x.source)} n={10} what="headlines">{(shown) => <DataTable label="Latest dated headlines and filings for the theme" columns={cols} rows={shown} rowKey={(x) => `${x.at}${x.headline}`} empty="No recent headlines or filings were found for this theme's companies." />}</Fold>}
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
        <h3 className="k-sub">The biggest companies by market value</h3>
        <DataTable label="The theme's biggest companies by market value" columns={[
          { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x: (typeof s.size.biggest)[number]) => <Name r={r} sym={x.symbol} name={x.name} wide={dive.company_wide.includes(x.symbol)} /> },
          { key: "m", header: "Market value", numeric: true, cell: (x) => amount(x.cap, r) },
          { key: "s", header: "Share of the theme", numeric: true, cell: (x) => pc(x.share) },
        ]} rows={s.size.biggest} rowKey={(x) => x.symbol} foot={{ c: `All ${s.size.companies} listed companies (${s.size.with_value} with a market value)`, m: amount(s.size.total_cap, r), s: "100.0%" }} />
        {s.size.top3_share != null && <p className="k-note">The three largest make up {pc(s.size.top3_share)} of the theme's market value.</p>}
      </Card>

      <Card id="numbers-growth" label="Growth and profitability">
        <CardHead title="Growth and profitability" info="Together: the companies' figures added up, for the companies that report both ends of the period (growth a year for three years). Median: the middle company's own rate. Companies that run other businesses too are left out." />
        <h3 className="k-sub">Revenue and profit growth</h3>
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
        <h3 className="k-sub">The theme's medians against all listed companies</h3>
        <DataTable label="Margins and returns: the theme against all listed companies" columns={[
          { key: "m", header: "Median", rowHeader: true, cell: (x: KV) => x.measure }, { key: "a", header: "Theme", numeric: true, cell: (x) => x.a }, { key: "b", header: "Companies", numeric: true, cell: (x) => x.b },
          { key: "c", header: "All listed", numeric: true, info: "The middle company among all those StratLab holds figures for.", cell: (x) => x.c },
        ]} rowKey={(x) => x.key} rows={said([
          { key: "e", measure: "EBITDA margin", a: med(s.medians.ebitda), b: s.medians.ebitda?.n ?? dash, c: med(s.market.opm) },
          { key: "n", measure: "Net margin", a: med(s.medians.net), b: s.medians.net?.n ?? dash, c: med(s.market.net_margin) },
          { key: "r", measure: "ROCE", a: med(s.medians.roce), b: s.medians.roce?.n ?? dash, c: med(s.market.roce) },
          { key: "g", measure: "Revenue growth, 3 years a year", a: med(gm.median.revenue_3y, (v) => pct(v)), b: gm.median.revenue_3y?.n ?? dash, c: med(s.market.sales_cagr_3y, (v) => pct(v)) },
        ])} />
      </Card>

      <Card id="numbers-valuation" label="Valuation">
        <CardHead title="Valuation" info="P/E is the price over the last four reported quarters' earnings per share. P/B is the price over book value per share. EV/EBITDA is market value plus debt less cash, over the latest year's EBITDA. Each is left out for a company where a figure it needs is missing, and for a loss." />
        <DataTable label="Valuation: the theme against all listed companies" columns={[
          { key: "m", header: "Measure", rowHeader: true, cell: (x: KV) => x.measure }, { key: "a", header: "Theme median", numeric: true, cell: (x) => x.a }, { key: "b", header: "Range", numeric: true, cell: (x) => x.b },
          { key: "c", header: "Companies", numeric: true, cell: (x) => x.c }, { key: "d", header: "All listed, median", numeric: true, cell: (x) => x.d },
        ]} rowKey={(x) => x.key} rows={said([
          { key: "pe", measure: "P/E", a: med(val.pe, (v) => times(v)), b: span(val.pe, (v) => times(v)), c: val.pe?.n ?? dash, d: med(val.market_pe, (v) => times(v)) },
          { key: "pb", measure: "P/B", a: med(val.pb, (v) => times(v)), b: span(val.pb, (v) => times(v)), c: val.pb?.n ?? dash, d: med(val.market_pb, (v) => times(v)) },
          { key: "ev", measure: "EV/EBITDA", a: med(val.ev_ebitda, (v) => times(v)), b: span(val.ev_ebitda, (v) => times(v)), c: val.ev_ebitda?.n ?? dash, d: dash },
        ])} />
        {medianPe != null && marketPe != null && <p className="k-small">The theme's median P/E is {times(medianPe)} against {times(marketPe)} for all {val.market_n.toLocaleString("en-IN")} listed companies with one.</p>}
        {val.ev_missing > 0 && <p className="k-note">EV/EBITDA is n/a for {val.ev_missing} compan{val.ev_missing === 1 ? "y" : "ies"} where debt, cash or EBITDA isn't stored. The all-listed comparison is not worked out for it.</p>}
        {val.history.length >= 2
          ? <><h3 className="k-sub">The theme's median P/E, week by week</h3><Fold rows={val.history.slice(-26).reverse()} n={8} what="weeks">{(shown) => <DataTable label="The theme's median P/E over time" columns={[
            { key: "d", header: "Week of", rowHeader: true, cell: (h: (typeof val.history)[number]) => fmtDate(h.d) }, { key: "p", header: "Median P/E", numeric: true, cell: (h) => times(h.pe) }, { key: "n", header: "Companies", numeric: true, cell: (h) => h.n },
          ]} rows={shown} rowKey={(h) => h.d} />}</Fold></>
          : <p className="k-note">The theme's own P/E history builds forward from this page: it keeps the median once a week from now.</p>}
      </Card>

      <Card id="numbers-quarter" label="The latest quarter">
        <CardHead title="The latest quarter against a year earlier" info="Each company's latest reported quarter against the same quarter a year before, as its company page gives it. It compares a company with its own past, not with anyone's estimate." />
        <Fold rows={s.quarter.companies} n={12} what="companies">{(shownQ) => <DataTable label="Latest reported quarter against the same quarter a year before" columns={[
          { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x: (typeof s.quarter.companies)[number]) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "q", header: "Quarter", cell: (x) => x.of }, { key: "s", header: "Revenue", numeric: true, cell: (x) => chg(x.sales) }, { key: "p", header: "Net profit", numeric: true, cell: (x) => chg(x.profit) },
        ]} rows={shownQ} rowKey={(x) => x.symbol} empty="No company in the theme has a latest quarter stored against a year before."
          foot={s.quarter.companies.length ? { c: `${s.quarter.sales_up} up, ${s.quarter.sales_down} down on revenue; ${s.quarter.profit_up} up, ${s.quarter.profit_down} down on profit`, q: "Median", s: chg(s.quarter.sales?.median), p: chg(s.quarter.profit?.median) } : undefined} />}</Fold>
      </Card>

      <Card id="numbers-balance" label="Balance sheet and cash">
        <CardHead title="Balance sheet and cash" info="Debt to equity is borrowings over shareholders' equity (not for lenders). Cash from operations over profit is the latest year's." />
        <KVTable t={kv("Balance sheet and cash of the theme's companies", ["Median", "Range", "Companies"], said([
          { key: "de", measure: "Debt to equity", a: med(bal.debt_equity, (v) => `${ratio(v)}x`), b: span(bal.debt_equity, (v) => `${ratio(v)}x`), c: bal.with_debt_equity },
          { key: "ic", measure: "Interest cover (profit before interest and tax over interest)", a: med(bal.interest_cover, (v) => times(v)), b: span(bal.interest_cover, (v) => times(v)), c: bal.interest_cover?.n ?? dash },
          { key: "cfo", measure: "Cash from operations as a multiple of net profit", a: med(bal.cfo_to_profit, (v) => times(v, 2)), b: span(bal.cfo_to_profit, (v) => times(v, 2)), c: bal.cfo_n || dash },
        ]))} />
        <p className="k-note">{bal.with_debt_equity > 0 ? `${bal.above_1} of ${bal.with_debt_equity} companies have borrowings above their equity. ` : ""}{bal.interest_cover ? `${bal.cover_under_2} of ${bal.interest_cover.n} cover their interest less than twice. ` : ""}A company with no interest cost has no interest cover.</p>
      </Card>

      <PriceCards dive={dive} prices={prices} busy={pricesBusy} />

      <Card id="numbers-ownership" label="Ownership">
        <CardHead title="Ownership" info={r === "IN" ? "From each company's latest shareholding filing with the exchange: the promoter group's named holders added up, and the funds, insurers and foreign investors the filing names above 1%. Change is against the quarter before, in percentage points." : "Insider purchases filed in the last 90 days."} />
        {/* promoters are an Indian filing's group: a US theme has no promoter column (LIVE6-017) */}
        {r === "IN" && <>
        <h3 className="k-sub">Promoter and named institutional holdings</h3>
        <Fold rows={own.holdings} n={12} what="companies">{(shownH) => <DataTable label="Promoter and named institutional holdings" columns={[
          { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x: (typeof own.holdings)[number]) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "p", header: "Promoters", numeric: true, cell: (x) => pc(x.promoter) }, { key: "pc", header: "Change", numeric: true, cell: (x) => <Signed value={x.promoter_change}>{points(x.promoter_change)}</Signed> },
          { key: "i", header: "Named institutions", numeric: true, cell: (x) => pc(x.institutions) }, { key: "ic", header: "Change", numeric: true, cell: (x) => <Signed value={x.institutions_change}>{points(x.institutions_change)}</Signed> },
          { key: "q", header: "Quarter", cell: (x) => x.quarter },
        ]} rows={shownH} rowKey={(x) => x.symbol} empty="No shareholding filings are stored for these companies yet." />}</Fold>
        </>}
        <h3 className="k-sub">{r === "IN" ? "Promoter and insider purchases and pledges, last 90 days" : "Insider purchases, last 90 days"}</h3>
        <DataTable label="Promoter and insider purchases, last 90 days, and pledges" columns={[
          { key: "k", header: "What", rowHeader: true, cell: (x: { key: string; what: string; name: string; sym: string; at: string; url?: string | null }) => x.what },
          { key: "c", header: "Company", wrap: true, cell: (x) => <Name r={r} sym={x.sym} name={x.name} /> }, { key: "d", header: "Filed", cell: (x) => fmtDate(x.at) },
          { key: "f", header: "Filing", cell: (x) => (x.url ? <a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">Open ↗</a> : dash) },
        ]} rows={[
          ...own.insider_buys.map((b) => ({ key: `b${b.symbol}`, what: r === "IN" ? "Promoter or insider bought" : "Insider bought", name: b.name, sym: b.symbol, at: b.at, url: null as string | null })),
          ...own.pledges.map((p, i) => ({ key: `p${i}${p.symbol}`, what: p.label, name: p.name, sym: p.symbol, at: p.at, url: p.url ?? null })),
        ]} rowKey={(x) => x.key} empty="No promoter or insider purchases and no pledge filings in the last 90 days." />
        {r === "IN" && own.holdings.length > 0 && <p className="k-note">Promoters' stake rose at {own.promoter_up} and fell at {own.promoter_down} of the {own.holdings.length} companies with a filing stored.</p>}
      </Card>

      <Card id="numbers-events" label="Events">
        <CardHead title="Events" info="Results dates as the companies announced them, results filings with the numbers as filed, ex-dates of dividends and other corporate actions, and red-flag filings of the last 90 days." />
        <h3 className="k-sub">Results due in the next four weeks</h3>
        <DataTable label="Results due in the next four weeks" columns={[
          { key: "d", header: "Date", rowHeader: true, cell: (x: (typeof ev.results_due)[number]) => fmtDate(x.date) }, { key: "c", header: "Company", wrap: true, cell: (x) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "p", header: "Purpose", wrap: true, cell: (x) => x.purpose ?? dash },
        ]} rows={ev.results_due} rowKey={(x) => x.symbol + x.date} empty="No results dates are announced for these companies in the next four weeks." />
        <h3 className="k-sub">Results filed in the last 30 days</h3>
        <DataTable label="Results filed in the last 30 days" columns={[
          { key: "d", header: "Filed", rowHeader: true, cell: (x: (typeof ev.results_filed)[number]) => fmtDate(x.date) }, { key: "c", header: "Company", wrap: true, cell: (x) => <Name r={r} sym={x.symbol} name={x.name} /> },
          ...(ev.results_filed.some((x) => x.numbers.length) ? [{ key: "n", header: "Numbers as filed", wrap: true, cell: (x: (typeof ev.results_filed)[number]) => (x.numbers.length ? x.numbers.map((n) => `${n.label} ${n.value}`).join(" · ") : dash) }] : []),
          { key: "f", header: "Filing", cell: (x) => (x.url ? <a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">Open ↗</a> : dash) },
        ]} rows={ev.results_filed} rowKey={(x) => x.symbol + x.date} empty="No results were filed by these companies in the last 30 days." />
        <h3 className="k-sub">Dividends, splits and other actions, 30 days back to 60 ahead</h3>
        <DataTable label="Dividends, splits and other corporate actions, from 30 days ago to 60 days ahead" columns={[
          { key: "d", header: "Ex-date", rowHeader: true, cell: (x: (typeof ev.actions)[number]) => fmtDate(x.date) }, { key: "c", header: "Company", wrap: true, cell: (x) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "a", header: "Action", wrap: true, cell: (x) => (x.text ? `${x.label}: ${x.text}` : x.label) },
        ]} rows={ev.actions} rowKey={(x) => x.symbol + x.date + x.label} empty="No dividends, splits or other corporate actions in that window." />
        <h3 className="k-sub">Red-flag filings, last 90 days</h3>
        <DataTable label="Red-flag filings, last 90 days" columns={[
          { key: "d", header: "Filed", rowHeader: true, cell: (x: (typeof own.red_flags)[number]) => fmtDate(x.at) }, { key: "c", header: "Company", wrap: true, cell: (x) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "l", header: "Kind", wrap: true, cell: (x) => x.label }, { key: "f", header: "Filing", cell: (x) => (x.url ? <a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">Open ↗</a> : dash) },
        ]} rows={own.red_flags} rowKey={(x) => x.symbol + x.at + x.label} empty="No red-flag filings for these companies in the last 90 days." />
      </Card>

      <Card id="numbers-management" label="Management">
        <CardHead title="Management report cards" info="What management said it would deliver on earnings calls, set against the reported years. Only annual targets are settled here; each company's own page has the rest." />
        <Fold rows={mg.companies} n={12} what="companies">{(shownM) => <DataTable label="Management targets met and missed" columns={[
          { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (x: (typeof mg.companies)[number]) => <Name r={r} sym={x.symbol} name={x.name} /> },
          { key: "m", header: "Targets met", numeric: true, cell: (x) => x.met }, { key: "x", header: "Missed", numeric: true, cell: (x) => x.missed },
        ]} rows={shownM} rowKey={(x) => x.symbol} foot={{ c: `${mg.with_card} compan${mg.with_card === 1 ? "y" : "ies"} with a stored report card`, m: mg.met, x: mg.missed }}
          empty="No stored management report cards for these companies yet." />}</Fold>
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
      <CardHead title="Price" info="Price change over calendar periods to the last close: one month is from the close on or before the same day a month earlier. Median: the middle company. Equal-weighted: the companies' weekly changes averaged, so each counts the same. Stage and Supertrend are from each company's stored page." />
      <h3 className="k-sub">Price change against {prices?.benchmark || "the market's index"}</h3>
      <DataTable label="The theme's price change against the market's index" columns={[
        { key: "m", header: prices?.returns_to ? `Over, to ${fmtDate(prices.returns_to)}` : "Over", rowHeader: true, cell: (x: KV) => x.measure }, { key: "a", header: "Median company", numeric: true, cell: (x) => x.a },
        { key: "b", header: "Theme, equal-weighted", numeric: true, cell: (x) => x.b }, { key: "c", header: prices?.benchmark || "Index", numeric: true, cell: (x) => x.c },
        { key: "d", header: "Companies", numeric: true, cell: (x) => x.d },
      ]} rows={retRows} rowKey={(x) => x.key} empty={busy ? "Reading prices…" : "No prices yet."} />
      {busy ? <Working small label="Reading the companies' latest prices…" />
        : prices && prices.pending > 0 ? <p className="k-note">{prices.pending.toLocaleString("en-IN")} {prices.pending === 1 ? "company's price isn't" : "companies' prices aren't"} read yet.</p> : null}
      {prices?.line && (
        <>
          <h3 className="k-sub">The theme against {prices.benchmark}, weekly, rebased to 100</h3>
          <LineChart ariaLabel={`The theme's equal-weighted price line and relative strength against ${prices.benchmark}`} height={220} format={(v) => v.toFixed(1)} labels={prices.line.weeks.map((w) => fmtDate(w))} times={prices.line.weeks} ranges={false}
            lines={[{ label: "Theme", color: "var(--blue)", values: prices.line.theme }, { label: prices.benchmark, color: "var(--muted)", values: prices.line.bench },
              { label: "Relative strength (theme over index)", short: "Rel. strength", color: "var(--orange)", values: prices.line.rs, dash: "4 3" }]} legend baseline={100} />
        </>
      )}
      <h3 className="k-sub">Breadth inside the theme</h3>
      <DataTable label="Breadth inside the theme" columns={[
        { key: "m", header: "Companies that are", rowHeader: true, cell: (x: KV) => x.measure }, { key: "a", header: "Count", numeric: true, cell: (x) => x.a }, { key: "b", header: "Share", numeric: true, cell: (x) => x.b },
      ]} rows={said(rows)} rowKey={(x) => x.key} empty="No company has a stored price stage yet." />
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
  const phone = usePhone();
  return (
    <Card id="numbers-leaders" label="Leaders and laggards">
      <CardHead title="Every company, sortable" info="Click a column to sort. Sorted by the figure you pick, not ranked: nothing here says which to own."
        actions={phone ? <><Select label="Sort by" small value={sort.key} onChange={(v) => setSort({ key: v, desc: v !== "name" })} options={cols.filter((c) => c.sortable).map((c) => ({ value: c.key, label: typeof c.header === "string" ? c.header : c.key }))} />
          <button type="button" className="btn quiet sm" onClick={() => setSort((x) => ({ ...x, desc: !x.desc }))}>{sort.desc ? "High to low" : "Low to high"}</button></> : undefined} />
      <Fold rows={sorted} n={20} what="companies">{(shown) => <DataTable label="Every company in the theme with its figures" columns={cols} rows={shown} rowKey={(x) => x.symbol} sort={{ ...sort, onSort }} />}</Fold>
    </Card>
  );
}
