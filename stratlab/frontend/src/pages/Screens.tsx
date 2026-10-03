import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { pct, price } from "../lib/format";
import { REGION_NAME, saveRegion, savedRegion, type Region } from "../lib/research";
import {
  NO_FILTERS, conditionCount, screensApi, type Bound, type Filters, type RangeId, type SavedPage, type SavedScreen,
  type ScreenMeta, type ScreenResult, type ScreenRow,
} from "../lib/screens";
import { ResearchNav } from "../components/Research";
import { AsOf, Info, Loading } from "../components/ui";
import { Trash } from "../components/Icons";

type Draft = Partial<Record<RangeId, { min: string; max: string }>>;
type Col = { id: keyof ScreenRow; label: string; short?: string; help?: string; cell: (r: ScreenRow, region: Region) => string; india?: boolean };

const num = (v: number | null, dp = 1, unit = "") => (v == null ? "–" : `${v.toFixed(dp)}${unit}`);
function cap(v: number | null, region: Region): string {
  if (v == null) return "–";
  if (region === "IN") return `₹${Math.round(v).toLocaleString("en-IN")} cr`;
  return v >= 1e6 ? `$${(v / 1e6).toFixed(2)} T` : v >= 1000 ? `$${(v / 1000).toFixed(1)} B` : `$${Math.round(v)} M`;
}

const COLS: Col[] = [
  { id: "name", label: "Company", cell: (r) => r.name },
  { id: "sector", label: "Sector", cell: (r) => r.sector ?? "–" },
  { id: "market_cap", label: "Market value", cell: (r, g) => cap(r.market_cap, g) },
  { id: "price", label: "Last price", cell: (r, g) => (r.price == null ? "–" : price(r.price, g === "IN" ? "INR" : "USD")) },
  { id: "from_high", label: "vs 52-week high", cell: (r) => (r.from_high == null ? "–" : pct(r.from_high)) },
  { id: "sales_cagr_3y", label: "Revenue growth, 3y", cell: (r) => (r.sales_cagr_3y == null ? "–" : pct(r.sales_cagr_3y)) },
  { id: "net_margin", label: "Net margin", cell: (r) => num(r.net_margin, 1, "%") },
  { id: "opm", label: "Operating margin", cell: (r) => num(r.opm, 1, "%") },
  { id: "debt_equity", label: "Debt to equity", cell: (r) => num(r.debt_equity, 2) },
  { id: "roe", label: "ROE", cell: (r) => num(r.roe, 1, "%") },
  { id: "roce", label: "ROCE", cell: (r) => num(r.roce, 1, "%") },
  { id: "div_yield", label: "Dividend yield", cell: (r) => num(r.div_yield, 2, "%") },
  { id: "pe", label: "P/E", cell: (r) => num(r.pe, 1) },
  { id: "stage", label: "Stage", cell: (r) => (r.stage == null ? "–" : String(r.stage)) },
  { id: "red_flags", label: "Red-flag filings (3 months)", short: "Red flags", cell: (r) => (r.red_flags == null ? "–" : String(r.red_flags)), india: true },
];

function useRegion(): [Region, (r: Region) => void] {
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("region")?.toUpperCase();
  const [region, setState] = useState<Region>(fromUrl === "US" || fromUrl === "IN" ? fromUrl : savedRegion());
  return [region, (r: Region) => {
    setState(r); saveRegion(r);
    const p = new URLSearchParams(params); p.set("region", r); setParams(p, { replace: true });
  }];
}

const toDraft = (f: Filters): Draft => Object.fromEntries(Object.entries(f.ranges).map(([k, b]) =>
  [k, { min: b?.min == null ? "" : String(b.min), max: b?.max == null ? "" : String(b.max) }]));
/** The typed bounds as numbers; a box that isn't a number yet is left out (and marked). */
function fromDraft(d: Draft): { ranges: Partial<Record<RangeId, Bound>>; bad: Set<string> } {
  const ranges: Partial<Record<RangeId, Bound>> = {}, bad = new Set<string>();
  for (const [k, v] of Object.entries(d) as [RangeId, { min: string; max: string }][]) {
    const read = (s: string, side: string) => {
      const t = s.trim().replace(/,/g, "");
      if (!t) return null;
      const n = Number(t);
      if (!Number.isFinite(n)) { bad.add(`${k}.${side}`); return null; }
      return n;
    };
    const b = { min: read(v.min, "min"), max: read(v.max, "max") };
    if (b.min != null || b.max != null) ranges[k] = b;
  }
  return { ranges, bad };
}

/** Companies filtered by plain facts, in a table. No ranking, scores or picks: the user's own conditions, sorted
 * alphabetically or by the column they choose. */
