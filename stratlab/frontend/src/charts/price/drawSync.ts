/* Saving a chart's drawings and layout: this browser at once (so a reload or a dropped connection loses nothing), the
 * account a moment later (so they come back on any device). Offline-safe: every storage call is wrapped, a failed save
 * stays marked unsent and goes out on the next change, the next load or when the connection returns. */
import { api } from "../../lib/api";
import { cleanDrawings, splitKey, type Drawing } from "./drawGeo";

export interface SavedStudy { id: string; type: string; params: number[]; slot: number }
export interface Layout { tf?: string; range?: string; type?: string; volume?: boolean; hide_drawings?: boolean; studies?: SavedStudy[] }
export interface Saved { drawings: Drawing[]; layout: Layout | null; at: number; dirty: boolean }

const LS = "stratlab.pc.dr.";
const TFS = ["5m", "15m", "1h", "1d", "1w", "1mo"];
const RANGES = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "All"];
const TYPES = ["candles", "hollow", "heikin", "bars", "line", "area", "baseline"];

export function readLocal(key: string): Saved | null {
  try {
    const raw = localStorage.getItem(LS + key);
    if (!raw) return null;
    const v = JSON.parse(raw);
    if (Array.isArray(v)) return { drawings: cleanDrawings(v), layout: null, at: 0, dirty: false };          // the first chart's format
    if (!v || typeof v !== "object") return null;
    return { drawings: cleanDrawings(v.drawings), layout: cleanLayout(v.layout), at: Number(v.at) || 0, dirty: v.dirty === true };
  } catch { return null; }
}

export function writeLocal(key: string, s: Saved): void {
  try { localStorage.setItem(LS + key, JSON.stringify(s)); } catch { /* private window or full: the account copy still saves */ }
}

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

interface Remote { drawings?: unknown; layout?: unknown; updated_at?: string | null }

/** The account's copy, or null when it can't be reached (signed out, offline). */
export async function fetchRemote(key: string): Promise<{ drawings: Drawing[]; layout: Layout | null; at: number } | null> {
  const { region, symbol } = splitKey(key);
  try {
    const r = await api<Remote>(`/me/drawings/${encodeURIComponent(region)}/${encodeURIComponent(symbol)}`);
    return { drawings: cleanDrawings(r?.drawings), layout: cleanLayout(r?.layout), at: r?.updated_at ? Date.parse(r.updated_at) || 0 : 0 };
  } catch { return null; }
}

export async function pushRemote(key: string, drawings: Drawing[], layout: Layout | null): Promise<boolean> {
  const { region, symbol } = splitKey(key);
  try {
    await api(`/me/drawings/${encodeURIComponent(region)}/${encodeURIComponent(symbol)}`, { method: "PUT", body: { drawings, layout } });
    return true;
  } catch { return false; }
}

/** Which copy to show: an unsent local one newer than the account's wins (and is sent); otherwise the account's. */
export function choose(local: Saved | null, remote: { drawings: Drawing[]; layout: Layout | null; at: number } | null):
  { use: { drawings: Drawing[]; layout: Layout | null }; send: boolean } {
  const has = (s: { drawings: Drawing[]; layout: Layout | null } | null) => !!s && (s.drawings.length > 0 || !!s.layout);
  if (!remote) return { use: local ?? { drawings: [], layout: null }, send: false };
  if (local && has(local) && (local.dirty ? local.at >= remote.at : !has(remote))) return { use: local, send: true };
  if (local?.dirty && !has(local) && local.at >= remote.at) return { use: local, send: true };          // everything was deleted offline
  return { use: remote, send: false };
}
