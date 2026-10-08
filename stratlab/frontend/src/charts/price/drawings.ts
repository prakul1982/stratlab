/* Drawings on the price chart: lines, levels, boxes, channels, Fibonacci retracements, long and short position boxes,
 * measures, notes, arrows and brush strokes, pinned to times and prices so they stay put across zoom, timeframes and
 * scale modes. Painting, picking and the tool list live here; the maths is in drawGeo.ts and the engine owns state. */
import {
  channelShift, distToSegment, FIB_LEVELS, fibPrice, levelText, measureStats, rayEnd, statsOf,
  type ColorKey, type Drawing, type DrawingKind, type XY,
} from "./drawGeo";

export type { ColorKey, DashStyle, Drawing, DrawingKind, Pt as DrawPoint } from "./drawGeo";
export { COLOR_KEYS, CLICKS, DASH_KEYS, FIB_LEVELS } from "./drawGeo";

export interface ToolDef { kind: DrawingKind; name: string; /** Shortcut key (a capital letter means Shift). */ key: string; icon: string }

export const DRAW_TOOLS: ToolDef[] = [
  { kind: "trend", name: "Trend line", key: "T", icon: "trend" },
  { kind: "ray", name: "Ray", key: "R", icon: "ray" },
  { kind: "hline", name: "Horizontal line", key: "H", icon: "hline" },
  { kind: "hray", name: "Horizontal ray", key: "Shift+H", icon: "hray" },
  { kind: "vline", name: "Vertical line", key: "Shift+V", icon: "vline" },
  { kind: "rect", name: "Rectangle", key: "B", icon: "rect" },
  { kind: "channel", name: "Parallel channel", key: "C", icon: "channel" },
  { kind: "fib", name: "Fibonacci retracement", key: "F", icon: "fib" },
  { kind: "long", name: "Long position", key: "L", icon: "long" },
  { kind: "short", name: "Short position", key: "S", icon: "short" },
  { kind: "measure", name: "Measure", key: "M", icon: "measure" },
  { kind: "prange", name: "Price range", key: "P", icon: "prange" },
  { kind: "drange", name: "Date range", key: "D", icon: "drange" },
  { kind: "text", name: "Text note", key: "N", icon: "text" },
  { kind: "arrow", name: "Arrow", key: "A", icon: "arrow" },
  { kind: "brush", name: "Brush", key: "Shift+B", icon: "brush" },
];
export const TOOL: Record<DrawingKind, ToolDef> = Object.fromEntries(DRAW_TOOLS.map((t) => [t.kind, t])) as Record<DrawingKind, ToolDef>;

export const TOOL_GROUPS: { id: string; name: string; kinds: DrawingKind[] }[] = [
  { id: "lines", name: "Lines", kinds: ["trend", "ray", "hline", "hray", "vline"] },
  { id: "shapes", name: "Shapes and Fibonacci", kinds: ["rect", "channel", "fib"] },
  { id: "positions", name: "Positions", kinds: ["long", "short"] },
  { id: "measure", name: "Measure", kinds: ["measure", "prange", "drange"] },
  { id: "notes", name: "Notes", kinds: ["text", "arrow", "brush"] },
];

/** What to do next, while a tool is picked. */
export const TOOL_HINT: Record<DrawingKind, string> = {
  trend: "Click the first point, then the second (or drag from one to the other). Esc cancels.",
  ray: "Click the first point, then a point on the line it should run through. Esc cancels.",
  hline: "Click where the level goes. Esc cancels.",
  hray: "Click where the ray starts. Esc cancels.",
  vline: "Click the time for the line. Esc cancels.",
  rect: "Click one corner, then the opposite one. Esc cancels.",
  channel: "Click two points for the line, then a third for the width. Esc cancels.",
  fib: "Click the swing's start, then its end. Esc cancels.",
  long: "Click the entry, then the target. Drag the stop afterwards. Esc cancels.",
  short: "Click the entry, then the target. Drag the stop afterwards. Esc cancels.",
  measure: "Click the start, then the end. Esc cancels.",
  prange: "Click the first price, then the second. Esc cancels.",
  drange: "Click the first time, then the second. Esc cancels.",
  text: "Click where the note goes, then type it. Esc cancels.",
  arrow: "Click the tail, then the tip. Esc cancels.",
  brush: "Press and drag to draw freehand. Esc cancels.",
};

