import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { asOf, fmtDate, latestDue, marketTz, pct, price } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { REGION_NAME, screenCap, screenNum, useRegion, type Region } from "../lib/research";
import {
  NO_FILTERS, conditionCount, screensApi, staleNote, type Bound, type Filters, type RangeId, type SavedPage, type SavedScreen,
  type ScreenMeta, type ScreenResult, type ScreenRow,
} from "../lib/screens";
import { RegionSwitch } from "../components/Research";
import { screenFromQuery, screenQuery, withParams } from "../lib/investUi";
import { Trash } from "../components/Icons";
import { SurvBadges } from "../components/Surveillance";
import { useMoreColumns } from "../components/MoreColumns";
import {
  Card, CardHead, ChipSet, CheckField, ConfirmDialog, DataTable, EmptyState, ErrorState, Field, FieldGroup, FormActions, FormGrid, Notice, PageHeader, PlanNote, Seg, Select, Signed, Skeleton,
  type Column,
} from "../components/kit";
import { limitLine, planIdOf } from "../lib/lockText";

type Draft = Partial<Record<RangeId, { min: string; max: string }>>;
type Col = { id: keyof ScreenRow; label: string; short?: string; cell: (r: ScreenRow, region: Region) => ReactNode; india?: boolean; text?: boolean };

const num = screenNum;
const cap = screenCap;

const COLS: Col[] = [
  { id: "name", label: "Company", cell: (r) => r.name, text: true },
  { id: "sector", label: "Sector", cell: (r) => r.sector ?? "–", text: true },
  { id: "market_cap", label: "Market value", cell: (r, g) => cap(r.market_cap, g) },
  { id: "price", label: "Last close", cell: (r, g) => (r.price == null ? "–" : price(r.price, g === "IN" ? "INR" : "USD")) },
  { id: "from_high", label: "vs 52-week high", cell: (r) => (r.from_high == null ? "–" : pct(r.from_high)) },
  { id: "sales_cagr_3y", label: "Revenue growth, 3y", cell: (r) => (r.sales_cagr_3y == null ? "–" : <Signed value={r.sales_cagr_3y}>{pct(r.sales_cagr_3y)}</Signed>) },
  { id: "net_margin", label: "Net margin", cell: (r) => num(r.net_margin, 1, "%") },
  { id: "opm", label: "EBITDA margin", cell: (r) => num(r.opm, 1, "%") },
  { id: "debt_equity", label: "Debt to equity", cell: (r) => num(r.debt_equity, 2) },
  { id: "roe", label: "ROE", cell: (r) => num(r.roe, 1, "%") },
  { id: "roce", label: "ROCE", cell: (r) => num(r.roce, 1, "%") },
  { id: "div_yield", label: "Dividend yield", cell: (r) => num(r.div_yield, 2, "%") },
  { id: "pe", label: "P/E", cell: (r) => num(r.pe, 1) },
  { id: "stage", label: "Stage", cell: (r) => (r.stage == null ? "–" : String(r.stage)) },
  { id: "red_flags", label: "Red-flag filings (3 months)", short: "Red flags", cell: (r) => (r.red_flags == null ? "–" : String(r.red_flags)) },
];

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

/** One filter: its name with its (i), and the control under it. */
function Group({ title, help, children }: { title: string; help?: string; children: ReactNode }) {
  return (
    <FieldGroup label={title} info={help} infoLabel={`What is ${title}?`}>
      {children}
    </FieldGroup>
  );
}

/** How many rows were on the page for a screen (its address), so Back loads as many again (review 5c). */
const LOADED_KEY = "stratlab.screens.loaded";
function loadedFor(key: string): number {
  try { const v = JSON.parse(sessionStorage.getItem(LOADED_KEY) || "{}"); return v.key === key && Number(v.n) > 0 ? Number(v.n) : 0; } catch { return 0; }
}
function rememberLoaded(key: string, n: number) {
  try { sessionStorage.setItem(LOADED_KEY, JSON.stringify({ key, n })); } catch { /* storage off: Back shows the first rows */ }
}

/** Companies filtered by plain facts, in a table. No ranking, scores or picks: the user's own conditions, sorted
 * by market value (the largest first) or by the column they choose. */
