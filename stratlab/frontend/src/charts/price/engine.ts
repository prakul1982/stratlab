/* The price chart engine: candles and lines drawn on a canvas, with a second canvas on top for the crosshair and
 * drawings, so moving the pointer never repaints the candles. Repaints are batched into animation frames and only
 * happen when something changed. Only the bars on screen are drawn; when they are thinner than ~1.5 px they are
 * merged into one candle per group so a long history pans as fast as a short one. */
import { DRAW_TOOLS, hitDrawing, paintDrawing, type Drawing, type DrawingKind, type Mapper } from "./drawings";
import { attachGestures } from "./interaction";
import { stepDecimals, TimeScale, timeLabel, timeTicks, ValueScale, type ScaleMode } from "./scales";
import { compute, type StudyConfig, type StudyLine, type StudyOutput } from "./studies";
import { heikinAshi, indexAtOrBefore, type Bar } from "./transforms";

export type ChartType = "candles" | "hollow" | "heikin" | "bars" | "line" | "area" | "baseline";
export const CHART_TYPES: { type: ChartType; name: string }[] = [
  { type: "candles", name: "Candles" }, { type: "hollow", name: "Hollow candles" }, { type: "heikin", name: "Heikin-Ashi" },
  { type: "bars", name: "OHLC bars" }, { type: "line", name: "Line" }, { type: "area", name: "Area" }, { type: "baseline", name: "Baseline" },
];

export interface ChartMarker { t: number; side: "buy" | "sell"; text?: string }
export interface PriceLevel { price: number; label: string; tone: "up" | "down" | "muted" }
export interface Theme {
  bg: string; text: string; muted: string; grid: string; border: string; ink: string;
  up: string; down: string; onUp: string; onDown: string; accent: string; slots: string[]; font: string;
}
export interface Compare { label: string; bars: Bar[] }
export interface Hover { index: number; bar: Bar; prev: Bar | null; x: number; compare: number | null }

type Listener = { crosshair: (h: Hover | null) => void; view: () => void; drawings: (d: Drawing[]) => void; select: (id: string | null) => void; tool: (t: DrawingKind | null) => void };

const AXIS_H = 24;
const LINE_TYPES = new Set<ChartType>(["line", "area", "baseline"]);

interface Pane { kind: "price" | "study"; study?: StudyOutput; top: number; height: number; scale: ValueScale }

export class PriceChartEngine {
  readonly host: HTMLElement;
  private main: HTMLCanvasElement;
  private over: HTMLCanvasElement;
  private mc: CanvasRenderingContext2D;
  private oc: CanvasRenderingContext2D;
  private dpr = 1;
  private W = 0;
  private H = 0;
  private axisW = 64;
  readonly time = new TimeScale();
  readonly price = new ValueScale();
  private panes: Pane[] = [];
  bars: Bar[] = [];
  private shown: Bar[] = [];
  private walls: number[] = [];
  type: ChartType = "candles";
  auto = true;
  volume = true;
  intraday = false;
  private configs: StudyConfig[] = [];
  studies: StudyOutput[] = [];
  private markers: ChartMarker[] = [];
  private levels: PriceLevel[] = [];
  private compare: { label: string; values: number[] } | null = null;
  private compareBars: Bar[] = [];
  drawings: Drawing[] = [];
  selected: string | null = null;
  tool: DrawingKind | null = null;
  /** When set, a click on the price pane hands its price to this instead of drawing or selecting (chart replay's
   *  stop and target lines). */
  picker: ((price: number) => void) | null = null;
  private draft: { d: Drawing; pending: boolean; moved: boolean } | null = null;
  private moving: { id: string; handle: number | null; from: { t: number; p: number }; orig: Drawing } | null = null;
  private axisDrag: { kind: "price" | "time"; x: number; y: number } | null = null;
  private cross: { x: number; y: number } | null = null;
  private hoverIndex = -1;
  private theme: Theme;
  private format: (v: number, decimals: number) => string;
  askText: (initial: string) => string | null = (s) => window.prompt("Note text", s);
  private dirtyMain = true;
  private dirtyOver = true;
  private frame = 0;
  private on: Partial<Listener> = {};
  private detach: () => void;
  private ro: ResizeObserver;
  private viewSet = false;

  constructor(host: HTMLElement, theme: Theme, format: (v: number, decimals: number) => string) {
    this.host = host;
    this.theme = theme;
    this.format = format;
    this.main = document.createElement("canvas");
    this.over = document.createElement("canvas");
    for (const c of [this.main, this.over]) {
      c.setAttribute("aria-hidden", "true");
      c.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;display:block";
      host.appendChild(c);
    }
    this.over.style.cursor = "crosshair";
    this.mc = this.main.getContext("2d")!;
    this.oc = this.over.getContext("2d")!;
    this.detach = attachGestures(this.over, {
      down: (x, y, e) => this.down(x, y, e),
      drag: (x, y) => this.dragTo(x, y),
      drop: (x, y) => this.dropAt(x, y),
      pan: (dx, dy) => this.panBy(dx, dy),
      panEnd: () => this.emitView(),
      zoom: (f, x) => { this.time.zoom(f, Math.min(x, this.plotW())); this.clampView(); this.invalidate(); this.emitView(); },
      hover: (x, y) => this.hover(x, y),
      leave: () => { this.cross = null; this.setHover(-1); this.invalidate(false); },
      tap: (x, y, e) => { if (e.pointerType !== "mouse") this.hover(x, y); },
      reset: () => this.resetView(),
    });
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(host);
    this.resize();
  }

  destroy(): void {
    cancelAnimationFrame(this.frame);
    this.detach();
    this.ro.disconnect();
    this.main.remove();
    this.over.remove();
  }

  listen<K extends keyof Listener>(k: K, fn: Listener[K]): void {
    this.on[k] = fn;
  }

  // ---------- data ----------
  setData(bars: Bar[], keepView = false): void {
    const lastT = this.bars.length ? this.bars[this.bars.length - 1].t : null;
    const right = this.time.right - (this.bars.length - 1);
    this.bars = bars;
    this.rebuild();
    if (keepView && this.viewSet && lastT != null) this.time.right = bars.length - 1 + right;
    else this.resetView(false);
    this.invalidate();
  }