/** Every shortcut, for the (i) next to the drawing tools. */
export const SHORTCUTS: { keys: string; what: string }[] = [
  ...DRAW_TOOLS.map((t) => ({ keys: t.key, what: t.name })),
  { keys: "V or Esc", what: "Select (stop drawing)" },
  { keys: "G", what: "Magnet to open, high, low and close" },
  { keys: "O", what: "Hide or show all drawings" },
  { keys: "Delete", what: "Delete the selected drawing" },
  { keys: "Ctrl/Cmd + D", what: "Duplicate the selected drawing" },
  { keys: "Shift + L", what: "Lock or unlock the selected drawing" },
  { keys: "Ctrl/Cmd + Z", what: "Undo" },
  { keys: "Ctrl/Cmd + Shift + Z", what: "Redo" },
  { keys: "Arrow keys", what: "Move the chart (a drawing's handle stays where it is)" },
  { keys: "+ and -", what: "Zoom the chart" },
];

/** The key that picks a tool, for the keyboard handler: lower-case letter plus whether Shift is held. */
export function toolForKey(key: string, shift: boolean): DrawingKind | null {
  const k = key.toLowerCase();
  for (const t of DRAW_TOOLS) {
    const want = t.key.replace("Shift+", "").toLowerCase();
    if (want === k && t.key.startsWith("Shift+") === shift) return t.kind;
  }
  return null;
}

/** Screen position of a drawing's point. */
export interface Mapper { x(t: number): number; y(p: number): number; width: number; top: number; bottom: number }

/** Numbers as the chart prints them, with the instrument's own currency symbol. */
export interface DrawFmt {
  price(p: number): string;
  /** A signed price change with the currency symbol: +₹50.00, −₹20.00. `like` sets the decimals. */
  move(d: number, like: number): string;
  /** A signed percentage: +4.17%, −1.67%. */
  pct(v: number): string;
  /** An amount of money, whole units: ₹10,000. */
  money(v: number): string;
  count(n: number): string;
  /** A time as the axis would label it. */
  time(t: number): string;
  /** Candles between two times. */
  bars(t0: number, t1: number): number;
  /** The time between two times: 3d 4h. */
  span(ms: number): string;
}

export interface DrawTheme {
  ink: string; accent: string; muted: string; text: string; bg: string; font: string;
  down: string; green: string; magenta: string; orange?: string;
  /** A colour with an alpha, for fills. */
  alpha(color: string, a: number): string;
}

export function colorOf(d: Drawing, th: DrawTheme): string {
  switch (d.color) {
    case "blue": return th.accent;
    case "orange": return th.orange ?? th.down;
    case "green": return th.green;
    case "magenta": return th.magenta;
    case "grey": return th.muted;
    default: return th.ink;
  }
}

/** The palette a person picks from, in the chart's own colours. */
export function swatch(key: ColorKey, th: DrawTheme): string {
  return colorOf({ id: "", kind: "trend", points: [], color: key }, th);
}

const DASH: Record<string, number[]> = { solid: [], dashed: [7, 5], dotted: [2, 4] };

// ---------- where things are on screen ----------
function pts(d: Drawing, m: Mapper): XY[] {
  return d.points.map((p) => ({ x: m.x(p.t), y: m.y(p.p) }));
}

interface PosBox { x0: number; x1: number; ye: number; yt: number; ys: number }
/** The boxes of a long or short position: entry, target and stop heights, and the left and right edges. */
function posBox(d: Drawing, m: Mapper): PosBox | null {
  if (d.points.length < 3) return null;
  const [a, b, c] = pts(d, m);
  return { x0: Math.min(a.x, b.x), x1: Math.max(a.x, b.x), ye: a.y, yt: b.y, ys: c.y };
}

/** Where each handle sits, in order of the drawing's points. */
export function handlesOf(d: Drawing, m: Mapper): XY[] {
  const p = pts(d, m);
  if (d.kind === "long" || d.kind === "short") {
    const b = posBox(d, m);
    return b ? [{ x: p[0].x, y: b.ye }, { x: p[1].x, y: b.yt }, { x: p[1].x, y: b.ys }] : [];
  }
  if (d.kind === "hline") return p.length ? [{ x: Math.min(m.width - 30, Math.max(30, m.width * 0.5)), y: p[0].y }] : [];
  if (d.kind === "vline") return p.length ? [{ x: p[0].x, y: (m.top + m.bottom) / 2 }] : [];
  if (d.kind === "brush") return p.length ? [p[0], p[p.length - 1]] : [];
  return p;
}