export function ScreensPage() {
  const { fail, notify, me } = useApp();
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  // the conditions and the sort are kept in the address (replaced, not pushed), so Back from a company returns to this screen
  const [start] = useState(() => screenFromQuery(params, NO_FILTERS));
  const [meta, setMeta] = useState<ScreenMeta | null>(null);
  const [filters, setFilters] = useState<Filters>(start.filters);
  const [draft, setDraft] = useState<Draft>(() => toDraft(start.filters));
  const [sort, setSort] = useState(start.sort);               // the largest companies first (R5O-012)
  const [desc, setDesc] = useState(start.desc);
  const [out, setOut] = useState<ScreenResult | null>(null);
  const [rows, setRows] = useState<ScreenRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState<SavedPage | null>(null);
  const [open, setOpen] = useState<SavedScreen | null>(null);
  const [name, setName] = useState("");
  const [weekly, setWeekly] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dropping, setDropping] = useState<SavedScreen | null>(null);
  // on a phone the filters start folded, so the table is in view; one tap opens them
  const [showFilters, setShowFilters] = useState(() => typeof matchMedia !== "function" || matchMedia("(min-width: 1361px)").matches);
  const seq = useRef(0);

  const { ranges, bad } = useMemo(() => fromDraft(draft), [draft]);
  const current: Filters = useMemo(() => ({ ...filters, ranges }), [filters, ranges]);
  const query = useMemo(() => screenQuery({ filters: current, sort, desc }, NO_FILTERS), [current, sort, desc]);
  useEffect(() => {
    const next = withParams(params, query);
    if (next !== params) setParams(next, { replace: true });
  }, [query, params, setParams]);
  // the rows a Back should load again: as many as were shown for this same screen (read once, on opening)
  const screenKey = `${region}?${new URLSearchParams(Object.entries(query).filter(([, v]) => v != null) as [string, string][])}`;
  const restore = useRef(loadedFor(screenKey));

  useEffect(() => {
    // another market's screen has other columns and other stocks: the old result goes, and a run still on its way for the old market is dropped
    seq.current++; setOut(null); setRows([]);
    setMeta(null);
    screensApi.meta(region).then(setMeta).catch((e) => setError((e as Error).message));
  }, [region]);
  useEffect(() => { screensApi.saved().then(setSaved).catch(() => undefined); }, []);

  const run = useCallback((offset = 0) => {
    const n = ++seq.current;
    setLoading(true);
    screensApi.run(region, current, sort, desc, offset)
      .then((r) => {
        if (n !== seq.current) return;
        setOut(r); setRows((old) => (offset ? [...old, ...r.rows] : r.rows)); setError(null);
        const shown = offset + r.rows.length;
        // back on a screen that had more rows showing: the next page is asked for until they are all there again
        if (restore.current > shown && shown < r.total && r.rows.length) { runRef.current(shown); return; }
        restore.current = 0;
        rememberLoaded(screenKey, shown);
      })
      .catch((e) => { if (n === seq.current) { restore.current = 0; setError((e as Error).message); } })
      .finally(() => { if (n === seq.current) setLoading(false); });
  }, [region, current, sort, desc, screenKey]);
  const runRef = useRef(run);
  runRef.current = run;
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
  const clear = () => { setFilters(NO_FILTERS); setDraft({}); setSort("market_cap"); setDesc(true); setOpen(null); };
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
  // asked first (R62-011): one tap on the bin took a saved screen and its weekly email with it
  const remove = async (s: SavedScreen) => {
    try { setSaved(await screensApi.remove(s.id)); if (open?.id === s.id) setOpen(null); notify(`Deleted “${s.name}”.`); } catch (e) { fail(e); } finally { setDropping(null); }
  };

  // the US column is the SEC's industry division (Manufacturing, Services), not a market sector (R13S-015)
  const sectorName = region === "US" ? "Industry (SEC division)" : "Sector";
  const cols = COLS.filter((c) => !c.india || region === "IN").map((c) => (c.id === "sector" ? { ...c, label: sectorName, short: region === "US" ? "Industry" : undefined } : c));
  const n = conditionCount(current);
  const full = !!saved && saved.count >= saved.limit;
  const help = meta?.help ?? {};
  // the first five columns (and the one sorted by) fit beside the filters; the rest are one click away
  const more = useMoreColumns("screens", Math.max(0, cols.length - 5));
  const tableCols: Column<ScreenRow>[] = cols.map((c) => c.id === "name"
    ? { key: c.id, header: c.short ?? c.label, rowHeader: true, wrap: true, sortable: true, cell: (r: ScreenRow) => (
      <><Link className="link" to={`/research/${region}/${encodeURIComponent(r.symbol)}`}>{r.name}</Link> <span className="k-note">{r.symbol}</span>
        {r.surveillance && r.surveillance.length > 0 && <> <SurvBadges region={region} symbol={r.symbol} codes={r.surveillance} /></>}</>) }
    : { key: c.id, header: c.short ?? c.label, numeric: !c.text, sortable: true, cell: (r: ScreenRow) => (
      // a row whose close is of another day than the header's says its own day (R7O-004)
      c.id === "price" && r.price != null && r.price_at && out?.as_of && r.price_at.slice(0, 10) !== out.as_of.slice(0, 10)
        ? <>{c.cell(r, region)}<span className="k-sub-line">{fmtDate(r.price_at.slice(0, 10), { year: false })} close</span></>
        : c.cell(r, region)) });

  const shownCols = more.on ? tableCols : tableCols.filter((c, i) => i < 5 || c.key === sort);
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/screens")} title="Filter companies by plain facts" asOf={out?.as_of} asOfLabel={out?.as_of_newest && out.as_of && out.as_of_newest.slice(0, 10) !== out.as_of.slice(0, 10) ? "Oldest close" : "Prices as of"} asOfTz={marketTz(region)}
        info={out?.index_at ? <>List gathered as of {asOf(out.index_at) ?? out.index_at}. Facts from reported results, exchange filings and daily prices, not advice.</> : "Facts from reported results, exchange filings and daily prices, not advice."}
        lede="Pick the conditions; see every company that meets them. Nothing here scores companies: the list starts with the largest market value; sort by any column." />
      {latestDue(out?.as_of_newest ?? out?.as_of, out?.pending) && <p className="k-note" data-testid="screens-pending">{latestDue(out?.as_of_newest ?? out?.as_of, out?.pending)}</p>}
      {staleNote(out?.stale) && <p className="k-note" data-testid="screens-stale">{staleNote(out?.stale)}</p>}
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={pickRegion} /></div>

      {saved && saved.items.length > 0 && (
        <Card label="Your saved screens">
          <CardHead title="Your screens" actions={<span className="k-note">{saved.count} of {saved.limit} saved</span>} />
          <div className="k-row">
            {saved.items.map((s) => (
              <span key={s.id} className="saved-screen">
                <button className={`btn quiet sm${open?.id === s.id ? " on" : ""}`} aria-pressed={open?.id === s.id} onClick={() => load(s)}
                  title={s.conditions.join("; ") || "Every company"}>{s.name}{s.region !== region ? ` (${s.region})` : ""}{s.notify ? " · weekly" : ""}</button>
                <button className="btn quiet sm icon-only" aria-label={`Delete ${s.name}`} onClick={() => setDropping(s)}><Trash size={16} /></button>
              </span>
            ))}
          </div>
        </Card>
      )}

      <div className="k-split2">
        <div className="inv-sticky">
          <Card label="Filters">
            <CardHead title="Filters" actions={<>
              <button className="btn quiet sm inv-toggle" aria-expanded={showFilters} onClick={() => setShowFilters((s) => !s)}>{showFilters ? "Hide filters" : "Show filters"}{n ? ` (${n})` : ""}</button>
              <button className="btn quiet sm" onClick={clear} disabled={!n && sort === "market_cap" && desc}>Clear</button></>} />
            {!meta ? <Skeleton label="Loading the filters" lines={4} /> : showFilters && <>
              <Group title={sectorName} help={help.sector}>
                {meta.sectors.length === 0 ? <p className="k-small k-muted">No companies gathered yet.</p>
                  : <ChipSet label={sectorName} options={meta.sectors.map((s) => ({ value: s, label: s }))} on={filters.sector} onToggle={(v) => toggle("sector", v)} />}
              </Group>
              <Group title="Company size (market value)" help={help.cap}>
                <ChipSet label="Company size" options={meta.cap.map((c) => ({ value: c.id, label: c.label }))} on={filters.cap} onToggle={(v) => toggle("cap", v as Filters["cap"][number])} />
              </Group>
              {meta.ranges.map((r) => (
                <Group key={r.id} title={r.label} help={r.help}>
                  <div className="inv-bounds">
                    <Field label="At least" inputMode="decimal" value={draft[r.id]?.min ?? ""} placeholder="Any" aria-label={`${r.label}: at least`}
                      aria-invalid={bad.has(`${r.id}.min`)} onChange={(e) => setBound(r.id, "min", e.target.value)} />
                    <Field label="At most" inputMode="decimal" value={draft[r.id]?.max ?? ""} placeholder="Any" aria-label={`${r.label}: at most`}
                      aria-invalid={bad.has(`${r.id}.max`)} onChange={(e) => setBound(r.id, "max", e.target.value)} />
                    <span className="k-unit">{r.unit === "%" ? "%" : "times"}</span>
                  </div>
                  {(bad.has(`${r.id}.min`) || bad.has(`${r.id}.max`)) && <span className="k-note k-down">Enter a plain number, like 15 or -10.</span>}
                </Group>
              ))}
              <Group title="Stage" help={help.stage}>
                <ChipSet label="Stage" options={meta.stages.map((s) => ({ value: String(s.id), label: s.label }))} on={filters.stage.map(String)}
                  onToggle={(v) => toggle("stage", meta.stages.find((s) => String(s.id) === v)!.id as Filters["stage"][number])} />
              </Group>
              {meta.red_flags && (
                <Group title="Recent red-flag filings" help={help.red_flags}>
                  <Seg label="Recent red-flag filings" value={filters.red_flags ?? "either"} onChange={(v) => setFilters((f) => ({ ...f, red_flags: v === "either" ? null : (v as "yes" | "no") }))}
                    options={[{ value: "either", label: "Either" }, { value: "no", label: "None" }, { value: "yes", label: "At least one" }]} />
                </Group>
              )}
              {meta.insider && (
                <Group title="Promoter or insider bought" help={help.insider_buy}>
                  <Seg label="Promoter or insider bought" value={filters.insider_buy ?? "either"} onChange={(v) => setFilters((f) => ({ ...f, insider_buy: v === "either" ? null : (v as "yes" | "no") }))}
                    options={[{ value: "either", label: "Either" }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }]} />
                  <Field label="On the open market, in the last">
                    {(id) => <Select id={id} label="Promoter or insider bought: in the last" value={filters.insider_days ?? meta.insider!.default}
                      onChange={(v) => setFilters((f) => ({ ...f, insider_days: Number(v) }))} options={meta.insider!.days.map((d) => ({ value: d, label: `${d} days` }))} />}
                  </Field>
                </Group>
              )}
              {meta.surveillance && (
                <Group title="Exchange surveillance" help={help.surveillance}>
                  <Seg label="Exchange surveillance" value={filters.surveillance ?? "either"} onChange={(v) => setFilters((f) => ({ ...f, surveillance: v === "either" ? null : (v as "on" | "off") }))}
                    options={[{ value: "either", label: "Either" }, { value: "on", label: "On a list" }, { value: "off", label: "On none" }]} />
                  {filters.surveillance && (
                    <FieldGroup label="Which lists (none picked means any)">
                      <ChipSet label="Surveillance lists" options={meta.surveillance.lists.map((l) => ({ value: l.id, label: l.label }))} on={filters.surv_lists ?? []}
                        onToggle={(v) => setFilters((f) => ({ ...f, surv_lists: (f.surv_lists ?? []).includes(v) ? (f.surv_lists ?? []).filter((x) => x !== v) : [...(f.surv_lists ?? []), v] }))} />
                    </FieldGroup>
                  )}
                </Group>
              )}
            </>}
          </Card>
        </div>

        <div className="k-stack">
          <Card label="Companies that match">
            <CardHead title={out ? `${out.total.toLocaleString("en-IN")} of ${out.indexed.toLocaleString("en-IN")} companies match` : "Checking…"}
              actions={<>
                <Select label="Sort by" small value={sort} onChange={(v) => { setSort(v); setDesc(false); }} options={cols.map((c) => ({ value: c.id, label: c.short ?? c.label }))} />
                <button className="btn quiet sm" onClick={() => setDesc((d) => !d)}>{desc ? "High to low ↓" : sort === "name" || sort === "sector" ? "A to Z ↑" : "Low to high ↑"}</button>{more.toggle}</>} />
            {!out && !error && <div className="screens-wait"><Skeleton label="Finding the companies" lines={8} /></div>}
            {error && <ErrorState title="The companies couldn't be read" action={{ label: "Try again", onClick: () => run(0) }}>{error}</ErrorState>}
            {out && out.indexed === 0 && <EmptyState title="Still gathering company numbers">StratLab is still gathering company numbers for {REGION_NAME[region]}. Check back in a little while.</EmptyState>}
            {out && out.indexed > 0 && out.total === 0 && <EmptyState title="No company meets every condition.">Try widening one of them.</EmptyState>}
            {rows.length > 0 && (
              <div className="screens-table">
                <DataTable label="Companies that match" rows={rows} rowKey={(r) => r.symbol} stack columns={shownCols} sort={{ key: sort, desc, onSort: sortBy }} />
              </div>
            )}
            {out && rows.length < out.total && <button className="btn quiet sm k-btn-end" disabled={loading} onClick={() => run(rows.length)}>Show more ({(out.total - rows.length).toLocaleString("en-IN")} left)</button>}
          </Card>

          <Card>
            <CardHead title={open ? `Screen: ${open.name}` : "Save this screen"} info="Saved screens keep your conditions. Turn on the weekly email to hear on Saturday mornings which companies newly meet them. Your plan sets how many you can keep." />
            <FormGrid label="Save this screen" onSubmit={(e) => e.preventDefault()}>
              <Field label="Name" maxLength={60} placeholder="Like: Low debt, growing revenue" value={name} onChange={(e) => setName(e.target.value)} />
              <FieldGroup label="Email">
                <CheckField label="Weekly email of new matches" checked={weekly} onChange={setWeekly} />
              </FieldGroup>
              <FormActions>
                {open && <button type="button" className="btn" disabled={saving} onClick={() => save(false)}>Update “{open.name}”</button>}
                <button type="button" className={`btn${open ? " quiet" : ""}`} disabled={saving || full} onClick={() => save(true)}>{open ? "Save as a new screen" : "Save screen"}</button>
              </FormActions>
            </FormGrid>
            {saved && !full && <p className="k-small k-muted" data-testid="screens-left">{saved.count} of {saved.limit} saved.</p>}
            {/* the one lock wording (DP2-022, DP1-018): the plan and its count, what the next plan gives; the note adds the price */}
            {full && saved && (() => {
              const l = limitLine(planIdOf(me?.plan), "screens", `Your ${me?.plan_info.name ?? "plan"} plan keeps ${saved.limit} saved screen${saved.limit === 1 ? "" : "s"}. Delete one to save another`, "screens");
              return l.next ? <PlanNote plan={l.next}>{l.text}</PlanNote> : <Notice>{l.text}</Notice>;
            })()}
            {weekly && saved?.email && !saved.email_confirmed && <Notice>The email goes out once you've confirmed {saved.email} in <Link className="link" to="/settings#newsletters">Settings</Link>.</Notice>}
          </Card>
        </div>
      </div>
      <p className="k-note inv-text">Companies appear here once StratLab has gathered their reported numbers; the list grows through the day. A blank means the company doesn't report that number. Not investment advice.</p>
      {dropping && <ConfirmDialog title={`Delete “${dropping.name}”?`} confirmLabel="Delete this screen" onConfirm={() => void remove(dropping)} onClose={() => setDropping(null)}>
        The saved filters{dropping.notify ? " and its weekly email" : ""} go. The companies and your other screens aren't touched.</ConfirmDialog>}
    </div>
  );
}
