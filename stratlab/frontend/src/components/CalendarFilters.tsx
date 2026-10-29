import type { ReactNode } from "react";
import { Info } from "./ui";
import { Card, CheckField, ChipSet, Field, Select } from "./kit";
import { usePhone } from "./kit";
import { useState } from "react";
import type { Region } from "../lib/research";

/* The filters of the two company calendars (results, corporate actions): company size, sector, index, day, F&O, a sort and the counts
 * ("112 companies · 23 shown"), in one compact grid; on a phone behind a "Filters (n)" button. The page adds its own (the meeting's
 * purpose, the kind of action) as children. */

export interface Facets {
  sizes: { id: string; label: string; count: number }[]; sectors: { name: string; count: number }[];
  indices: { id: string; name: string; count: number }[]; fo: number | null;
}
export interface CalFilters { size: string[]; sector: string; index: string; fo: boolean; on: string; sort: string }
export const NO_CAL: CalFilters = { size: [], sector: "", index: "", fo: false, on: "", sort: "" };
export const SIZE_NAME: Record<string, string> = { large: "Large", mid: "Mid", small: "Small", micro: "Micro" };

/** How many of the shared choices are set (`sort` counts when it is not the page's first). */
export const calCount = (f: CalFilters, firstSort: string) => f.size.length + (f.sector ? 1 : 0) + (f.index ? 1 : 0) + (f.fo ? 1 : 0) + (f.on ? 1 : 0) + (f.sort && f.sort !== firstSort ? 1 : 0);

/** The filters kept on this device (a per-viewer convenience: storage can be off, then they start clear). */
export function keptFilters<F>(key: string, start: F): F {
  try {
    const raw = JSON.parse(localStorage.getItem(key) ?? "{}");
    return { ...start, ...(raw && typeof raw === "object" ? raw : {}), size: Array.isArray(raw?.size) ? raw.size.filter((x: unknown) => typeof x === "string") : [] };
  } catch { return start; }
}
export function keepFilters(key: string, f: unknown) { try { localStorage.setItem(key, JSON.stringify(f)); } catch { /* storage off: the choice holds for this visit */ } }

export function CalendarFilters({ region, facets, filters, set, firstSort, sorts, days, total, matching, unknownSize, active, onClear, testId, noun = "company", children, search }: {
  region: Region; facets: Facets | null; filters: CalFilters; set: (p: Partial<CalFilters>) => void; firstSort: string; sorts: Record<string, string>;
  days: { value: string; label: string }[]; total: number | null; matching: number | null; unknownSize: number; active: number; onClear: () => void;
  testId: string; noun?: string; children?: ReactNode; search?: ReactNode;
}) {
  const phone = usePhone();
  const [open, setOpen] = useState(false);
  const plural = (n: number) => (n === 1 ? noun : noun === "company" ? "companies" : `${noun}s`);
  const count = total == null || matching == null ? "Counting…" : active || (matching !== total)
    ? `${total.toLocaleString("en-IN")} ${plural(total)} · ${matching.toLocaleString("en-IN")} shown` : `${total.toLocaleString("en-IN")} ${plural(total)}`;
  return (
    <Card label="Filters" className="res-filters">
      <div className="k-row res-count">
        <b data-testid={testId}>{count}</b>
        {phone && <button type="button" className="btn quiet sm" aria-expanded={open} onClick={() => setOpen((s) => !s)}>{open ? "Hide filters" : "Filters"}{active ? ` (${active})` : ""}</button>}
        {active > 0 && <button type="button" className="btn quiet sm" onClick={onClear}>Clear filters</button>}
      </div>
      {(!phone || open) && facets && (
        <div className="res-filter-grid">
          <div className="k-field wide">
            <div className="k-label-row"><span className="k-lbl">Company size</span>
              <Info label="About company size">{region === "IN" ? "By rank in market value among the listed companies the app keeps, as for the screener: large is the 100 largest, mid the 101st to 250th, small the 251st to 500th, micro the rest." : "By market value: large $10 billion and up, mid $2 to 10 billion, small $300 million to 2 billion, micro under $300 million."}</Info></div>
            <ChipSet label="Company size" options={facets.sizes.map((s) => ({ value: s.id, label: `${SIZE_NAME[s.id]} ${s.count}` }))} on={filters.size}
              onToggle={(v) => set({ size: filters.size.includes(v) ? filters.size.filter((x) => x !== v) : [...filters.size, v] })} />
            {filters.size.length > 0 && unknownSize > 0 && <span className="k-note k-muted">{unknownSize} {unknownSize === 1 ? "company has" : "companies have"} no market value kept yet, so a size can't place {unknownSize === 1 ? "it" : "them"}.</span>}
          </div>
          <Field label={region === "IN" ? "Sector" : "Industry division"}>
            {(id) => <Select id={id} value={filters.sector} onChange={(v) => set({ sector: v })}
              options={[{ value: "", label: "All" }, ...facets.sectors.map((s) => ({ value: s.name, label: `${s.name} (${s.count})` })),
                ...(filters.sector && !facets.sectors.some((s) => s.name === filters.sector) ? [{ value: filters.sector, label: filters.sector }] : [])]} />}
          </Field>
          <Field label="Index">
            {(id) => <Select id={id} value={filters.index} onChange={(v) => set({ index: v })} options={[{ value: "", label: "Any" }, ...facets.indices.map((i) => ({ value: i.id, label: `${i.name} (${i.count})` }))]} />}
          </Field>
          <Field label="Day">
            {(id) => <Select id={id} value={filters.on} onChange={(v) => set({ on: v })} options={days} />}
          </Field>
          {children}
          <Field label="Sort by">
            {(id) => <Select id={id} value={filters.sort || firstSort} onChange={(v) => set({ sort: v })} options={Object.entries(sorts).map(([value, label]) => ({ value, label }))} />}
          </Field>
          {region === "IN" && facets.fo != null && (
            <CheckField checked={filters.fo} onChange={(on) => set({ fo: on })} label={<>F&amp;O stocks only ({facets.fo})
              <Info label="About F&O stocks">The stocks the exchange trades futures and options in, from its lot-size file.</Info></>} />
          )}
        </div>
      )}
      {search}
    </Card>
  );
}
