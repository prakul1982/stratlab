/* Saving a chart's drawings and layout: this browser at once (so a reload or a dropped connection loses nothing), the
 * account a moment later (so they come back on any device). Offline-safe: every storage call is wrapped, a failed save
 * stays marked unsent and goes out on the next change, the next load or when the connection returns. */
import { api } from "../../lib/api";
import { cleanDrawings, splitKey, type Drawing } from "./drawGeo";
import { cleanLayout } from "./drawChoose";

export type { Layout, Saved } from "./drawChoose";
export { cleanLayout } from "./drawChoose";
import type { Layout, Saved } from "./drawChoose";

const LS = "stratlab.pc.dr.";

export function readLocal(key: string): Saved | null {
  try {
    const raw = localStorage.getItem(LS + key);
    if (!raw) return null;
    const v = JSON.parse(raw);
    if (Array.isArray(v)) return { drawings: cleanDrawings(v), layout: null, at: 0, dirty: false, synced: false };          // the first chart's format
    if (!v || typeof v !== "object") return null;
    return { drawings: cleanDrawings(v.drawings), layout: cleanLayout(v.layout), at: Number(v.at) || 0, dirty: v.dirty === true,
      synced: v.synced === true || (v.synced === undefined && v.dirty !== true && Number(v.at) > 0) };          // a copy saved before this flag: sent when not dirty
  } catch { return null; }
}

export function writeLocal(key: string, s: Saved): void {
  try { localStorage.setItem(LS + key, JSON.stringify(s)); } catch { /* private window or full: the account copy still saves */ }
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

/** Sends the copy. `refused` is the server's own message when it turned the copy down for good (too big), else null. */
export async function pushRemote(key: string, drawings: Drawing[], layout: Layout | null): Promise<{ ok: boolean; refused: string | null }> {
  const { region, symbol } = splitKey(key);
  try {
    await api(`/me/drawings/${encodeURIComponent(region)}/${encodeURIComponent(symbol)}`, { method: "PUT", body: { drawings, layout } });
    return { ok: true, refused: null };
  } catch (e) {
    const x = e as { status?: number; code?: string; message?: string };
    // refused for good: too big (413), or past the plan's limit on charts or indicators (402): the server's own words are shown
    return { ok: false, refused: x.status === 413 || x.code === "drawings_too_big" || x.code === "plan_limit" ? (x.message || "There are too many drawings on this chart to save.") : null };
  }
}

export { choose } from "./drawChoose";