  /** The series again with older bars in front (history scrolled into view), without moving what is on screen. */
  replaceOlder(all: Bar[]): void {
    const oldFirst = this.bars[0]?.t;
    const added = oldFirst == null ? 0 : Math.max(0, indexAtOrBefore(all, oldFirst));
    this.bars = all;
    this.time.right += added;
    this.rebuild();
    this.invalidate();
  }

  /** The live candle: patched in place, or appended when a new one starts. The view follows the newest bar when
   *  it was in sight. */
  update(bar: Bar): void {
    const n = this.bars.length, last = this.bars[n - 1];
    if (last && bar.t < last.t) return;
    const following = this.time.right >= n - 1;
    if (last && bar.t === last.t) this.bars[n - 1] = bar;
    else {
      this.bars.push(bar);
      if (following) this.time.right += 1;
    }
    this.rebuild();
    this.invalidate();
  }

  private rebuild(): void {
    this.shown = this.type === "heikin" ? heikinAshi(this.bars) : this.bars;
    this.walls = this.bars.map((b) => b.w);
    this.studies = this.configs.map((c) => compute(this.bars, c, this.intraday));
    if (this.compareBars.length) this.alignCompare();
    this.layout();
    this.time.minSpacing = Math.max(0.05, Math.min(2, this.plotW() / Math.max(1, this.bars.length) / 1.2));
  }

  setType(t: ChartType): void { this.type = t; this.rebuild(); this.invalidate(); }
  setVolume(on: boolean): void { this.volume = on; this.invalidate(); }
  setScaleMode(m: ScaleMode): void { this.price.mode = m; this.auto = true; this.invalidate(); this.emitView(); }
  setAuto(on: boolean): void { this.auto = on; this.invalidate(); this.emitView(); }
  setStudies(c: StudyConfig[]): void { this.configs = c; this.rebuild(); this.invalidate(); }
  setMarkers(m: ChartMarker[]): void { this.markers = m; this.invalidate(); }
  setLevels(l: PriceLevel[]): void { this.levels = l; this.invalidate(); }
  setTheme(t: Theme): void { this.theme = t; this.invalidate(); }
  setIntraday(on: boolean): void { this.intraday = on; this.rebuild(); this.invalidate(); }

  setCompare(c: Compare | null): void {
    this.compareBars = c?.bars ?? [];
    this.compare = c ? { label: c.label, values: [] } : null;
    if (c) { this.alignCompare(); this.price.mode = "percent"; }
    this.auto = true;
    this.invalidate();
  }

  private alignCompare(): void {
    if (!this.compare) return;
    this.compare.values = this.bars.map((b) => {
      const i = indexAtOrBefore(this.compareBars, b.t);
      return i >= 0 ? this.compareBars[i].c : NaN;
    });
  }

  setDrawings(d: Drawing[]): void { this.drawings = d; this.selected = null; this.invalidate(false); }

  setTool(t: DrawingKind | null): void {
    this.tool = t;
    this.draft = null;
    this.over.style.cursor = t ? "copy" : "crosshair";
    this.on.tool?.(t);
    this.invalidate(false);
  }

  deleteSelected(): boolean {
    if (!this.selected) return false;
    this.drawings = this.drawings.filter((d) => d.id !== this.selected);
    this.select(null);
    this.on.drawings?.(this.drawings);
    this.invalidate(false);
    return true;
  }

  clearDrawings(): void { this.drawings = []; this.select(null); this.on.drawings?.(this.drawings); this.invalidate(false); }

  private select(id: string | null): void {
    if (this.selected === id) return;
    this.selected = id;
    this.on.select?.(id);
  }

  // ---------- view ----------
  plotW(): number { return Math.max(10, this.W - this.axisW); }

  /** Bars on screen, clamped to the data: [first, last]. */
  visibleRange(): [number, number] {
    const [a, b] = this.time.visible();
    return [Math.max(0, a), Math.min(this.bars.length - 1, b)];
  }

  resetView(emit = true): void {
    const n = this.bars.length;
    const want = Math.max(20, Math.min(n, Math.round(this.plotW() / 9)));
    this.time.fit(n - want, n - 1, Math.max(2, Math.round(want * 0.04)));
    this.auto = true;
    this.viewSet = n > 0;
    this.clampView();
    this.invalidate();
    if (emit) this.emitView();
  }

  /** Show the bars from time `from` to the newest one. */
  showFrom(from: number): void {
    const n = this.bars.length;
    if (!n) return;
    const i = Math.max(0, indexAtOrBefore(this.bars, from) + (this.bars[0].t < from ? 1 : 0));
    this.time.fit(Math.min(i, n - 1), n - 1, Math.max(1, Math.round((n - i) * 0.03)));
    this.auto = true;
    this.viewSet = true;
    this.clampView();
    this.invalidate();
    this.emitView();
  }

  zoomBy(f: number): void { this.time.zoom(f, this.plotW()); this.clampView(); this.invalidate(); this.emitView(); }

  private clampView(): void {
    const n = this.bars.length, span = this.plotW() / this.time.spacing;
    this.time.right = Math.min(n - 1 + span * 0.6, Math.max(Math.min(n - 1, 3), this.time.right));
  }

  private panBy(dx: number, dy: number): void {
    if (this.cross && this.cross.x >= 0) this.cross = null;
    this.time.pan(dx);
    if (!this.auto && dy) this.price.pan(dy);
    this.clampView();
    this.invalidate();
    this.emitViewSoon();
  }

  private viewTimer = 0;
  private emitViewSoon(): void {
    if (this.viewTimer) return;
    this.viewTimer = window.setTimeout(() => { this.viewTimer = 0; this.emitView(); }, 120);
  }

  private emitView(): void { this.on.view?.(); }

  // ---------- pointer ----------
  private toPoint(x: number, y: number): { t: number; p: number } {
    return { t: this.timeAt(x), p: this.price.value(y) };
  }