/** Which of `handlesOf` moves which point: a brush's two ends are not points to move. */
export function canMoveHandle(d: Drawing): boolean { return d.kind !== "brush"; }

// ---------- painting ----------
function line(ctx: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number) {
  ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
}

/** A small box of text with a coloured edge, kept inside the plot. `anchor` says which corner of the box (x, y) is. */
function pill(ctx: CanvasRenderingContext2D, lines: string[], x: number, y: number, m: Mapper, th: DrawTheme, color: string,
  anchor: "tl" | "tc" | "tr" | "bl" | "bc" | "br" | "cc" = "tl"): { x: number; y: number; w: number; h: number } {
  ctx.save();
  ctx.setLineDash([]);
  ctx.font = th.font;
  const lh = 16, pad = 6;
  const w = Math.ceil(Math.max(...lines.map((l) => ctx.measureText(l).width))) + pad * 2, h = lines.length * lh + 4;
  let left = anchor.endsWith("r") ? x - w : anchor.endsWith("c") ? x - w / 2 : x;
  let top = anchor.startsWith("b") ? y - h : anchor === "cc" ? y - h / 2 : y;
  left = Math.max(4, Math.min(m.width - w - 4, left));
  top = Math.max(m.top + 2, Math.min(m.bottom - h - 2, top));
  ctx.fillStyle = th.alpha(th.bg, 0.94);
  ctx.strokeStyle = color; ctx.lineWidth = 1;
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(left, top, w, h, 4); else ctx.rect(left, top, w, h);
  ctx.fill(); ctx.stroke();
  ctx.fillStyle = th.text; ctx.textAlign = "left"; ctx.textBaseline = "middle";
  lines.forEach((l, i) => ctx.fillText(l, left + pad, top + 2 + lh / 2 + i * lh));
  ctx.restore();
  return { x: left, y: top, w, h };
}

function arrowHead(ctx: CanvasRenderingContext2D, a: XY, b: XY, size: number) {
  const ang = Math.atan2(b.y - a.y, b.x - a.x);
  ctx.beginPath();
  ctx.moveTo(b.x, b.y);
  ctx.lineTo(b.x - size * Math.cos(ang - 0.45), b.y - size * Math.sin(ang - 0.45));
  ctx.lineTo(b.x - size * Math.cos(ang + 0.45), b.y - size * Math.sin(ang + 0.45));
  ctx.closePath();
  ctx.fill();
}

