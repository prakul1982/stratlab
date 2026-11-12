/* Import a watchlist (owner, 12 Nov): what was pasted split into lines, what the server's symbol search made of each, and what fits the
 * list under the plan. Free of React so the unit tests read it. The server is backend/app/watch_import.py. */
import type { WatchItem } from "./watch";

/** Lines checked in one go (the server's watch_import.MAX_QUERIES, a list's most symbols). */
export const IMPORT_MAX = 300;

/** The lock on the file import, said in the app's one lock wording (PlanNote) by whoever opens the dialog. */
export const FILE_LOCK = "Importing from a CSV or Excel file, picking its column, is on the Basic plan. Pasting symbols works on every plan.";

export type ImportStatus = "found" | "confirm" | "missing";
export interface ImportRow { query: string; status: ImportStatus; item: WatchItem | null; suggestions: WatchItem[] }
/** A file's column to pick from (watch_import.columns_of). */
export interface ImportColumn { index: number; name: string; sample: string[]; values: string[]; count: number }

/** What was pasted as lines: one a line, or separated by commas, semicolons or tabs; any case; each once (case aside), in order. */
export function splitPasted(text: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of text.split(/[\n\r,;\t]+/)) {
    const s = raw.replace(/\s+/g, " ").trim().replace(/^["'`]+|["'`]+$/g, "").trim();
    if (!s || seen.has(s.toUpperCase())) continue;
    seen.add(s.toUpperCase());
    out.push(s);
    if (out.length >= IMPORT_MAX) break;
  }
  return out;
}

/** The pasted lines and a file's column together, each once. */
export function allQueries(pasted: string[], column: string[]): string[] {
  return splitPasted([...pasted, ...column].join("\n"));
}

/** Which item each row adds: a found row its item, a row to confirm the suggestion picked (the best one unless changed; "" skips it). */
export function chosenItem(row: ImportRow, pick: string | undefined): WatchItem | null {
  if (row.status === "found") return pick === "" ? null : row.item;
  if (row.status === "confirm") {
    if (pick === "") return null;
    return row.suggestions.find((s) => s.id === pick) ?? row.suggestions[0] ?? null;
  }
  return null;
}

/** The items to add, each once and none already on the list, in the order given. */
export function toAdd(rows: ImportRow[], picks: Record<string, string>, onList: Set<string>): WatchItem[] {
  const out: WatchItem[] = [];
  const seen = new Set(onList);
  for (const r of rows) {
    const it = chosenItem(r, picks[r.query]);
    if (it && !seen.has(it.id)) { seen.add(it.id); out.push(it); }
  }
  return out;
}

/** "4 found, 1 to confirm, 1 not found". */
export function summaryLine(rows: ImportRow[]): string {
  const n = (s: ImportStatus) => rows.filter((r) => r.status === s).length;
  return [`${n("found")} found`, n("confirm") ? `${n("confirm")} to confirm` : null, n("missing") ? `${n("missing")} not found` : null].filter(Boolean).join(", ");
}

/** How many of `adding` fit a list holding `used` under a cap of `cap` symbols (null: no limit). */
export function room(cap: number | null, used: number, adding: number): number {
  return cap == null ? adding : Math.max(0, Math.min(adding, cap - used));
}

/** Said plainly when the import would pass the plan's limit; null when everything fits. `next` is the next plan's own words
 * ("Basic keeps 100"). */
export function limitSaid(opts: { cap: number | null; used: number; adding: number; plan: string; list: string; next?: string | null }): string | null {
  const { cap, used, adding, plan, list, next } = opts;
  if (cap == null || used + adding <= cap) return null;
  const fit = room(cap, used, adding);
  const head = `${list} has ${used} of the ${cap} symbols ${plan} keeps in a list`;
  const tail = next ? ` ${next}.` : "";
  return fit === 0
    ? `${head}, so none of these can be added.${tail}`
    : `${head}: ${fit} of these ${adding} fit, so the first ${fit} will be added and the other ${adding - fit} left out.${tail}`;
}

/** The main button's words: "Add 5 to Watchlist", "Add the first 3 to Tech", or nothing to add. */
export function addLabel(adding: number, fit: number, list: string): string {
  if (fit <= 0) return `Nothing to add to ${list}`;
  return fit < adding ? `Add the first ${fit} to ${list}` : `Add ${fit} to ${list}`;
}