  /** The time under x, between bars or beyond either end (spaced like the bars around it). */
  timeAt(x: number): number {
    const b = this.bars, n = b.length;
    if (!n) return 0;
    const f = this.time.index(x);
    const step = n > 1 ? (b[n - 1].t - b[0].t) / (n - 1) : 86_400_000;
    if (f <= 0) return b[0].t + f * (n > 1 ? b[1].t - b[0].t : step);
    if (f >= n - 1) return b[n - 1].t + (f - (n - 1)) * (n > 1 ? b[n - 1].t - b[n - 2].t : step);
    const i = Math.floor(f);
    return b[i].t + (f - i) * (b[i + 1].t - b[i].t);
  }

  /** x for a time (the inverse of timeAt). */
  xAt(t: number): number {
    const b = this.bars, n = b.length;
    if (!n) return 0;
    if (t <= b[0].t) return this.time.x(n > 1 ? (t - b[0].t) / (b[1].t - b[0].t) : 0);
    if (t >= b[n - 1].t) return this.time.x(n - 1 + (n > 1 ? (t - b[n - 1].t) / (b[n - 1].t - b[n - 2].t) : 0));
    const i = indexAtOrBefore(b, t);
    return this.time.x(i + (t - b[i].t) / (b[i + 1].t - b[i].t));
  }

  private mapper(): Mapper {
    const pane = this.panes[0];
    return { x: (t) => this.xAt(t), y: (p) => this.price.y(p), width: this.plotW(), top: pane?.top ?? 0, bottom: (pane?.top ?? 0) + (pane?.height ?? 0) };
  }

  private inPricePane(y: number): boolean {
    const p = this.panes[0];
    return !!p && y >= p.top && y <= p.top + p.height;
  }

  private down(x: number, y: number, e: PointerEvent): boolean {
    (this.host.closest("[tabindex]") as HTMLElement | null)?.focus({ preventScroll: true });
    if (x > this.plotW()) { this.axisDrag = { kind: "price", x, y }; return true; }
    if (y > this.H - AXIS_H) { this.axisDrag = { kind: "time", x, y }; return true; }
    if (!this.inPricePane(y)) return false;
    if (this.picker) {
      const p = this.price.value(y);
      if (Number.isFinite(p) && p > 0) this.picker(p);
      return true;
    }
    if (this.draft?.pending) {
      this.draft.d.points[1] = this.toPoint(x, y);
      this.finishDraft();
      return true;
    }
    if (this.tool) {
      const def = DRAW_TOOLS.find((d) => d.kind === this.tool)!;
      const pt = this.toPoint(x, y);
      const d: Drawing = { id: `d${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`, kind: this.tool, points: def.points === 2 ? [pt, { ...pt }] : [pt] };
      if (d.kind === "text") {
        const text = this.askText("");
        if (!text) { this.setTool(null); return true; }
        d.text = text.slice(0, 200);
      }
      this.draft = { d, pending: false, moved: false };
      if (def.points === 1) this.finishDraft();
      return true;
    }
    const hit = hitDrawing(this.drawings, x, y, this.mapper(), e.pointerType === "mouse" ? 7 : 14);
    if (hit) {
      this.select(hit.id);
      const orig = this.drawings.find((d) => d.id === hit.id)!;
      this.moving = { id: hit.id, handle: hit.handle, from: this.toPoint(x, y), orig: { ...orig, points: orig.points.map((p) => ({ ...p })) } };
      this.invalidate(false);
      return true;
    }
    if (this.selected) { this.select(null); this.invalidate(false); }
    return false;
  }

  private dragTo(x: number, y: number): void {
    if (this.axisDrag) {
      if (this.axisDrag.kind === "price") {
        this.auto = false;
        this.price.zoom(Math.exp((y - this.axisDrag.y) * 0.006));
      } else {
        this.time.zoom(Math.exp((x - this.axisDrag.x) * 0.006), this.plotW());
        this.clampView();
      }
      this.axisDrag.x = x; this.axisDrag.y = y;
      this.invalidate();
      this.emitViewSoon();
      return;
    }
    if (this.draft) {
      this.draft.moved = true;
      if (this.draft.d.points.length > 1) this.draft.d.points[1] = this.toPoint(x, y);
      this.cross = { x, y };
      this.invalidate(false);
      return;
    }
    if (this.moving) {
      const d = this.drawings.find((q) => q.id === this.moving!.id);
      if (!d) return;
      const now = this.toPoint(x, y), o = this.moving.orig;
      if (this.moving.handle != null) d.points[this.moving.handle] = now;
      else {
        const dt = now.t - this.moving.from.t;
        // move in price by the same screen distance whatever the scale mode
        const dy = y - this.price.y(this.moving.from.p);
        d.points = o.points.map((p) => ({ t: p.t + dt, p: this.price.value(this.price.y(p.p) + dy) }));
      }
      this.invalidate(false);
    }
  }

  private dropAt(x: number, y: number): void {
    if (this.axisDrag) { this.axisDrag = null; this.emitView(); return; }
    if (this.draft) {
      if (this.draft.moved) { this.draft.d.points[1] = this.toPoint(x, y); this.finishDraft(); }
      else this.draft.pending = true;            // a click: the next click places the second point
      return;
    }
    if (this.moving) { this.moving = null; this.on.drawings?.(this.drawings); }
  }

  private finishDraft(): void {
    if (!this.draft) return;
    const d = this.draft.d;
    this.draft = null;
    this.drawings = [...this.drawings, d];
    this.setTool(null);
    this.select(d.id);
    this.on.drawings?.(this.drawings);
    this.invalidate(false);
  }

  private hover(x: number, y: number): void {
    this.cross = { x, y };
    if (this.draft?.pending && this.draft.d.points.length > 1) this.draft.d.points[1] = this.toPoint(x, y);
    const n = this.bars.length;
    this.setHover(n && x <= this.plotW() ? Math.max(0, Math.min(n - 1, Math.round(this.time.index(x)))) : -1);
    this.invalidate(false);
  }

  private setHover(i: number): void {
    if (i === this.hoverIndex) return;
    this.hoverIndex = i;
    this.on.crosshair?.(i < 0 ? null : this.hoverAt(i));
  }

