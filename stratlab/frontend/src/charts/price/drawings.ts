/* Drawings on the price chart: lines, levels, boxes, Fibonacci retracements and notes, pinned to times and prices
 * so they stay put across zoom, timeframes and scale modes. Painting and hit-testing only; the engine owns state. */

export type DrawingKind = "trend" | "hline" | "ray" | "rect" | "fib" | "text";
export interface DrawPoint { t: number; p: number }
export interface Drawing { id: string; kind: DrawingKind; points: DrawPoint[]; text?: string }

export const DRAW_TOOLS: { kind: DrawingKind; name: string; points: 1 | 2 }[] = [
  { kind: "trend", name: "Trend line", points: 2 },
  { kind: "hline", name: "Price level", points: 1 },
  { kind: "ray", name: "Ray", points: 2 },
  { kind: "rect", name: "Rectangle", points: 2 },
  { kind: "fib", name: "Fibonacci retracement", points: 2 },
  { kind: "text", name: "Text note", points: 1 },
];

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

/** Screen position of a drawing's point. */
export interface Mapper { x(t: number): number; y(p: number): number; width: number; top: number; bottom: number }

export interface DrawTheme { line: string; accent: string; text: string; bg: string; fill: string; font: string }

function pts(d: Drawing, m: Mapper): { x: number; y: number }[] {
  return d.points.map((p) => ({ x: m.x(p.t), y: m.y(p.p) }));
}

/** Where a ray from a through b leaves the plot on the right. */
function rayEnd(a: { x: number; y: number }, b: { x: number; y: number }, width: number) {
  if (Math.abs(b.x - a.x) < 1e-6) return { x: b.x, y: b.y };
  const k = (b.y - a.y) / (b.x - a.x);
  const x = b.x >= a.x ? width : 0;
  return { x, y: a.y + k * (x - a.x) };
}

export function paintDrawing(ctx: CanvasRenderingContext2D, d: Drawing, m: Mapper, th: DrawTheme, selected: boolean, fmt: (p: number) => string): void {
  const p = pts(d, m);
  if (!p.length) return;
  const [a, b] = [p[0], p[1] ?? p[0]];
  ctx.save();
  ctx.strokeStyle = selected ? th.accent : th.line;
  ctx.fillStyle = th.text;
  ctx.lineWidth = selected ? 2 : 1.5;
  ctx.font = th.font;
  ctx.setLineDash([]);
  switch (d.kind) {
    case "trend":
      line(ctx, a.x, a.y, b.x, b.y);
      break;
    case "ray": {
      const e = rayEnd(a, b, m.width);
      line(ctx, a.x, a.y, e.x, e.y);
      break;
    }
    case "hline":
      line(ctx, 0, a.y, m.width, a.y);
      label(ctx, fmt(d.points[0].p), m.width - 6, a.y - 5, "right", th);
      break;
    case "rect": {
      ctx.fillStyle = th.fill;
      ctx.fillRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
      ctx.strokeRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
      break;
    }
    case "fib": {
      const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x);
      const [p0, p1] = [d.points[0].p, (d.points[1] ?? d.points[0]).p];
      ctx.globalAlpha = 0.9;
      for (const lv of FIB_LEVELS) {
        const price = p1 + (p0 - p1) * lv;      // 0 at the second point, 1 at the first, as charting apps do
        const y = m.y(price);
        ctx.setLineDash(lv === 0 || lv === 1 ? [] : [4, 3]);
        line(ctx, x0, y, x1, y);
        label(ctx, `${lv} (${fmt(price)})`, x0 + 4, y - 4, "left", th);
      }
      ctx.setLineDash([2, 3]);
      line(ctx, a.x, a.y, b.x, b.y);
      break;
    }
    case "text": {
      const text = d.text || "Note";
      ctx.font = th.font;
      const w = ctx.measureText(text).width + 12;
      ctx.fillStyle = th.bg;
      ctx.strokeStyle = selected ? th.accent : th.line;
      ctx.beginPath();
      ctx.rect(a.x, a.y - 22, w, 22);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = th.text;
      ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.fillText(text, a.x + 6, a.y - 11);
      break;
    }
  }
  if (selected) {
    ctx.setLineDash([]);
    for (const q of d.kind === "hline" ? [{ x: Math.min(m.width - 30, Math.max(30, a.x)), y: a.y }] : p) {
      ctx.fillStyle = th.bg; ctx.strokeStyle = th.accent; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(q.x, q.y, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
  }
  ctx.restore();
}

function line(ctx: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number) {
  ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
}

function label(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, align: CanvasTextAlign, th: DrawTheme) {
  ctx.save();
  ctx.setLineDash([]);
  ctx.font = th.font; ctx.textAlign = align; ctx.textBaseline = "alphabetic";
  ctx.fillStyle = th.text;
  ctx.fillText(text, x, y);
  ctx.restore();
}

function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay;
  const len = dx * dx + dy * dy;
  const t = len ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len)) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/** The drawing (and the handle, if a point was grabbed) under (x, y), topmost first; null when none is near. */
export function hitDrawing(list: Drawing[], x: number, y: number, m: Mapper, tol = 7): { id: string; handle: number | null } | null {
  for (let k = list.length - 1; k >= 0; k--) {
    const d = list[k];
    const p = pts(d, m);
    if (!p.length) continue;
    const handle = d.kind === "hline" ? -1 : p.findIndex((q) => Math.hypot(q.x - x, q.y - y) <= tol + 2);
    if (handle >= 0) return { id: d.id, handle };
    const [a, b] = [p[0], p[1] ?? p[0]];
    let near = false;
    switch (d.kind) {
      case "trend": near = distToSegment(x, y, a.x, a.y, b.x, b.y) <= tol; break;
      case "ray": { const e = rayEnd(a, b, m.width); near = distToSegment(x, y, a.x, a.y, e.x, e.y) <= tol; break; }
      case "hline": near = Math.abs(y - a.y) <= tol; break;
      case "rect": {
        const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x), y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y);
        near = x >= x0 - tol && x <= x1 + tol && y >= y0 - tol && y <= y1 + tol;
        break;
      }
      case "fib": {
        const x0 = Math.min(a.x, b.x) - tol, x1 = Math.max(a.x, b.x) + tol;
        const [p0, p1] = [d.points[0].p, (d.points[1] ?? d.points[0]).p];
        near = x >= x0 && x <= x1 && FIB_LEVELS.some((lv) => Math.abs(m.y(p1 + (p0 - p1) * lv) - y) <= tol);
        break;
      }
      case "text": near = x >= a.x - tol && x <= a.x + 160 && y >= a.y - 22 - tol && y <= a.y + tol; break;
    }
    if (near) return { id: d.id, handle: null };
  }
  return null;
}