export function paintDrawing(ctx: CanvasRenderingContext2D, d: Drawing, m: Mapper, th: DrawTheme, selected: boolean, f: DrawFmt): void {
  const p = pts(d, m);
  if (!p.length) return;
  const a = p[0], b = p[1] ?? p[0];
  const col = colorOf(d, th);
  ctx.save();
  ctx.strokeStyle = col; ctx.fillStyle = col;
  ctx.lineWidth = selected ? 2.4 : 1.6;
  ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.font = th.font;
  const dash = DASH[d.dash ?? "solid"];
  ctx.setLineDash(dash);
  switch (d.kind) {
    case "trend": line(ctx, a.x, a.y, b.x, b.y); break;
    case "ray": { const e = rayEnd(a, b, m.width); line(ctx, a.x, a.y, e.x, e.y); break; }
    case "arrow": line(ctx, a.x, a.y, b.x, b.y); ctx.setLineDash([]); arrowHead(ctx, a, b, 11); break;
    case "hline":
      line(ctx, 0, a.y, m.width, a.y);
      pill(ctx, [f.price(d.points[0].p)], m.width - 4, a.y - 3, m, th, col, "br");
      break;
    case "hray":
      line(ctx, a.x, a.y, m.width, a.y);
      pill(ctx, [f.price(d.points[0].p)], m.width - 4, a.y - 3, m, th, col, "br");
      break;
    case "vline":
      line(ctx, a.x, m.top, a.x, m.bottom);
      pill(ctx, [f.time(d.points[0].t)], a.x, m.bottom - 3, m, th, col, "bc");
      break;
    case "rect": {
      ctx.fillStyle = th.alpha(col, 0.1);
      ctx.fillRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
      ctx.strokeRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
      break;
    }
    case "channel": {
      const c = p[2] ?? b, dy = channelShift(a, b, c);
      ctx.fillStyle = th.alpha(col, 0.08);
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.lineTo(b.x, b.y + dy); ctx.lineTo(a.x, a.y + dy); ctx.closePath(); ctx.fill();
      line(ctx, a.x, a.y, b.x, b.y);
      line(ctx, a.x, a.y + dy, b.x, b.y + dy);
      ctx.setLineDash([3, 4]); ctx.lineWidth = 1;
      line(ctx, a.x, a.y + dy / 2, b.x, b.y + dy / 2);
      break;
    }
    case "fib": {
      const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x);
      const [p0, p1] = [d.points[0].p, (d.points[1] ?? d.points[0]).p];
      const ys = FIB_LEVELS.map((lv) => m.y(fibPrice(p0, p1, lv)));
      for (let i = 0; i < ys.length - 1; i++) {
        ctx.fillStyle = th.alpha(col, i % 2 ? 0.05 : 0.1);
        ctx.fillRect(x0, Math.min(ys[i], ys[i + 1]), x1 - x0, Math.abs(ys[i + 1] - ys[i]));
      }
      FIB_LEVELS.forEach((lv, i) => {
        ctx.setLineDash(dash.length ? dash : lv === 0 || lv === 1 ? [] : [4, 3]);
        line(ctx, x0, ys[i], x1, ys[i]);
        ctx.setLineDash([]);
        ctx.fillStyle = th.text; ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
        ctx.fillText(`${levelText(lv)} (${f.price(fibPrice(p0, p1, lv))})`, x0 + 4, ys[i] - 4);
      });
      ctx.setLineDash([2, 3]); ctx.lineWidth = 1;
      line(ctx, a.x, a.y, b.x, b.y);
      break;
    }
    case "long": case "short": paintPosition(ctx, d, m, th, col, f); break;
    case "measure": {
      const s = measureStats(d.points[0], d.points[1] ?? d.points[0], f.bars(d.points[0].t, (d.points[1] ?? d.points[0]).t));
      const x0 = Math.min(a.x, b.x), y0 = Math.min(a.y, b.y), w = Math.abs(b.x - a.x), h = Math.abs(b.y - a.y);
      ctx.fillStyle = th.alpha(col, 0.1); ctx.fillRect(x0, y0, w, h);
      ctx.setLineDash([4, 3]); ctx.lineWidth = 1; ctx.strokeRect(x0, y0, w, h);
      ctx.setLineDash([]); ctx.lineWidth = selected ? 2.4 : 1.6;
      line(ctx, a.x, a.y, b.x, b.y); arrowHead(ctx, a, b, 9);
      pill(ctx, [`${f.move(s.move, d.points[0].p)} (${f.pct(s.pct)})`, `${f.count(s.bars)} bars, ${f.span(s.ms)}`],
        (a.x + b.x) / 2, b.y >= a.y ? b.y + 6 : b.y - 6, m, th, col, b.y >= a.y ? "tc" : "bc");
      break;
    }
    case "prange": {
      const s = measureStats(d.points[0], d.points[1] ?? d.points[0], 0);
      const x0 = Math.min(a.x, b.x), y0 = Math.min(a.y, b.y), h = Math.abs(b.y - a.y), w = Math.max(24, Math.abs(b.x - a.x));
      ctx.fillStyle = th.alpha(col, 0.1); ctx.fillRect(x0, y0, w, h);
      ctx.setLineDash([4, 3]); ctx.lineWidth = 1;
      line(ctx, x0, a.y, x0 + w, a.y); line(ctx, x0, b.y, x0 + w, b.y);
      ctx.setLineDash([]); ctx.lineWidth = selected ? 2.4 : 1.6;
      const mx = x0 + w / 2;
      line(ctx, mx, a.y, mx, b.y); arrowHead(ctx, { x: mx, y: a.y }, { x: mx, y: b.y }, 9);
      pill(ctx, [`${f.move(s.move, d.points[0].p)} (${f.pct(s.pct)})`], mx, b.y >= a.y ? b.y + 6 : b.y - 6, m, th, col, b.y >= a.y ? "tc" : "bc");
      break;
    }
    case "drange": {
      const t0 = d.points[0], t1 = d.points[1] ?? d.points[0];
      const s = measureStats(t0, t1, f.bars(t0.t, t1.t));
      const x0 = Math.min(a.x, b.x), w = Math.max(2, Math.abs(b.x - a.x));
      ctx.fillStyle = th.alpha(col, 0.08); ctx.fillRect(x0, m.top, w, m.bottom - m.top);
      ctx.setLineDash([4, 3]); ctx.lineWidth = 1;
      line(ctx, a.x, m.top, a.x, m.bottom); line(ctx, b.x, m.top, b.x, m.bottom);
      ctx.setLineDash([]); ctx.lineWidth = selected ? 2.4 : 1.6;
      const my = (m.top + m.bottom) / 2;
      line(ctx, a.x, my, b.x, my); arrowHead(ctx, { x: a.x, y: my }, { x: b.x, y: my }, 9);
      pill(ctx, [`${f.count(Math.abs(s.bars))} bars, ${f.span(Math.abs(s.ms))}`], (a.x + b.x) / 2, my - 8, m, th, col, "bc");
      break;
    }
    case "text": {
      const text = d.text || "Note";
      const w = ctx.measureText(text).width + 12;
      ctx.fillStyle = th.alpha(th.bg, 0.94);
      ctx.beginPath(); ctx.rect(a.x, a.y - 22, w, 22); ctx.fill(); ctx.stroke();
      ctx.fillStyle = th.text; ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.setLineDash([]);
      ctx.fillText(text, a.x + 6, a.y - 11);
      break;
    }
    case "brush": {
      ctx.beginPath();
      p.forEach((q, i) => (i ? ctx.lineTo(q.x, q.y) : ctx.moveTo(q.x, q.y)));
      ctx.stroke();
      break;
    }
  }
  if (selected) {
    ctx.setLineDash([]);
    for (const q of handlesOf(d, m)) {
      ctx.fillStyle = th.bg; ctx.strokeStyle = th.accent; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(q.x, q.y, 5.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
  }
  if (d.locked) {
    const q = handlesOf(d, m)[0] ?? a;
    // a small padlock beside the first handle
    const x = q.x + 9, y = q.y - 14;
    ctx.setLineDash([]); ctx.strokeStyle = th.muted; ctx.fillStyle = th.muted; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(x + 4, y + 2, 3, Math.PI, 0); ctx.stroke();
    ctx.fillRect(x, y + 2, 8, 6);
  }
  ctx.restore();
}

/** The boxes of a position: target above (or below, for a short) the entry and stop on the other side, with the
 *  risk-to-reward ratio and the price moves to each as plain numbers. */
function paintPosition(ctx: CanvasRenderingContext2D, d: Drawing, m: Mapper, th: DrawTheme, col: string, f: DrawFmt) {
  const box = posBox(d, m), st = statsOf(d);
  if (!box || !st) return;
  const w = Math.max(2, box.x1 - box.x0);
  ctx.fillStyle = th.alpha(col, 0.16);
  ctx.fillRect(box.x0, Math.min(box.ye, box.yt), w, Math.abs(box.yt - box.ye));
  ctx.fillStyle = th.alpha(col, 0.07);
  ctx.fillRect(box.x0, Math.min(box.ye, box.ys), w, Math.abs(box.ys - box.ye));
  ctx.lineWidth = 1.4;
  for (const y of [box.yt, box.ys]) line(ctx, box.x0, y, box.x0 + w, y);
  ctx.setLineDash([5, 4]);
  line(ctx, box.x0, box.ye, box.x0 + w, box.ye);
  ctx.setLineDash([]);
  ctx.strokeRect(box.x0, Math.min(box.yt, box.ys), w, Math.abs(box.ys - box.yt));
  const cx = box.x0 + w / 2;
  const up = box.yt <= box.ye;       // the target box is drawn above the entry line
  pill(ctx, [`Target ${f.price(st.target)} · ${f.move(st.targetMove, st.entry)} (${f.pct(st.targetPct)})`], cx, up ? box.yt - 3 : box.yt + 3, m, th, col, up ? "bc" : "tc");
  pill(ctx, [`Stop ${f.price(st.stop)} · ${f.move(st.stopMove, st.entry)} (${f.pct(st.stopPct)})`], cx, box.ys >= box.ye ? box.ys + 3 : box.ys - 3, m, th, col, box.ys >= box.ye ? "tc" : "bc");
  const mid: string[] = [st.ratio == null ? "Risk : reward –" : `Risk : reward 1 : ${st.ratio.toFixed(2)}`];
  if (st.qty != null) mid.push(`Qty ${f.count(st.qty)} · risk ${f.money(st.riskTotal ?? 0)} · reward ${f.money(st.rewardTotal ?? 0)}`);
  else if (d.risk) mid.push("Risk amount is smaller than one unit");
  if (!st.stopSideOk || !st.targetSideOk) mid.push(!st.stopSideOk ? "Stop is on the target's side of the entry" : "Target is on the stop's side of the entry");
  pill(ctx, mid, cx, box.ye, m, th, col, "cc");
}

// ---------- picking ----------
const nearBox = (x: number, y: number, x0: number, y0: number, x1: number, y1: number, tol: number) =>
  x >= Math.min(x0, x1) - tol && x <= Math.max(x0, x1) + tol && y >= Math.min(y0, y1) - tol && y <= Math.max(y0, y1) + tol;

/** The drawing (and the handle, if a point was grabbed) under (x, y), topmost first; null when none is near.
 *  `onlySelected` limits handle grabs to that drawing, as handles of other drawings are not on screen. */
export function hitDrawing(list: Drawing[], x: number, y: number, m: Mapper, tol = 7, selected: string | null = null): { id: string; handle: number | null } | null {
  // a selected drawing's handles win over anything on top of them
  const sel = selected ? list.find((d) => d.id === selected) : null;
  if (sel && canMoveHandle(sel)) {
    const h = handlesOf(sel, m).findIndex((q) => Math.hypot(q.x - x, q.y - y) <= tol + 3);
    if (h >= 0) return { id: sel.id, handle: h };
  }
  for (let k = list.length - 1; k >= 0; k--) {
    const d = list[k];
    const p = pts(d, m);
    if (!p.length) continue;
    const [a, b] = [p[0], p[1] ?? p[0]];
    let near = false;
    switch (d.kind) {
      case "trend": case "arrow": near = distToSegment(x, y, a.x, a.y, b.x, b.y) <= tol; break;
      case "ray": { const e = rayEnd(a, b, m.width); near = distToSegment(x, y, a.x, a.y, e.x, e.y) <= tol; break; }
      case "hline": near = Math.abs(y - a.y) <= tol; break;
      case "hray": near = x >= a.x - tol && Math.abs(y - a.y) <= tol; break;
      case "vline": near = Math.abs(x - a.x) <= tol; break;
      case "rect": near = nearBox(x, y, a.x, a.y, b.x, b.y, tol); break;
      case "channel": {
        const dy = channelShift(a, b, p[2] ?? b);
        near = distToSegment(x, y, a.x, a.y, b.x, b.y) <= tol || distToSegment(x, y, a.x, a.y + dy, b.x, b.y + dy) <= tol
          || distToSegment(x, y, a.x, a.y + dy / 2, b.x, b.y + dy / 2) <= tol;
        break;
      }
      case "fib": {
        const x0 = Math.min(a.x, b.x) - tol, x1 = Math.max(a.x, b.x) + tol;
        const [p0, p1] = [d.points[0].p, (d.points[1] ?? d.points[0]).p];
        near = x >= x0 && x <= x1 && FIB_LEVELS.some((lv) => Math.abs(m.y(fibPrice(p0, p1, lv)) - y) <= tol);
        break;
      }
      case "long": case "short": {
        const box = posBox(d, m);
        near = !!box && nearBox(x, y, box.x0, Math.min(box.yt, box.ys, box.ye), box.x0 + Math.max(2, box.x1 - box.x0), Math.max(box.yt, box.ys, box.ye), 2);
        break;
      }
      case "measure": case "prange": near = nearBox(x, y, a.x, a.y, b.x, b.y, tol); break;
      case "drange": near = x >= Math.min(a.x, b.x) - tol && x <= Math.max(a.x, b.x) + tol && y >= m.top && y <= m.bottom; break;
      case "text": near = x >= a.x - tol && x <= a.x + 12 + (d.text || "Note").length * 7 + tol && y >= a.y - 22 - tol && y <= a.y + tol; break;
      case "brush": for (let i = 1; i < p.length && !near; i++) near = distToSegment(x, y, p[i - 1].x, p[i - 1].y, p[i].x, p[i].y) <= tol; break;
    }
    if (near) return { id: d.id, handle: null };
  }
  return null;
}

/** A short name for the drawings list: "Trend line", "Long position 1 : 2.00", "Note: breakout". */
export function drawingTitle(d: Drawing): string {
  const base = TOOL[d.kind].name;
  const st = statsOf(d);
  if (st?.ratio != null) return `${base}, 1 : ${st.ratio.toFixed(2)}`;
  if (d.kind === "text" && d.text) return `${base}: ${d.text.slice(0, 24)}`;
  return base;
}
