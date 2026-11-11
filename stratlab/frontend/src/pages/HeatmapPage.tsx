import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { bigMoney, fmtDate, pct, price } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { researchApi, useRegion, type Region } from "../lib/research";
import { PERIODS, PERIOD_LABEL, PERIOD_SHORT, closesNote, colorValue, isPeriod, matches, type ColorBy, type GroupBy, type HeatView, type Period, type Placed, type SizeBy, type Tile } from "../lib/heatmap";
import { Treemap, TreemapLegend } from "../components/chart/Treemap";
import { Card, CardHead, ChipBar, DataTable, EmptyState, ErrorState, Field, FieldGroup, PageHeader, Seg, Select, Signed, Working, type Column } from "../components/kit";

/* /invest/heatmap (L4): a market as one picture. Every company of a group is a tile, sized by its market value (or equally, or by the
 * value traded) and coloured by its change over a period (or that change against the index, or its volume against its average),
 * grouped by sector or industry. With ?theme=<a theme>, the tiles are that theme's companies, grouped by the layers of its chain.
 * The figures are the daily closes the app already stores (one read; the settings below change the picture without another).
 * Facts only: a tile says what the price did, never what to do about it. */

const REGION_NAME: Record<Region, string> = { IN: "India", US: "United States" };
const COLORS: { value: ColorBy; label: string }[] = [{ value: "change", label: "Change" }, { value: "vs", label: "Vs index" }, { value: "volume", label: "Volume" }];
const SIZES: { value: SizeBy; label: string }[] = [{ value: "cap", label: "Market value" }, { value: "equal", label: "Equal" }, { value: "traded", label: "Value traded" }];
// the smallest market value offered, in the market's own unit (₹ crore, $ million)
const MIN_CAPS: Record<Region, { value: string; label: string }[]> = {
  IN: [{ value: "", label: "Any size" }, { value: "1000", label: "₹1,000 cr and up" }, { value: "5000", label: "₹5,000 cr and up" }, { value: "20000", label: "₹20,000 cr and up" }, { value: "100000", label: "₹1 lakh cr and up" }],
  US: [{ value: "", label: "Any size" }, { value: "2000", label: "$2B and up" }, { value: "10000", label: "$10B and up" }, { value: "50000", label: "$50B and up" }, { value: "200000", label: "$200B and up" }],
};
const UNIT: Record<Region, number> = { IN: 1e7, US: 1e6 };
const CCY: Record<Region, string> = { IN: "INR", US: "USD" };
const pick = <T extends string>(v: string | null, all: readonly { value: T }[], d: T): T => (all.some((o) => o.value === v) ? (v as T) : d);

/** A colour figure as text: "+1.2%", "+1.2 pts" against the index, "1.8×" of the average volume. */
export function figureText(v: number | null, by: ColorBy): string {
  if (v == null) return "–";
  if (by === "volume") return `${v.toFixed(1)}×`;
  return by === "vs" ? pct(v, 1).replace("%", " pts") : pct(v, 1);
}

type ThemeCos = { name: string; layers: Map<string, string>; symbols: string[] };