  hoverAt(i: number): Hover | null {
    const bar = this.shown[i];
    if (!bar) return null;
    return { index: i, bar, prev: this.shown[i - 1] ?? null, x: this.time.x(i), compare: this.compare?.values[i] ?? null };
  }

  /** Arrow keys pan, + and - zoom, Delete removes the selected drawing, Esc stops drawing. */
  key(e: KeyboardEvent): boolean {
    const step = Math.max(this.time.spacing, this.plotW() * (e.shiftKey ? 0.5 : 0.1));      // a tenth of the view per press
    switch (e.key) {
      case "ArrowLeft": this.panBy(step, 0); return true;
      case "ArrowRight": this.panBy(-step, 0); return true;
      case "+": case "=": this.zoomBy(1.25); return true;
      case "-": case "_": this.zoomBy(0.8); return true;
      case "Delete": case "Backspace": return this.deleteSelected();
      case "Escape":
        if (this.tool || this.draft) { this.setTool(null); return true; }
        if (this.selected) { this.select(null); this.invalidate(false); return true; }
        return false;
    }
    return false;
  }

  // ---------- layout and painting ----------
  private resize(): void {
    const r = this.host.getBoundingClientRect();
    this.W = Math.max(50, Math.floor(r.width));
    this.H = Math.max(80, Math.floor(r.height));
    this.dpr = Math.min(3, window.devicePixelRatio || 1);
    for (const c of [this.main, this.over]) {
      c.width = Math.round(this.W * this.dpr);
      c.height = Math.round(this.H * this.dpr);
    }
    this.time.width = this.plotW();
    this.layout();
    if (!this.viewSet && this.bars.length) this.resetView(false);
    this.invalidate();
  }

  private layout(): void {
    const own = this.studies.filter((s) => s.pane === "own");
    const free = this.H - AXIS_H;
    const each = own.length ? Math.max(56, Math.min(130, Math.round(free * (own.length > 1 ? 0.18 : 0.22)))) : 0;
    const priceH = Math.max(80, free - each * own.length);
    const old = new Map(this.panes.filter((p) => p.study).map((p) => [p.study!.config.id, p.scale]));
    this.panes = [{ kind: "price", top: 0, height: priceH, scale: this.price }];
    this.price.top = 0; this.price.height = priceH;
    let top = priceH;
    for (const s of own) {
      const scale = old.get(s.config.id) ?? new ValueScale();
      scale.top = top + 6; scale.height = each - 10;
      this.panes.push({ kind: "study", study: s, top, height: each, scale });
      top += each;
    }
  }

