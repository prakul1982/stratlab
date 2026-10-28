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

/** A floating panel dragged by `dx`, `dy`, kept inside the window. */
export function dragged(l: PanelLayout, dx: number, dy: number, vw: number, vh: number): PanelLayout {
  const x0 = l.x ?? vw - l.w - 16, y0 = l.y ?? vh - l.h - 16;
  return { ...l, x: Math.max(0, Math.min(vw - l.w, Math.round(x0 + dx))), y: Math.max(0, Math.min(vh - l.h, Math.round(y0 + dy))) };
}

/** A panel resized from its left (docked) or top-left (floating) edge by `dx`, `dy`: dragging left or up makes it bigger. */
export function resized(l: PanelLayout, dx: number, dy: number, vw: number, vh: number): PanelLayout {
  const maxW = Math.max(MIN_W, Math.min(MAX_W, vw - 80)), maxH = Math.max(MIN_H, vh - 32);
  const w = Math.max(MIN_W, Math.min(maxW, Math.round(l.w - dx)));
  if (l.mode === "dock") return { ...l, w };
  const h = Math.max(MIN_H, Math.min(maxH, Math.round(l.h - dy)));
  const x0 = l.x ?? vw - l.w - 16, y0 = l.y ?? vh - l.h - 16;
  return { ...l, w, h, x: Math.max(0, x0 + (l.w - w)), y: Math.max(0, y0 + (l.h - h)) };
}
