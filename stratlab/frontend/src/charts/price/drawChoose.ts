/* Which copy of a chart's drawings to show, local or the account's. No network here, so it can be tested alone. */
import type { Drawing } from "./drawGeo";

export interface SavedStudy { id: string; type: string; params: number[]; slot: number }
export interface Layout { tf?: string; range?: string; type?: string; volume?: boolean; hide_drawings?: boolean; studies?: { id: string; type: string; params: number[]; slot: number }[] }
/** `synced`: the account has held this copy (it was sent, or it came from the account). */
export interface Saved { drawings: Drawing[]; layout: Layout | null; at: number; dirty: boolean; synced?: boolean }

/** Which copy to show: an unsent local one newer than the account's wins (and is sent); otherwise the account's.
 *  A copy the account already held loses to an emptied account: another device cleared it. */
export function choose(local: Saved | null, remote: { drawings: Drawing[]; layout: Layout | null; at: number } | null):
  { use: { drawings: Drawing[]; layout: Layout | null }; send: boolean } {
  const has = (s: { drawings: Drawing[]; layout: Layout | null } | null) => !!s && (s.drawings.length > 0 || !!s.layout);
  if (!remote) return { use: local ?? { drawings: [], layout: null }, send: false };
  if (local && has(local) && (local.dirty ? local.at >= remote.at : !has(remote) && !local.synced)) return { use: local, send: true };
  if (local?.dirty && !has(local) && local.at >= remote.at) return { use: local, send: true };          // everything was deleted offline
  return { use: remote, send: false };
}

const TFS = ["1m", "3m", "5m", "10m", "15m", "30m", "1h", "2h", "4h", "1d", "1w", "1mo"];
const RANGES = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "All"];
const TYPES = ["candles", "hollow", "heikin", "bars", "line", "area", "baseline"];

/** A layout with only what the chart understands. */
export function cleanLayout(v: unknown): Layout | null {
  if (!v || typeof v !== "object") return null;
  const r = v as Record<string, unknown>, out: Layout = {};
  if (typeof r.tf === "string" && TFS.includes(r.tf)) out.tf = r.tf;
  if (typeof r.range === "string" && RANGES.includes(r.range)) out.range = r.range;
  if (typeof r.type === "string" && TYPES.includes(r.type)) out.type = r.type;
  if (typeof r.volume === "boolean") out.volume = r.volume;
  if (typeof r.hide_drawings === "boolean") out.hide_drawings = r.hide_drawings;
  if (Array.isArray(r.studies)) {
    out.studies = r.studies.filter((s): s is SavedStudy => !!s && typeof s === "object" && typeof (s as SavedStudy).id === "string" && typeof (s as SavedStudy).type === "string"
      && Array.isArray((s as SavedStudy).params)).slice(0, 12)
      .map((s) => ({ id: s.id, type: s.type, params: s.params.map(Number).filter(Number.isFinite).slice(0, 4), slot: Number.isInteger(s.slot) ? s.slot : 0 }));
  }
  return Object.keys(out).length ? out : null;
}