  /** Ask for a repaint at the next frame: the candles too, or just the crosshair and drawings. */
  invalidate(main = true): void {
    if (main) this.dirtyMain = true;
    this.dirtyOver = true;
    if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; this.paint(); });
  }

  /** Paint now (for screenshots and tests). */
  paint(): void {
    if (this.dirtyMain) { this.dirtyMain = false; this.paintMain(); }
    if (this.dirtyOver) { this.dirtyOver = false; this.paintOver(); }
  }

  private autoscale(from: number, to: number): void {
    const s = this.shown;
    if (!s.length) return;
    const line = LINE_TYPES.has(this.type);
    const a = Math.max(0, from), b = Math.min(s.length - 1, to);
    this.price.base = s[a]?.c || 1;
    if (!this.auto) return;
    let lo = Infinity, hi = -Infinity;
    for (let i = a; i <= b; i++) {
      const bar = s[i];
      if (line) { lo = Math.min(lo, bar.c); hi = Math.max(hi, bar.c); } else { lo = Math.min(lo, bar.l); hi = Math.max(hi, bar.h); }
    }
    for (const st of this.studies) {
      if (st.pane !== "price" || st.config.type === "hl52") continue;
      for (const l of st.lines) for (let i = a; i <= b; i++) { const v = l.values[i]; if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
    }
    if (this.compare) {
      const cb = this.compareBase(a);
      for (let i = a; i <= b; i++) { const v = this.compareAsPrice(i, cb); if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
    }
    if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
    if (this.price.mode === "log" && lo <= 0) lo = Math.max(hi * 1e-3, 1e-9);
    this.price.fit(lo, hi, 0.1, this.volume ? 0.22 : 0.08);
  }

  private compareBase(from: number): number {
    const v = this.compare!.values;
    for (let i = Math.max(0, from); i < v.length; i++) if (Number.isFinite(v[i])) return v[i];
    return NaN;
  }

  /** The compared symbol's close at bar i, as the main symbol's price with the same % change from the left edge. */
  private compareAsPrice(i: number, base: number): number {
    return this.price.base * (this.compare!.values[i] / base);
  }

  private bucket(): number {
    return this.time.spacing < 1.5 ? Math.ceil(1.5 / this.time.spacing) : 1;
  }

  /** Widen or narrow the price axis to its longest label, keeping the newest bar where it is. True if it changed. */
  private fitAxis(): boolean {
    const c = this.mc;
    c.font = this.theme.font;
    let w = 0;
    for (const p of this.panes) {
      const ticks = p.scale.ticks(p.kind === "price" ? 48 : 30);
      const step = ticks.length > 1 ? Math.abs(p.scale.tf(ticks[1]) - p.scale.tf(ticks[0])) : 1;
      for (const v of ticks) w = Math.max(w, c.measureText(this.axisText(p.scale, v, step)).width);
    }
    const last = this.shown[this.shown.length - 1];
    if (last) w = Math.max(w, c.measureText(this.tagText(last.c)).width);
    for (const l of this.levels) w = Math.max(w, c.measureText(this.tagText(l.price)).width);
    const want = Math.max(this.W < 480 ? 44 : 52, Math.min(120, Math.ceil(w + 14)));
    if (Math.abs(want - this.axisW) < 2) return false;
    this.axisW = want;
    this.time.width = this.plotW();
    return true;
  }

  private paintMain(): void {
    const c = this.mc, th = this.theme;
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    let [from, to] = this.time.visible();
    let a = Math.max(0, from), b = Math.min(this.shown.length - 1, to);
    this.autoscale(a, b);
    for (const p of this.panes) if (p.study) this.scaleStudy(p, a, b);
    if (this.fitAxis()) {
      [from, to] = this.time.visible();
      a = Math.max(0, from); b = Math.min(this.shown.length - 1, to);
      this.autoscale(a, b);
      for (const p of this.panes) if (p.study) this.scaleStudy(p, a, b);
    }
    const W = this.W, H = this.H, pw = this.plotW();
    c.fillStyle = th.bg;
    c.fillRect(0, 0, W, H);
    c.font = th.font;
    // grid
    c.lineWidth = 1;
    c.strokeStyle = th.grid;
    const tt = timeTicks(this.walls, a, b, (i) => this.time.x(i), W < 480 ? 64 : 84);
    c.beginPath();
    for (const t of tt) { const x = Math.round(this.time.x(t.i)) + 0.5; c.moveTo(x, 0); c.lineTo(x, H - AXIS_H); }
    for (const p of this.panes) for (const v of p.scale.ticks(p.kind === "price" ? 48 : 30)) { const y = Math.round(p.scale.y(v)) + 0.5; c.moveTo(0, y); c.lineTo(pw, y); }
    c.stroke();
    // price pane
    const pp = this.panes[0];
    if (pp && b >= a) {
      c.save();
      c.beginPath(); c.rect(0, pp.top, pw, pp.height); c.clip();
      if (this.volume) this.paintVolume(a, b, pp);
      this.paintSeries(a, b);
      for (const st of this.studies) if (st.pane === "price") this.paintStudy(st, this.price, a, b);
      if (this.compare) this.paintCompare(a, b);
      this.paintLevels();
      this.paintMarkers(a, b);
      c.restore();
    }
    for (const p of this.panes) {
      if (!p.study || b < a) continue;
      c.save();
      c.beginPath(); c.rect(0, p.top, pw, p.height); c.clip();
      this.paintStudy(p.study, p.scale, a, b);
      c.restore();
    }
    // separators and axes
    c.strokeStyle = th.border;
    c.beginPath();
    for (const p of this.panes.slice(1)) { c.moveTo(0, Math.round(p.top) + 0.5); c.lineTo(W, Math.round(p.top) + 0.5); }
    c.moveTo(Math.round(pw) + 0.5, 0); c.lineTo(Math.round(pw) + 0.5, H);
    c.moveTo(0, H - AXIS_H + 0.5); c.lineTo(W, H - AXIS_H + 0.5);
    c.stroke();
    c.fillStyle = th.bg;
    c.fillRect(pw + 1, 0, W - pw - 1, H);
    c.fillRect(0, H - AXIS_H + 1, W, AXIS_H - 1);
    c.fillStyle = th.muted;
    c.textBaseline = "middle"; c.textAlign = "left";
    for (const p of this.panes) {
      const ticks = p.scale.ticks(p.kind === "price" ? 48 : 30);
      const step = ticks.length > 1 ? Math.abs(p.scale.tf(ticks[1]) - p.scale.tf(ticks[0])) : 1;
      for (const v of ticks) {
        const y = p.scale.y(v);
        if (y < p.top + 6 || y > p.top + p.height - 6) continue;
        c.fillText(this.axisText(p.scale, v, step), pw + 6, y);
      }
    }
    c.textAlign = "center";
    for (const t of tt) {
      const x = this.time.x(t.i);
      if (x < 16 || x > pw - 16) continue;
      c.fillStyle = t.major ? th.text : th.muted;
      c.fillText(t.label, x, H - AXIS_H / 2);
    }
    // the last price, on the axis
    const last = this.shown[this.shown.length - 1];
    if (last && pp) {
      const prev = this.shown[this.shown.length - 2];
      const up = !prev || last.c >= prev.c;
      const y = this.price.y(last.c);
      if (y >= pp.top && y <= pp.top + pp.height) {
        c.strokeStyle = up ? th.up : th.down;
        c.setLineDash([2, 3]);
        c.beginPath(); c.moveTo(0, Math.round(y) + 0.5); c.lineTo(pw, Math.round(y) + 0.5); c.stroke();
        c.setLineDash([]);
        this.axisTag(y, this.tagText(last.c), up ? th.up : th.down, up ? th.onUp : th.onDown);
      }
    }
    for (const l of this.levels) {
      const y = this.price.y(l.price);
      if (y >= pp.top && y <= pp.top + pp.height) this.axisTag(y, this.tagText(l.price), this.tone(l.tone), l.tone === "muted" ? th.bg : l.tone === "up" ? th.onUp : th.onDown);
    }
  }

  /** A price with the decimals its size (or the size of `like`, for a change in price) needs. */
  priceText(v: number, like = v): string {
    const a = Math.abs(like);
    return this.format(v, a >= 1 ? 2 : a >= 0.01 ? 4 : 6);
  }

  /** A price on the axis's coloured tag: exact, or its % in percent mode. */
  private tagText(v: number): string {
    return this.price.mode === "percent" ? this.axisText(this.price, v, 0.01) : this.priceText(v);
  }

  private tone(t: "up" | "down" | "muted"): string {
    return t === "up" ? this.theme.up : t === "down" ? this.theme.down : this.theme.muted;
  }

  private priceStep(): number {
    const t = this.price.ticks(48);
    return t.length > 1 ? Math.abs(this.price.tf(t[1]) - this.price.tf(t[0])) / 10 : 0.01;
  }

  private axisText(s: ValueScale, v: number, step: number): string {
    if (s.mode === "percent") return `${this.format(s.tf(v), stepDecimals(step))}%`;
    const d = s.mode === "log" ? Math.max(0, Math.min(6, 2 - Math.floor(Math.log10(Math.abs(v) || 1)))) : stepDecimals(step);
    return this.format(v, Math.min(d, Math.abs(v) >= 1000 ? 1 : 6));
  }

  private axisTag(y: number, text: string, bg: string, fg: string): void {
    const c = this.mc, pw = this.plotW();
    c.fillStyle = bg;
    c.beginPath();
    c.roundRect?.(pw + 1, y - 10, this.W - pw - 2, 20, 3);
    if (!c.roundRect) c.rect(pw + 1, y - 10, this.W - pw - 2, 20);
    c.fill();
    c.fillStyle = fg;
    c.textAlign = "left"; c.textBaseline = "middle";
    c.fillText(text, pw + 6, y);
  }

  private paintVolume(a: number, b: number, pane: Pane): void {
    const c = this.mc, th = this.theme, k = this.bucket();
    let max = 0;
    for (let i = a; i <= b; i++) max = Math.max(max, this.bars[i]?.v ?? 0);
    if (!max) return;
    const h = pane.height * 0.18, base = pane.top + pane.height;
    const w = Math.max(1, this.time.spacing * k * 0.7);
    const up = new Path2D(), dn = new Path2D();
    for (let i = a - (a % k); i <= b; i += k) {
      let v = 0, o = NaN, cl = NaN;
      for (let j = Math.max(0, i); j < i + k && j < this.bars.length; j++) { const x = this.bars[j]; v += x.v; if (Number.isNaN(o)) o = x.o; cl = x.c; }
      if (!v) continue;
      const bh = (v / (max * k)) * h, x = this.time.x(i + (k - 1) / 2);
      (cl >= o ? up : dn).rect(Math.round(x - w / 2), base - bh, Math.max(1, Math.round(w)), bh);
    }
    c.globalAlpha = 0.32;
    c.fillStyle = th.up; c.fill(up);
    c.fillStyle = th.down; c.fill(dn);
    c.globalAlpha = 1;
  }

  /** Bars i..i+k-1 merged into one candle. */
  private merged(i: number, k: number): Bar | null {
    const s = this.shown;
    if (k === 1) return s[i] ?? null;
    let out: Bar | null = null;
    for (let j = Math.max(0, i); j < i + k && j < s.length; j++) {
      const x = s[j];
      if (!out) out = { ...x }; else { out.h = Math.max(out.h, x.h); out.l = Math.min(out.l, x.l); out.c = x.c; }
    }
    return out;
  }

  private paintSeries(a: number, b: number): void {
    const c = this.mc, th = this.theme, s = this.shown, k = this.bucket(), ps = this.price;
    const sp = this.time.spacing * k;
    if (LINE_TYPES.has(this.type)) { this.paintLine(a, b); return; }
    const body = sp >= 3 ? Math.max(1, Math.floor(sp * 0.72) | 1) : Math.max(1, sp * 0.8);
    const upFill = new Path2D(), dnFill = new Path2D(), upStroke = new Path2D(), dnStroke = new Path2D(), upWick = new Path2D(), dnWick = new Path2D();
    const start = a - (a % k);
    for (let i = start; i <= b; i += k) {
      const bar = this.merged(i, k);
      if (!bar) continue;
      const prevC = s[i - 1]?.c ?? bar.o;
      const x = Math.round(this.time.x(i + (k - 1) / 2)) + 0.5;
      const yo = ps.y(bar.o), yc = ps.y(bar.c), yh = ps.y(bar.h), yl = ps.y(bar.l);
      if (this.type === "bars") {
        const up = bar.c >= bar.o;
        const p = up ? upWick : dnWick, tick = Math.max(1, Math.round(sp * 0.36));
        p.moveTo(x, yh); p.lineTo(x, yl);
        p.moveTo(x - tick, Math.round(yo) + 0.5); p.lineTo(x, Math.round(yo) + 0.5);
        p.moveTo(x, Math.round(yc) + 0.5); p.lineTo(x + tick, Math.round(yc) + 0.5);
        continue;
      }
      const hollow = this.type === "hollow";
      const up = hollow ? bar.c >= prevC : bar.c >= bar.o;
      const wick = up ? upWick : dnWick;
      const top = Math.min(yo, yc), bot = Math.max(yo, yc);
      wick.moveTo(x, yh); wick.lineTo(x, top);
      wick.moveTo(x, bot); wick.lineTo(x, yl);
      const bx = Math.round(x - body / 2), bh = Math.max(1, Math.round(bot - top));
      if (hollow && bar.c > bar.o && body >= 3) (up ? upStroke : dnStroke).rect(bx + 0.5, Math.round(top) + 0.5, body - 1, Math.max(1, bh - 1));
      else (up ? upFill : dnFill).rect(bx, Math.round(top), body, bh);
      if (body < 2) { wick.moveTo(x, top); wick.lineTo(x, bot); }
    }
    c.lineWidth = 1;
    c.fillStyle = th.up; c.fill(upFill);
    c.fillStyle = th.down; c.fill(dnFill);
    c.strokeStyle = th.up; c.stroke(upWick); c.stroke(upStroke);
    c.strokeStyle = th.down; c.stroke(dnWick); c.stroke(dnStroke);
  }

  private paintLine(a: number, b: number): void {
    const c = this.mc, th = this.theme, s = this.shown, ps = this.price, k = this.bucket();
    const from = Math.max(0, a - 1), to = Math.min(s.length - 1, b + 1);
    const path = new Path2D(), spikes = new Path2D();
    let first = true, x0 = 0, x1 = 0;
    for (let i = from - (from % k); i <= to; i += k) {
      const bar = this.merged(i, k);
      if (!bar) continue;
      const x = this.time.x(Math.min(i + k - 1, s.length - 1));
      const y = ps.y(bar.c);
      if (first) { path.moveTo(x, y); x0 = x; first = false; } else path.lineTo(x, y);
      x1 = x;
      if (k > 1) { spikes.moveTo(x, ps.y(bar.h)); spikes.lineTo(x, ps.y(bar.l)); }
    }
    if (first) return;
    const pane = this.panes[0];
    const bottom = pane.top + pane.height;
    if (this.type === "baseline") {
      const baseVal = s[Math.max(0, a - 1)]?.c ?? s[0].c;
      const by = ps.y(baseVal);
      const fill = new Path2D(path); fill.lineTo(x1, by); fill.lineTo(x0, by); fill.closePath();
      for (const [lo, hi, col] of [[pane.top, by, th.up], [by, bottom, th.down]] as [number, number, string][]) {
        c.save();
        c.beginPath(); c.rect(0, lo, this.plotW(), Math.max(0, hi - lo)); c.clip();
        c.globalAlpha = 0.14; c.fillStyle = col; c.fill(fill);
        c.globalAlpha = 1; c.strokeStyle = col; c.lineWidth = 2; c.stroke(path);
        c.restore();
      }
      c.strokeStyle = th.muted; c.setLineDash([4, 4]); c.lineWidth = 1;
      c.beginPath(); c.moveTo(0, Math.round(by) + 0.5); c.lineTo(this.plotW(), Math.round(by) + 0.5); c.stroke();
      c.setLineDash([]);
      return;
    }
    if (this.type === "area") {
      const fill = new Path2D(path); fill.lineTo(x1, bottom); fill.lineTo(x0, bottom); fill.closePath();
      const g = c.createLinearGradient(0, pane.top, 0, bottom);
      g.addColorStop(0, withAlpha(th.up, 0.28)); g.addColorStop(1, withAlpha(th.up, 0.02));
      c.fillStyle = g; c.fill(fill);
    }
    c.strokeStyle = th.up; c.lineWidth = 2; c.lineJoin = "round";
    if (k > 1) { c.lineWidth = 1; c.globalAlpha = 0.5; c.stroke(spikes); c.globalAlpha = 1; c.lineWidth = 2; }
    c.stroke(path);
  }

  private color(l: StudyLine): string {
    const th = this.theme;
    if (l.color === "up") return th.up;
    if (l.color === "down") return th.down;
    if (l.color === "muted") return th.muted;
    return th.slots[l.color % th.slots.length];
  }

  /** Slots past the palette's length repeat their colour, dashed, so two lines never look the same. */
  private dashFor(l: StudyLine): number[] {
    if (l.dash) return [5, 4];
    return typeof l.color === "number" && l.color >= this.theme.slots.length ? [7, 3] : [];
  }

  private polyline(values: number[], scale: ValueScale, a: number, b: number, step = false): Path2D {
    const p = new Path2D();
    let pen = false, py = 0;
    const k = this.bucket();
    for (let i = Math.max(0, a - 1); i <= Math.min(values.length - 1, b + 1); i += k) {
      const v = values[i];
      if (!Number.isFinite(v)) { pen = false; continue; }
      const x = this.time.x(i), y = scale.y(v);
      if (!pen) p.moveTo(x, y);
      else if (step) { p.lineTo(x, py); p.lineTo(x, y); }
      else p.lineTo(x, y);
      pen = true; py = y;
    }
    return p;
  }

  private paintStudy(st: StudyOutput, scale: ValueScale, a: number, b: number): void {
    const c = this.mc, th = this.theme, pw = this.plotW();
    if (st.guides) {
      c.strokeStyle = th.muted; c.lineWidth = 1; c.setLineDash([2, 4]);
      c.beginPath();
      for (const g of st.guides) { const y = Math.round(scale.y(g)) + 0.5; c.moveTo(0, y); c.lineTo(pw, y); }
      c.stroke(); c.setLineDash([]);
    }
    if (st.hist) {
      const up = new Path2D(), dn = new Path2D(), y0 = scale.y(0), w = Math.max(1, this.time.spacing * 0.6);
      for (let i = a; i <= b; i++) {
        const v = st.hist[i];
        if (!Number.isFinite(v)) continue;
        const y = scale.y(v), x = this.time.x(i);
        (v >= 0 ? up : dn).rect(x - w / 2, Math.min(y, y0), w, Math.max(1, Math.abs(y - y0)));
      }
      c.globalAlpha = 0.55;
      c.fillStyle = th.up; c.fill(up);
      c.fillStyle = th.down; c.fill(dn);
      c.globalAlpha = 1;
    }
    if (st.fill) {
      const [ui, li] = st.fill, U = st.lines[ui].values, L = st.lines[li].values;
      const p = new Path2D();
      let open = false;
      const lo = Math.max(0, a - 1), hi = Math.min(U.length - 1, b + 1);
      const back: [number, number][] = [];
      for (let i = lo; i <= hi; i++) {
        if (!Number.isFinite(U[i]) || !Number.isFinite(L[i])) continue;
        const x = this.time.x(i);
        if (!open) { p.moveTo(x, scale.y(U[i])); open = true; } else p.lineTo(x, scale.y(U[i]));
        back.push([x, scale.y(L[i])]);
      }
      for (let j = back.length - 1; j >= 0; j--) p.lineTo(back[j][0], back[j][1]);
      if (open) { c.globalAlpha = 0.08; c.fillStyle = this.color(st.lines[ui]); c.fill(p); c.globalAlpha = 1; }
    }
    for (const l of st.lines) {
      c.strokeStyle = this.color(l);
      c.lineWidth = l.width ?? 1.6;
      c.setLineDash(this.dashFor(l));
      c.stroke(this.polyline(l.values, scale, a, b, l.step));
    }
    c.setLineDash([]);
  }

  private scaleStudy(p: Pane, a: number, b: number): void {
    const st = p.study!;
    if (st.range) { p.scale.fit(st.range[0], st.range[1], 0.04, 0.04); return; }
    let lo = Infinity, hi = -Infinity;
    const seen = (v: number) => { if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } };
    for (let i = a; i <= b; i++) { for (const l of st.lines) seen(l.values[i]); if (st.hist) seen(st.hist[i]); }
    for (const g of st.guides ?? []) seen(g);
    if (!Number.isFinite(lo)) { lo = -1; hi = 1; }
    p.scale.fit(lo, hi, 0.1, 0.1);
  }

  private paintCompare(a: number, b: number): void {
    const c = this.mc, base = this.compareBase(a);
    if (!Number.isFinite(base)) return;
    const vals = this.compare!.values.map((_, i) => this.compareAsPrice(i, base));
    c.strokeStyle = this.theme.ink; c.lineWidth = 1.6; c.setLineDash([]);
    c.stroke(this.polyline(vals, this.price, a, b));
  }

  private paintLevels(): void {
    const c = this.mc;
    for (const l of this.levels) {
      const y = Math.round(this.price.y(l.price)) + 0.5;
      c.strokeStyle = this.tone(l.tone); c.lineWidth = 1.2; c.setLineDash([6, 4]);
      c.beginPath(); c.moveTo(0, y); c.lineTo(this.plotW(), y); c.stroke();
      c.setLineDash([]);
      c.fillStyle = this.tone(l.tone); c.textAlign = "left"; c.textBaseline = "bottom";
      c.fillText(l.label, 6, y - 3);
    }
  }

  private paintMarkers(a: number, b: number): void {
    if (!this.markers.length || !this.bars.length) return;
    const c = this.mc, th = this.theme, s = this.shown;
    const stack = new Map<number, number>();
    for (const m of this.markers) {
      const i = indexAtOrBefore(s, m.t);
      if (i < a || i > b) continue;
      const n = stack.get(i * 2 + (m.side === "buy" ? 0 : 1)) ?? 0;
      stack.set(i * 2 + (m.side === "buy" ? 0 : 1), n + 1);
      const x = this.time.x(i), size = 7;
      c.fillStyle = m.side === "buy" ? th.up : th.down;
      c.strokeStyle = th.bg; c.lineWidth = 2;
      c.beginPath();
      if (m.side === "buy") {
        const y = this.price.y(s[i].l) + 8 + n * 16;
        c.moveTo(x, y); c.lineTo(x - size, y + size * 1.6); c.lineTo(x + size, y + size * 1.6);
      } else {
        const y = this.price.y(s[i].h) - 8 - n * 16;
        c.moveTo(x, y); c.lineTo(x - size, y - size * 1.6); c.lineTo(x + size, y - size * 1.6);
      }
      c.closePath(); c.stroke(); c.fill();
    }
  }

  private paintOver(): void {
    const c = this.oc, th = this.theme, pw = this.plotW(), H = this.H;
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    c.clearRect(0, 0, this.W, H);
    const pane = this.panes[0];
    if (pane) {
      c.save();
      c.beginPath(); c.rect(0, pane.top, pw, pane.height); c.clip();
      const m = this.mapper();
      const dth = { line: th.ink, accent: th.accent, text: th.text, bg: th.bg, fill: withAlpha(th.accent, 0.08), font: th.font };
      const fmt = (p: number) => this.priceText(p);
      for (const d of this.drawings) paintDrawing(c, d, m, dth, d.id === this.selected, fmt);
      if (this.draft) paintDrawing(c, this.draft.d, m, dth, true, fmt);
      c.restore();
    }
    const x = this.cross;
    if (!x || this.hoverIndex < 0) return;
    const cx = Math.round(this.time.x(this.hoverIndex)) + 0.5;
    c.strokeStyle = th.muted; c.lineWidth = 1; c.setLineDash([4, 4]);
    c.beginPath();
    c.moveTo(cx, 0); c.lineTo(cx, H - AXIS_H);
    const hp = this.panes.find((p) => x.y >= p.top && x.y <= p.top + p.height);
    if (hp && x.x <= pw) { const y = Math.round(x.y) + 0.5; c.moveTo(0, y); c.lineTo(pw, y); }
    c.stroke(); c.setLineDash([]);
    c.font = th.font; c.textBaseline = "middle";
    if (hp && x.x <= pw) {
      const v = hp.scale.value(x.y);
      const step = hp.kind === "price" ? this.priceStep() : (hp.scale.hi - hp.scale.lo) / 100;
      const text = hp.kind === "price" && this.price.mode !== "percent" ? this.priceText(v) : this.axisText(hp.scale, v, step);
      c.fillStyle = th.ink;
      c.fillRect(pw + 1, x.y - 10, this.W - pw - 1, 20);
      c.fillStyle = th.bg; c.textAlign = "left";
      c.fillText(text, pw + 6, x.y);
    }
    const bar = this.shown[this.hoverIndex];
    if (bar) {
      const text = timeLabel(bar.w, this.intraday);
      const w = c.measureText(text).width + 14;
      const left = Math.max(0, Math.min(pw - w, cx - w / 2));
      c.fillStyle = th.ink;
      c.fillRect(left, H - AXIS_H + 1, w, AXIS_H - 1);
      c.fillStyle = th.bg; c.textAlign = "center";
      c.fillText(text, left + w / 2, H - AXIS_H / 2);
    }
  }

  /** The chart as one picture: candles, drawings and a title line (for the PNG download). */
  snapshot(title: string): HTMLCanvasElement {
    const cross = this.cross;
    this.cross = null;
    this.dirtyMain = this.dirtyOver = true;
    this.paint();
    const out = document.createElement("canvas");
    out.width = this.main.width; out.height = this.main.height;
    const c = out.getContext("2d")!;
    c.drawImage(this.main, 0, 0);
    c.drawImage(this.over, 0, 0);
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    c.font = `600 ${this.theme.font}`;
    const w = c.measureText(title).width + 16;
    c.fillStyle = withAlpha(this.theme.bg, 0.86);
    c.fillRect(6, 6, w, 24);
    c.fillStyle = this.theme.text; c.textBaseline = "middle"; c.textAlign = "left";
    c.fillText(title, 14, 18);
    this.cross = cross;
    this.invalidate(false);
    return out;
  }

  /** Numbers for tests and the page's data attributes. */
  state() {
    const [a, b] = this.visibleRange();
    return { bars: this.bars.length, from: a, to: b, spacing: this.time.spacing, mode: this.price.mode, auto: this.auto, drawings: this.drawings.length, selected: this.selected, tool: this.tool };
  }
}

/** A colour (hex or rgb) with an alpha. */
export function withAlpha(col: string, a: number): string {
  const s = col.trim();
  if (s.startsWith("#")) {
    const h = s.length === 4 ? s.slice(1).split("").map((x) => x + x).join("") : s.slice(1, 7);
    const n = parseInt(h, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }
  const m = /rgba?\(([^)]+)\)/.exec(s);
  if (m) { const [r, g, b] = m[1].split(",").map((x) => x.trim()); return `rgba(${r}, ${g}, ${b}, ${a})`; }
  return s;
}