export function ScreensPage() {
  const { fail, notify } = useApp();
  const [region, setRegion] = useRegion();
  const [meta, setMeta] = useState<ScreenMeta | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [draft, setDraft] = useState<Draft>({});
  const [sort, setSort] = useState("name");
  const [desc, setDesc] = useState(false);
  const [out, setOut] = useState<ScreenResult | null>(null);
  const [rows, setRows] = useState<ScreenRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState<SavedPage | null>(null);
  const [open, setOpen] = useState<SavedScreen | null>(null);
  const [name, setName] = useState("");
  const [weekly, setWeekly] = useState(false);
  const [saving, setSaving] = useState(false);
  // on a phone the filters start folded, so the table is in view; one tap opens them
  const [showFilters, setShowFilters] = useState(() => typeof matchMedia !== "function" || matchMedia("(min-width: 1001px)").matches);
  const seq = useRef(0);

  const { ranges, bad } = useMemo(() => fromDraft(draft), [draft]);
  const current: Filters = useMemo(() => ({ ...filters, ranges }), [filters, ranges]);

  useEffect(() => {
    setMeta(null);
    screensApi.meta(region).then(setMeta).catch((e) => setError((e as Error).message));
  }, [region]);
  useEffect(() => { screensApi.saved().then(setSaved).catch(() => undefined); }, []);

  const run = useCallback((offset = 0) => {
    const n = ++seq.current;
    setLoading(true);
    screensApi.run(region, current, sort, desc, offset)
      .then((r) => { if (n !== seq.current) return; setOut(r); setRows((old) => (offset ? [...old, ...r.rows] : r.rows)); setError(null); })
      .catch((e) => { if (n === seq.current) setError((e as Error).message); })
      .finally(() => { if (n === seq.current) setLoading(false); });
  }, [region, current, sort, desc]);
  // a short pause after each change, so typing a number runs the screen once
  useEffect(() => { const t = setTimeout(() => run(0), 350); return () => clearTimeout(t); }, [run]);

  const pickRegion = (r: Region) => { setRegion(r); setFilters(NO_FILTERS); setDraft({}); setOpen(null); };
  const toggle = <K extends "sector" | "cap" | "stage">(key: K, v: Filters[K][number]) =>
    setFilters((f) => {
      const list = f[key] as (string | number)[];
      return { ...f, [key]: list.includes(v) ? list.filter((x) => x !== v) : [...list, v] };
    });
  const setBound = (k: RangeId, side: "min" | "max", v: string) =>
    setDraft((d) => ({ ...d, [k]: { min: d[k]?.min ?? "", max: d[k]?.max ?? "", [side]: v } }));
  const clear = () => { setFilters(NO_FILTERS); setDraft({}); setSort("name"); setDesc(false); setOpen(null); };
  const sortBy = (id: string) => { if (sort === id) setDesc((d) => !d); else { setSort(id); setDesc(false); } };

  const load = (s: SavedScreen) => {
    if (s.region !== region) setRegion(s.region);
    setFilters({ ...NO_FILTERS, ...s.filters }); setDraft(toDraft(s.filters)); setSort(s.sort); setDesc(s.desc);
    setOpen(s); setName(s.name); setWeekly(s.notify);
  };
  const save = async (asNew: boolean) => {
    if (!name.trim()) { notify("Give the screen a name first."); return; }
    setSaving(true);
    try {
      const r = await screensApi.save({ name: name.trim(), region, filters: current, sort, desc, notify: weekly }, asNew ? undefined : open?.id);
      setSaved(r); setOpen(r.screen);
      notify(asNew ? `Saved “${r.screen.name}”.` : `Updated “${r.screen.name}”.`);
    } catch (e) { fail(e); } finally { setSaving(false); }
  };
  const remove = async (s: SavedScreen) => {
    try { setSaved(await screensApi.remove(s.id)); if (open?.id === s.id) setOpen(null); notify(`Deleted “${s.name}”.`); } catch (e) { fail(e); }
  };

  const cols = COLS.filter((c) => !c.india || region === "IN");
  const n = conditionCount(current);
  const full = !!saved && saved.count >= saved.limit;
  const help = meta?.help ?? {};

  return (
    <div className="stack" style={{ gap: 22 }}>
      <ResearchNav region={region} setRegion={pickRegion} />
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Research · {REGION_NAME[region]} · Screens</span>
        <h1 className="page-title">Filter companies by plain facts</h1>
        <p className="page-sub">Pick the conditions; see every company that meets them. Nothing here ranks or scores companies: the list is alphabetical unless you sort by a column. Facts from reported results, exchange filings and daily prices, not advice.</p>
      </div>

      {saved && saved.items.length > 0 && (
        <section className="card stack" style={{ gap: 10 }} aria-label="Your saved screens">
          <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
            <h2 className="h2" style={{ fontSize: 18 }}>Your screens</h2>
            <span className="small muted">{saved.count} of {saved.limit} saved</span>
          </div>
          <div className="row wrap" style={{ gap: 8 }}>
            {saved.items.map((s) => (
              <span key={s.id} className="saved-screen">
                <button className={`btn quiet sm${open?.id === s.id ? " on" : ""}`} aria-pressed={open?.id === s.id} onClick={() => load(s)}
                  title={s.conditions.join("; ") || "Every company"}>{s.name}{s.region !== region ? ` (${s.region})` : ""}{s.notify ? " · weekly" : ""}</button>
                <button className="btn quiet sm icon-only" aria-label={`Delete ${s.name}`} onClick={() => remove(s)}><Trash size={16} /></button>
              </span>
            ))}
          </div>
        </section>
      )}

      <div className="screens-grid">
        <section className="card stack screens-filters" style={{ gap: 16 }} aria-label="Filters">
          <div className="spread" style={{ gap: 8 }}>
            <button className="btn quiet sm screens-toggle" aria-expanded={showFilters} onClick={() => setShowFilters((s) => !s)}>
              {showFilters ? "Hide filters" : "Show filters"}{n ? ` (${n})` : ""}</button>
            <button className="btn quiet sm" onClick={clear} disabled={!n && sort === "name" && !desc}>Clear</button>
          </div>
          {!meta ? <Loading label="Loading the filters" /> : showFilters && <>
            <Group title="Sector" help={help.sector}>
              {meta.sectors.length === 0 ? <p className="small muted">No companies gathered yet.</p>
                : <div className="chips">{meta.sectors.map((s) =>
                  <button key={s} className="chip-btn" aria-pressed={filters.sector.includes(s)} onClick={() => toggle("sector", s)}>{s}</button>)}</div>}
            </Group>
            <Group title="Company size (market value)" help={help.cap}>
              <div className="chips">{meta.cap.map((c) =>
                <button key={c.id} className="chip-btn" aria-pressed={filters.cap.includes(c.id)} onClick={() => toggle("cap", c.id)}>{c.label}</button>)}</div>
            </Group>
            {meta.ranges.map((r) => (
              <Group key={r.id} title={r.label} help={r.help}>
                <div className="range-row">
                  <label className="field"><span className="hint">At least</span>
                    <input inputMode="decimal" value={draft[r.id]?.min ?? ""} placeholder="Any" aria-label={`${r.label}: at least`}
                      aria-invalid={bad.has(`${r.id}.min`)} onChange={(e) => setBound(r.id, "min", e.target.value)} /></label>
                  <label className="field"><span className="hint">At most</span>
                    <input inputMode="decimal" value={draft[r.id]?.max ?? ""} placeholder="Any" aria-label={`${r.label}: at most`}
                      aria-invalid={bad.has(`${r.id}.max`)} onChange={(e) => setBound(r.id, "max", e.target.value)} /></label>
                  <span className="hint range-unit">{r.unit === "%" ? "%" : "times"}</span>
                </div>
                {(bad.has(`${r.id}.min`) || bad.has(`${r.id}.max`)) && <span className="hint neg">Enter a plain number, like 15 or -10.</span>}
              </Group>
            ))}
            <Group title="Stage" help={help.stage}>
              <div className="chips">{meta.stages.map((s) =>
                <button key={s.id} className="chip-btn" aria-pressed={filters.stage.includes(s.id)} onClick={() => toggle("stage", s.id)}>{s.label}</button>)}</div>
            </Group>
            {meta.red_flags && (
              <Group title="Recent red-flag filings" help={help.red_flags}>
                <div className="seg" role="radiogroup" aria-label="Recent red-flag filings">
                  {([[null, "Either"], ["no", "None"], ["yes", "At least one"]] as const).map(([v, label]) => (
                    <button key={label} role="radio" aria-checked={filters.red_flags === v} aria-pressed={filters.red_flags === v}
                      onClick={() => setFilters((f) => ({ ...f, red_flags: v }))}>{label}</button>
                  ))}
                </div>
              </Group>
            )}
          </>}
        </section>

        <section className="stack" style={{ gap: 14, minWidth: 0 }} aria-label="Companies that match">
          <div className="card stack" style={{ gap: 12 }}>
            <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
              <span className="small">{out ? <><b>{out.total.toLocaleString()}</b> of {out.indexed.toLocaleString()} companies match</> : "Checking…"}
                {loading && <span className="spin" style={{ display: "inline-block", marginLeft: 8, verticalAlign: "middle" }} />}</span>
              <div className="row wrap" style={{ gap: 8 }}>
                <label className="field sort-field"><span className="hint">Sort by</span>
                  <select value={sort} onChange={(e) => { setSort(e.target.value); setDesc(false); }} aria-label="Sort by">
                    {cols.map((c) => <option key={c.id} value={c.id}>{c.short ?? c.label}</option>)}
                  </select></label>
                <button className="btn quiet sm" style={{ alignSelf: "flex-end" }} onClick={() => setDesc((d) => !d)}>
                  {desc ? "High to low ↓" : sort === "name" || sort === "sector" ? "A to Z ↑" : "Low to high ↑"}</button>
              </div>
            </div>
            <AsOf parts={[["Prices", out?.as_of], ["List gathered", out?.index_at]]} />
            {error && <p className="small neg" role="alert">{error}</p>}
            {out && out.indexed === 0 && <p className="small muted">StratLab is still gathering company numbers for {REGION_NAME[region]}. Check back in a little while.</p>}
            {out && out.indexed > 0 && out.total === 0 && <p className="small muted">No company meets every condition. Try widening one of them.</p>}
            {rows.length > 0 && (
              <div className="table-wrap screens-table">
                <table>
                  <thead><tr>{cols.map((c) => (
                    <th key={c.id} aria-sort={sort === c.id ? (desc ? "descending" : "ascending") : "none"}>
                      <button className="th-sort" onClick={() => sortBy(c.id)}>{c.short ?? c.label}{sort === c.id ? (desc ? " ↓" : " ↑") : ""}</button>
                    </th>))}</tr></thead>
                  <tbody>{rows.map((r) => (
                    <tr key={r.symbol}>{cols.map((c) => c.id === "name"
                      ? <td key={c.id}><Link className="link" to={`/research/${region}/${encodeURIComponent(r.symbol)}`}>{r.name}</Link> <span className="tiny muted">{r.symbol}</span></td>
                      : <td key={c.id} className={c.id === "sector" ? "" : "num"}>{c.cell(r, region)}</td>)}</tr>))}
                  </tbody>
                </table>
              </div>
            )}
            {out && rows.length < out.total && <button className="btn quiet sm" style={{ alignSelf: "center" }} disabled={loading} onClick={() => run(rows.length)}>Show more ({(out.total - rows.length).toLocaleString()} left)</button>}
          </div>

          <div className="card stack" style={{ gap: 10 }}>
            <h2 className="h2" style={{ fontSize: 18 }}>{open ? `Screen: ${open.name}` : "Save this screen"}<Info>{"Saved screens keep your conditions. Turn on the weekly email to hear on Saturday mornings which companies newly meet them. Your plan sets how many you can keep."}</Info></h2>
            <div className="row wrap" style={{ gap: 10, alignItems: "flex-end" }}>
              <label className="field" style={{ flex: "1 1 220px" }}><span>Name</span>
                <input value={name} maxLength={60} placeholder="Like: Low debt, growing revenue" onChange={(e) => setName(e.target.value)} /></label>
              <label className="row small" style={{ gap: 8, minHeight: 44 }}>
                <input type="checkbox" checked={weekly} onChange={(e) => setWeekly(e.target.checked)} />Weekly email of new matches</label>
            </div>
            <div className="row wrap" style={{ gap: 8 }}>
              {open && <button className="btn sm" disabled={saving} onClick={() => save(false)}>Update “{open.name}”</button>}
              <button className={`btn sm${open ? " quiet" : ""}`} disabled={saving || full} onClick={() => save(true)}>{open ? "Save as a new screen" : "Save screen"}</button>
            </div>
            {full && <p className="small muted">Your plan keeps {saved?.limit} saved screen{saved?.limit === 1 ? "" : "s"}. Delete one to save another, or <Link className="link" to="/plans">see plans</Link>.</p>}
            {weekly && saved?.email && !saved.email_confirmed && <p className="hint">The email goes out once you've confirmed {saved.email} in <Link className="link" to="/account#newsletters">Account</Link>.</p>}
          </div>
        </section>
      </div>
      <p className="hint">Companies appear here once StratLab has gathered their reported numbers; the list grows through the day. A blank means the company doesn't report that number. Not investment advice.</p>
    </div>
  );
}

function Group({ title, help, children }: { title: string; help?: string; children: React.ReactNode }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      <span className="small" style={{ fontWeight: 600 }}>{title}{help && <Info label={`What is ${title}?`}>{help}</Info>}</span>
      {children}
    </div>
  );
}
