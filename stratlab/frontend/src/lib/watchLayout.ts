/* Where Market Watch's panel is and how big, kept on this device (MW-1): open or shut, docked to the right edge or floating, its
 * size and place, the list and sort last used, and the chart last open in it. Pure (no page, no storage) apart from the key, so
 * the unit tests run it; the panel reads and writes it through usePersisted. */
import type { SortMode } from "./watch";
import { LAYOUT_KEY, isSheet } from "./watchKey";

export type PanelMode = "dock" | "float";
export interface PanelLayout {
  open: boolean; mode: PanelMode; w: number; h: number;
  /** Floating: the panel's top-left corner, px from the window's top-left (null: docked to the bottom-right corner). */
  x: number | null; y: number | null;
  list: string | null; sort: SortMode;
  /** The chart open in the panel, as "MARKET:SYMBOL" (null: the list). */
  chart: string | null;
}

export { LAYOUT_KEY, isSheet };
export const MIN_W = 300, MAX_W = 720, MIN_H = 320;
export const DEFAULT_LAYOUT: PanelLayout = { open: false, mode: "dock", w: 380, h: 560, x: null, y: null, list: null, sort: "custom", chart: null };


const num = (v: unknown, lo: number, hi: number, d: number): number => (typeof v === "number" && Number.isFinite(v) ? Math.max(lo, Math.min(hi, Math.round(v))) : d);

/** A saved layout made safe: unknown values dropped, sizes and place kept inside the window (a window that got smaller, or a
 * layout saved on a bigger screen). */
export function clampLayout(raw: unknown, vw: number, vh: number): PanelLayout {
  const r = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const maxW = Math.max(MIN_W, Math.min(MAX_W, vw - 80)), maxH = Math.max(MIN_H, vh - 32);
  const w = num(r.w, MIN_W, maxW, DEFAULT_LAYOUT.w), h = num(r.h, MIN_H, maxH, DEFAULT_LAYOUT.h);
  const float = r.mode === "float";
  return {
    open: r.open === true, mode: float ? "float" : "dock", w, h,
    x: float && typeof r.x === "number" ? num(r.x, 0, Math.max(0, vw - w), vw - w - 16) : null,
    y: float && typeof r.y === "number" ? num(r.y, 0, Math.max(0, vh - h), vh - h - 16) : null,
    list: typeof r.list === "string" && r.list.length <= 60 ? r.list : null,
    sort: r.sort === "change_desc" || r.sort === "change_asc" || r.sort === "name" ? r.sort : "custom",
    chart: typeof r.chart === "string" && /^[A-Z]{2,6}:[A-Za-z0-9^&._=-]{1,40}$/.test(r.chart) ? r.chart : null,
  };
}

/** A docked panel takes its width from the page, and a page drawn for a wide window is only right while it keeps about 1200px: under
 * this window width a "docked" panel floats in the bottom-right corner instead and the page is left as it is (found by the layout
 * lint, which showed pages built for a desktop window breaking at a docked panel's width). */
export const DOCK_FROM = 1600;

export type PanelShape = "sheet" | "dock" | "float";
/** How the panel is drawn at this window width. */
export const shapeOf = (l: PanelLayout, vw: number): PanelShape => (isSheet(vw) ? "sheet" : l.mode === "dock" && vw >= DOCK_FROM ? "dock" : "float");

/** The panel's width a docked panel takes from the page (0 when shut, floating, or a sheet). */
export function dockWidth(l: PanelLayout, vw: number): number {
  return l.open && shapeOf(l, vw) === "dock" ? Math.min(l.w, vw - 320) : 0;
}

/** The panel's height as drawn. A "docked" panel on a window too narrow to dock floats in the corner over the page: there it is at
 * most half the window high, so the page's top half (its heading and each card's buttons) stays clear (Instinct #11, 2 Nov: at 560px
 * on a 720px laptop it stood over the alerts page's New alert button and took its clicks). A panel the person floated keeps the
 * height they gave it. */
export function drawnHeight(l: PanelLayout, vw: number, vh: number): number {
  const h = Math.max(MIN_H, l.h);
  return l.mode === "dock" && shapeOf(l, vw) === "float" ? Math.max(MIN_H, Math.min(h, Math.round(vh / 2))) : h;
}

/** How much of the window's foot a panel floating in its corner stands over (0 when shut, docked, a sheet or moved elsewhere): the
 * page leaves that much room after its end, so its last lines scroll clear of the panel instead of staying under it. */
export function cornerCover(l: PanelLayout, vw: number, vh: number): number {
  return l.open && shapeOf(l, vw) === "float" && l.y == null ? drawnHeight(l, vw, vh) + 16 : 0;
}

/** A floating panel dragged by `dx`, `dy`, kept inside the window. */
export function dragged(l: PanelLayout, dx: number, dy: number, vw: number, vh: number): PanelLayout {
  const x0 = l.x ?? vw - l.w - 16, y0 = l.y ?? vh - l.h - 16;
  return { ...l, x: Math.max(0, Math.min(vw - l.w, Math.round(x0 + dx))), y: Math.max(0, Math.min(vh - l.h, Math.round(y0 + dy))) };
}

/** The edges and corners a floating panel is resized from (owner, 9 Nov: "why is this only extendable from one top corner"). */
export type Edge = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";
export const EDGES: Edge[] = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];

const within = (v: number, lo: number, hi: number): number => Math.round(Math.max(lo, Math.min(hi, v)));

/** A panel resized by `dx`, `dy` from one of its edges or corners: that edge follows the pointer and the opposite one stays where it
 * is. Never smaller than MIN_W by MIN_H, never wider than MAX_W or the window, and never past the window's edge. A docked panel has
 * only its left edge (dragging left makes it wider); a floating one is sized from its top-left corner unless told which edge. */
export function resized(l: PanelLayout, dx: number, dy: number, vw: number, vh: number, edge: Edge = "nw"): PanelLayout {
  const maxW = Math.max(MIN_W, Math.min(MAX_W, vw - 80)), maxH = Math.max(MIN_H, vh - 32);
  if (l.mode === "dock") return { ...l, w: within(l.w - dx, MIN_W, maxW) };
  const x0 = l.x ?? vw - l.w - 16, y0 = l.y ?? vh - l.h - 16;
  let left = x0, top = y0, right = x0 + l.w, bottom = y0 + l.h;
  if (edge.includes("w")) left = within(left + dx, Math.max(0, right - maxW), right - MIN_W);
  if (edge.includes("e")) right = within(right + dx, left + MIN_W, Math.max(left + MIN_W, Math.min(vw, left + maxW)));
  if (edge.includes("n")) top = within(top + dy, Math.max(0, bottom - maxH), bottom - MIN_H);
  if (edge.includes("s")) bottom = within(bottom + dy, top + MIN_H, Math.max(top + MIN_H, Math.min(vh, top + maxH)));
  return { ...l, w: Math.round(right - left), h: Math.round(bottom - top), x: Math.max(0, Math.round(left)), y: Math.max(0, Math.round(top)) };
}