export function HeatmapPage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const theme = (params.get("theme") ?? "").trim();
  const universe = params.get("u") ?? "";
  const minCap = MIN_CAPS[region].some((o) => o.value === params.get("min")) ? params.get("min")! : "";
  const period: Period = isPeriod(params.get("p")) ? (params.get("p") as Period) : "1d";
  const color = pick(params.get("c"), COLORS, "change");
  const size = pick(params.get("s"), SIZES, "cap");
  const groups: { value: GroupBy; label: string }[] = theme
    ? [{ value: "layer", label: "Layer" }, { value: "sector", label: "Sector" }, { value: "none", label: "None" }]
    : [{ value: "sector", label: "Sector" }, { value: "industry", label: "Industry" }, { value: "none", label: "None" }];
  const group = pick(params.get("g"), groups, groups[0].value);
  const table = params.get("view") === "table";
  const set = (changes: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) { if (v) p.set(k, v); else p.delete(k); }
    setParams(p, { replace: true });
  };

  const [view, setView] = useState<HeatView | null>(null);
  const [cos, setCos] = useState<ThemeCos | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [again, setAgain] = useState(0);
  const [opts, setOpts] = useState(false);          // a phone's settings folded under "Options" (LIVE6-019)
  const [query, setQuery] = useState("");
  const [leftOut, setLeftOut] = useState(0);
  const [sort, setSort] = useState<{ key: string; desc: boolean }>({ key: "cap", desc: true });
  const seq = useRef(0);
  useEffect(() => {
    const mine = ++seq.current;
    setBusy(true); setError(null);
    setView((v) => (v && v.market === region ? v : null));      // another market's tiles are not shown in this one's units
    const load = async (): Promise<[HeatView, ThemeCos | null]> => {
      if (!theme) {
        const q = new URLSearchParams({ market: region });
        if (universe) q.set("universe", universe);
        if (minCap) q.set("min_cap", minCap);
        return [await api<HeatView>(`/invest/heatmap?${q}`), null];
      }
      // a theme: its companies from the theme's own map (each in the first layer that names it), then their tiles
      const m = await researchApi.sector(region, theme);
      const layers = new Map<string, string>();
      for (const v of m.value_chain ?? []) for (const c of v.companies ?? []) if (!layers.has(c.ticker)) layers.set(c.ticker, v.layer || "Other");
      for (const s of m.sub_themes ?? []) for (const c of s.companies ?? []) if (!layers.has(c.ticker)) layers.set(c.ticker, "Named in a sub-theme only");
      const symbols = [...layers.keys()].slice(0, 300);
      const t: ThemeCos = { name: m.sector || theme, layers, symbols };
      if (!symbols.length) return [{ market: region, universe: null, universe_name: null, universes: [], periods: [...PERIODS], as_of: null, cap_unit: "", index: { name: "", r: null }, pending: false, min_cap: null, tiles: [], members: 0, with_prices: 0, matching: 0, shown: 0 }, t];
      const q = new URLSearchParams({ market: region, symbols: symbols.join(",") });
      return [await api<HeatView>(`/invest/heatmap?${q}`), t];
    };
    load().then(([v, t]) => { if (mine === seq.current) { setView(v); setCos(t); } })
      .catch((e) => {
        if (mine !== seq.current) return;
        // a group from an old link that this market doesn't have: the market's own first group
        if (e instanceof ApiError && e.status === 404 && universe) { set({ u: null }); return; }
        setError(e instanceof ApiError ? e.message : "The heatmap couldn't be read."); setView(null);
      })
      .finally(() => { if (mine === seq.current) setBusy(false); });
  }, [region, universe, minCap, theme, again]);

  const tiles: Tile[] = useMemo(() => (view?.tiles ?? []).map((t) => (cos ? { ...t, layer: cos.layers.get(t.s) ?? "Other" } : t)), [view, cos]);
  const index = view?.index.r ?? null;
  const pi = PERIODS.indexOf(period);
  const noIndex = color === "vs" && (index?.[pi] == null);
  const counts = useMemo(() => {
    let up = 0, down = 0, flat = 0;
    for (const t of tiles) { const v = t.r[pi]; if (v == null) continue; if (v > 0) up++; else if (v < 0) down++; else flat++; }
    return { up, down, flat };
  }, [tiles, pi]);
  const ccy = CCY[region];
  const capText = (v: number | null) => (v == null ? "–" : bigMoney(v * UNIT[region], ccy));
  const href = (t: Tile) => `/research/${region}/${encodeURIComponent(t.s)}`;
  const name = cos ? cos.name : view?.universe_name ?? "";
  const colorTitle = color === "change" ? `Change, ${PERIOD_LABEL[period].toLowerCase()}` : color === "vs" ? `Change less the index's, ${PERIOD_LABEL[period].toLowerCase()}` : "Volume against its 20-day average";
  const tip = (p: Placed) => {
    const t = p.tile, chg = t.r[pi], vs = colorValue(t, "vs", period, index);
    return (
      <>
        <div className="hm-tip-name">{t.n}</div>
        <div className="hm-tip-sub">{t.s}{t.layer ? ` · ${t.layer}` : t.sec ? ` · ${t.sec}` : ""}</div>
        <dl>
          <dt>Last close</dt><dd>{t.px == null ? "–" : price(t.px, ccy)}</dd>
          <dt>{PERIOD_LABEL[period]}</dt><dd><Signed value={chg} fmt={(v) => pct(v, 2)} /></dd>
          {vs != null && <><dt>Less the index</dt><dd><Signed value={vs}>{figureText(vs, "vs")}</Signed></dd></>}
          <dt>Market value</dt><dd>{capText(t.cap)}</dd>
          <dt>Volume vs average</dt><dd>{figureText(t.vx, "volume")}</dd>
        </dl>
      </>
    );
  };
  const shown = useMemo(() => {
    const val = (t: Tile): number | null => (sort.key === "cap" ? t.cap : sort.key === "vol" ? t.vx : sort.key === "vs" ? colorValue(t, "vs", period, index) : t.r[pi]);
    const rows = tiles.filter((t) => matches(t, query));
    return rows.sort((a, b) => {
      const x = val(a), y = val(b);
      if (x == null || y == null) return x == null ? (y == null ? a.s.localeCompare(b.s) : 1) : -1;
      return (sort.desc ? y - x : x - y) || a.s.localeCompare(b.s);
    });
  }, [tiles, query, sort, period, index, pi]);
  const cols: Column<Tile>[] = [
    { key: "n", header: "Company", rowHeader: true, wrap: true, cell: (t) => <Link className="link" to={href(t)}><b>{t.s}</b> <span className="k-muted">{t.n}</span></Link> },
    { key: "g", header: cos ? "Layer" : "Sector", wrap: true, narrow: false, cell: (t) => (cos ? t.layer : t.sec) ?? "–" },
    { key: "px", header: "Last close", numeric: true, cell: (t) => (t.px == null ? "–" : price(t.px, ccy)) },
    { key: "chg", header: PERIOD_LABEL[period], numeric: true, sortable: true, brief: true, cell: (t) => <Signed value={t.r[pi]} fmt={(v) => pct(v, 2)} /> },
    { key: "vs", header: "Less the index", numeric: true, sortable: true, cell: (t) => { const v = colorValue(t, "vs", period, index); return <Signed value={v}>{figureText(v, "vs")}</Signed>; } },
    { key: "cap", header: "Market value", numeric: true, sortable: true, cell: (t) => capText(t.cap) },
    { key: "vol", header: "Volume vs average", numeric: true, sortable: true, tight: false, cell: (t) => figureText(t.vx, "volume") },
  ];
  const asOf = view?.as_of ? fmtDate(view.as_of) : null;
  const cut = !!view && !cos && view.matching > view.shown;
  return (
    <div className="k-page hm-page">
      <PageHeader eyebrow={eyebrowOf("/invest/heatmap")} title={cos ? `Heatmap: ${cos.name}` : "Heatmap"}
        lede={theme ? "The theme's companies as tiles, grouped by the layers of its chain: each tile's size is the company's market value and its colour is what the price did. Facts, not advice."
          : "A market as one picture: each tile is a company, its size the market value and its colour what the price did over the period you pick. Facts, not advice."} />
      <Card label="Heatmap settings">
        {/* LIVE6-019: on a phone the settings filled the first screen and the map began about 1,150px down. There they fold into one
            row: what is picked, in words, and Options to open the rest; the period stays out as the one setting changed most */}
        <div className="hm-fold" data-testid="hm-fold">
          <span className="hm-fold-sum">{[REGION_NAME[region], !theme && view?.universe_name, !theme && minCap && MIN_CAPS[region].find((o) => o.value === minCap)?.label,
            COLORS.find((c) => c.value === color)!.label, SIZES.find((x) => x.value === size)!.label, groups.find((g) => g.value === group)?.label].filter(Boolean).join(" · ")}</span>
          <button type="button" className="btn quiet sm" aria-expanded={opts} aria-controls="hm-controls" onClick={() => setOpts((o) => !o)}>{opts ? "Done" : "Options"}</button>
        </div>
        <div id="hm-controls" className={`hm-controls${opts ? "" : " folded"}`} data-testid="hm-controls">
          <FieldGroup label="Market"><Seg label="Market" value={region} onChange={(v) => { setRegion(v as Region); set({ region: v, u: null, min: null }); }} options={[{ value: "IN", label: "₹ India" }, { value: "US", label: "$ United States" }]} /></FieldGroup>
          {!theme && view && view.universes.length > 0 && (
            <Field label="Stocks">{(id) => <Select id={id} value={view.universe ?? ""} onChange={(v) => set({ u: v })} options={view.universes.map((u) => ({ value: u.id, label: u.name }))} />}</Field>
          )}
          {!theme && <Field label="Smallest market value">{(id) => <Select id={id} value={minCap} onChange={(v) => set({ min: v || null })} options={MIN_CAPS[region]} />}</Field>}
          <FieldGroup label="Period"><ChipBar label="Period" wrap value={period} onChange={(v) => set({ p: v === "1d" ? null : v })} options={PERIODS.map((p) => ({ value: p, label: PERIOD_SHORT[p] }))} /></FieldGroup>
          <FieldGroup label="Colour by" infoLabel="About the colours"
            info="Change: what the price did over the period. Vs index: that change less the index's change over the same period, in percentage points. Volume: the last day's volume as a multiple of its average over the 20 sessions before.">
            <Seg label="Colour by" value={color} onChange={(v) => set({ c: v === "change" ? null : v })} options={COLORS} /></FieldGroup>
          <FieldGroup label="Size by" infoLabel="About the sizes"
            info="Market value: share price times shares. Equal: every company the same. Value traded: the last day's volume times its closing price.">
            <Seg label="Size by" value={size} onChange={(v) => set({ s: v === "cap" ? null : v })} options={SIZES} /></FieldGroup>
          <FieldGroup label="Group by"><Seg label="Group by" value={group} onChange={(v) => set({ g: v === groups[0].value ? null : v })} options={groups} /></FieldGroup>
        </div>
      </Card>
      {theme && <p className="k-note">Showing the companies of the theme <Link className="link" to={`/research/themes?q=${encodeURIComponent(theme)}&region=${region}`}>{cos?.name ?? theme}</Link>. <Link className="link" to={`/invest/heatmap?region=${region}`}>See the whole market</Link>.</p>}
      {error ? <ErrorState title="The heatmap couldn't be read" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>{error}</ErrorState>
        : !view ? <Card><Working label={theme ? "Reading the theme's companies" : "Reading the market's closes"} /></Card>
        : view.pending ? (
          <Card><EmptyState title="The heatmap fills in after the next market close">Each company's changes are worked out once a day from its daily closes, after the market shuts. They appear here on their own once that has run.</EmptyState></Card>
        ) : !tiles.length ? (
          <Card><EmptyState title={theme ? "None of this theme's companies has stored closes yet" : "No company matches these settings"}>
            {theme ? "A company appears here once the daily closes include it." : "Pick a smaller market value or another group of stocks."}</EmptyState></Card>
        ) : (
          <Card label="The heatmap" testId="heatmap">
            <CardHead title={`${name}: ${PERIOD_LABEL[period].toLowerCase()}`} infoLabel="About the heatmap"
              info={`Each tile is one company. Its area is its share of the ${size === "cap" ? "market value" : size === "traded" ? "value traded" : "number"} of the companies shown; its colour follows the legend. A group's own figure is the average of its tiles, each weighted by its size. Changes are from daily closing prices${asOf ? `, the latest ${asOf}` : ""}.`}
              actions={<><input className="k-input sm hm-search" type="search" aria-label="Find a company" placeholder="Find a company" autoComplete="off" value={query} onChange={(e) => setQuery(e.target.value)} />
                <Seg label="Show as" value={table ? "table" : "map"} onChange={(v) => set({ view: v === "table" ? "table" : null })} options={[{ value: "map", label: "Map" }, { value: "table", label: "Table" }]} /></>} />
            <p className="hm-facts" data-testid="hm-facts">
              {asOf && <span>Closes of <b>{asOf}</b></span>}
              {!cos && index?.[pi] != null && <span>{view.index.name} <b><Signed value={index[pi]} fmt={(v) => pct(v, 2)} /></b></span>}
              <span><b>{counts.up}</b> up, <b>{counts.down}</b> down{counts.flat ? <>, <b>{counts.flat}</b> unchanged</> : null}</span>
              <span><b>{tiles.length.toLocaleString("en-IN")}</b> {tiles.length === 1 ? "company" : "companies"}</span>
            </p>
            {busy && <Working small label="Reading the new settings" />}
            {noIndex && <p className="k-note">The index has no figure for this period yet, so there is nothing to set the changes against. Pick Change, or another period.</p>}
            {table ? (
              <DataTable csv={`heatmap ${name} ${PERIOD_SHORT[period]}`} label={`${name}: every company`} columns={cols} rows={shown} rowKey={(t) => t.s} stack compact phonePage={40} pageDesktop
                sort={{ key: sort.key, desc: sort.desc, onSort: (k) => setSort((s) => ({ key: k, desc: s.key === k ? !s.desc : true })) }}
                empty="No company matches what you typed." />
            ) : (
              <>
                <Treemap tiles={tiles} size={size} color={color} period={period} group={group} index={index} query={query} href={href}
                  figure={(v) => figureText(v, color)} tip={tip} onLeftOut={setLeftOut}
                  label={`${name}: ${tiles.length} companies as tiles, sized by ${SIZES.find((s) => s.value === size)!.label.toLowerCase()} and coloured by ${colorTitle.toLowerCase()}. The Table view lists every company.`} />
                <TreemapLegend color={color} period={period} title={colorTitle} />
              </>
            )}
            {cut && <p className="k-note">The {view.shown.toLocaleString("en-IN")} largest of {view.matching.toLocaleString("en-IN")} companies are shown. Pick a smallest market value to narrow the group.</p>}
            {!table && leftOut > 0 && <p className="k-note">{leftOut} {leftOut === 1 ? "company has" : "companies have"} no {size === "cap" ? "market value" : "traded value"} on record and {leftOut === 1 ? "is" : "are"} left out of the map. The Table view lists {leftOut === 1 ? "it" : "them"}.</p>}
            {closesNote(view, cos ? "in the theme" : "in this group") && <p className="k-note" data-testid="hm-closes-note">{closesNote(view, cos ? "in the theme" : "in this group")}</p>}
          </Card>
        )}
    </div>
  );
}
