/* f4: a theme's change log ("What changed", theme_changes.py) in words: each stored read of the theme set against the one before it.
 * Pure, no React: the unit tests read it as it is. */

export type ChangeCo = { symbol: string; name: string; layer?: string; why?: string; from?: string; to?: string };
/** c54: a removed layer says where its companies went ({layer: n}, "" out of the theme) and, when the placement said it, why it was not kept. */
export type LayerChange = { kind: "renamed" | "split" | "merged" | "added" | "removed"; from: string[]; to: string[]; n: number; went?: Record<string, number>; why?: string };
export type Restated = { symbol: string; name: string; year: string; revenue: [number | null, number | null]; margin: [number | null, number | null]; measure: string; what: ("revenue" | "margin")[] };
export type ChangeCounts = { removed: number; added: number; moved: number; layers: number; restated: number };
export type ChangeEntry = { at: string; d: string; cause: "rules" | "map" | "refresh" | "figures"; counts: ChangeCounts;
  removed: ChangeCo[]; added: ChangeCo[]; moved: ChangeCo[]; layers: LayerChange[]; restated: Restated[]; hidden?: number };
/** What the dive carries: every entry newest first (Basic and up), else the latest one cut to its first rows, and how many are older. */
export type ChangeLog = { full: boolean; since: string | null; entries: ChangeEntry[]; older: number };

export const CAUSE_WORDS: Record<ChangeEntry["cause"], string> = {
  rules: "Re-checked under new placement rules", map: "New map of the theme", refresh: "Refresh", figures: "Companies' figures updated",
};
const LAYER_WORDS: Record<LayerChange["kind"], string> = { renamed: "Layer renamed", split: "Layer split", merged: "Layers merged", added: "Layer added", removed: "Layer removed" };

const n = (k: number, one: string, many: string) => `${k.toLocaleString("en-IN")} ${k === 1 ? one : many}`;

/** The entry's counts in one line: "2 companies added, 1 removed, 3 moved between layers, 1 layer change, 4 restated figures". */
export function countsLine(c: ChangeCounts): string {
  const parts = [
    c.added ? `${n(c.added, "company", "companies")} added` : "",
    c.removed ? `${n(c.removed, "company", "companies")} removed` : "",
    c.moved ? `${n(c.moved, "company", "companies")} moved between layers` : "",
    c.layers ? n(c.layers, "layer change", "layer changes") : "",
    c.restated ? `${n(c.restated, "company's", "companies'")} figures restated` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : "No change";
}

export type ChangeRow = { key: string; change: string; company: string; detail: string };

const money = (v: number | null) => (v == null ? "–" : v.toLocaleString("en-IN", { maximumFractionDigits: 0 }));
const pct = (v: number | null) => (v == null ? "–" : `${v.toFixed(1).replace("-", "−")}%`);

/** An entry's rows, as the table and the workbook list them: removed, added, moved, layer changes, restated figures. */
export function changeRows(e: ChangeEntry, unit: string): ChangeRow[] {
  const rows: ChangeRow[] = [];
  for (const c of e.removed ?? []) rows.push({ key: `r-${c.symbol}`, change: "Removed", company: c.name, detail: `From ${c.layer}: ${c.why}` });
  for (const c of e.added ?? []) rows.push({ key: `a-${c.symbol}`, change: "Added", company: c.name, detail: `To ${c.layer}` });
  for (const c of e.moved ?? []) rows.push({ key: `m-${c.symbol}`, change: "Moved", company: c.name, detail: `${c.from} → ${c.to}${c.why ? `: ${c.why}` : ""}` });
  (e.layers ?? []).forEach((x, i) => rows.push({ key: `l-${i}`, change: LAYER_WORDS[x.kind] ?? x.kind, company: "",
    detail: x.kind === "added" ? `${x.to.join(", ")} (${n(x.n, "company", "companies")})` : x.kind === "removed" ? removedDetail(x)
      : `${x.from.join(" + ")} → ${x.to.join(" + ")} (${n(x.n, "company", "companies")})` }));
  for (const c of e.restated ?? []) {
    const bits = (c.what ?? []).map((w) => (w === "revenue" ? `revenue ${money(c.revenue[0])} → ${money(c.revenue[1])} ${unit}` : `${c.measure || "Margin"} ${pct(c.margin[0])} → ${pct(c.margin[1])}`));
    rows.push({ key: `s-${c.symbol}`, change: "Figures restated", company: c.name, detail: `${c.year}: ${bits.join("; ")}` });
  }
  return rows;
}

/** c54: "Aluminium (14 companies: 12 to Other, 2 to Steel pipes), none restored: ..." — a lost layer with where its companies went and why. */
export function removedDetail(x: LayerChange): string {
  const went = Object.entries(x.went ?? {}).slice(0, 4).map(([k, v]) => (k ? `${v.toLocaleString("en-IN")} to ${k}` : `${v.toLocaleString("en-IN")} out of the theme`));
  return `${x.from.join(", ")} (${n(x.n, "company", "companies")}${went.length ? `: ${went.join(", ")}` : ""})${x.why ? `, ${x.why}` : ""}`;
}

/** The lock's words for a plan without the whole log: what is shown and what Basic adds. */
export function changesLockLine(log: ChangeLog): string {
  const more = (log.entries[0]?.hidden ?? 0) > 0 || log.older > 0;
  return more ? `The full change log${log.older ? `, with ${n(log.older, "earlier refresh", "earlier refreshes")},` : ""} is on the Basic plan. Free shows the latest refresh's counts and its first 5 changes.`
    : "The full change log, with every earlier refresh, is on the Basic plan. Free shows the latest refresh's counts and its first 5 changes.";
}
