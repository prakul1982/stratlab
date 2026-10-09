import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { watchSize } from "../lib/resize";

export type Quadrant = "leading" | "weakening" | "lagging" | "improving";
export interface RotationRow {
  id: string; symbol: string; name: string; points: { t: string; x: number; y: number }[];
  x: number; y: number; quadrant: Quadrant; heading: number | null; moved: Quadrant | null; core?: boolean; stocks?: number;
}

export const QUADRANTS: { id: Quadrant; name: string; says: string }[] = [
  { id: "leading", name: "Leading", says: "stronger than the benchmark and still gaining" },
  { id: "weakening", name: "Weakening", says: "stronger than the benchmark but losing pace" },
  { id: "lagging", name: "Lagging", says: "weaker than the benchmark and still slipping" },
  { id: "improving", name: "Improving", says: "weaker than the benchmark but picking up" },
];
const Q_NAME: Record<Quadrant, string> = { leading: "Leading", weakening: "Weakening", lagging: "Lagging", improving: "Improving" };
const qColor = (q: Quadrant) => `var(--q-${q})`;

/** The swatch that carries a quadrant's colour next to its (ink-coloured) name. */
export function QuadrantTag({ q }: { q: Quadrant }) {
  return <span className="q-tag"><i className={`q-${q}`} />{Q_NAME[q]}</span>;
}

function useWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(800);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.clientWidth);
    return watchSize(el, () => setW(el.clientWidth));      // a frame later: no "ResizeObserver loop" page error (R7T-014)
  }, []);
  return [ref, w];
}

/** Relative strength (x) against its momentum (y), 100 = the benchmark, with each member's recent trail. */
export function RotationChart({ rows, benchmark, step, focus, onFocus }: {
  rows: RotationRow[]; benchmark: string; step?: number | null; focus?: string | null; onFocus?: (id: string | null) => void;
}) {
  const [box, width] = useWidth();
  const [hoverId, setHover] = useState<string | null>(null);
  const hover = hoverId ?? focus ?? null;          // the one trail drawn in full; the rest step back
  const phone = width < 560;
  const W = Math.max(300, width), H = Math.round(Math.min(640, Math.max(360, W * (phone ? 1.1 : 0.6))));
  const pad = { l: 44, r: 12, t: 24, b: phone ? 34 : 38 };
  const all = rows.flatMap((r) => r.points);
  const span = (k: "x" | "y") => Math.max(1.5, ...all.map((p) => Math.abs(p[k] - 100))) * 1.12;
  const sx = span("x"), sy = span("y");
  const X = (v: number) => pad.l + ((v - (100 - sx)) / (2 * sx)) * (W - pad.l - pad.r);
  const Y = (v: number) => pad.t + (1 - (v - (100 - sy)) / (2 * sy)) * (H - pad.t - pad.b);
  const cx = X(100), cy = Y(100);
  const ticks = (s: number) => { const st = (s > 6 ? 2 : s > 3 ? 1 : 0.5) * (phone ? 2 : 1); const out: number[] = []; for (let v = Math.ceil((100 - s) / st) * st; v <= 100 + s; v += st) out.push(+v.toFixed(2)); return out; };
  const shown = (r: RotationRow) => (step ? r.points.slice(0, Math.max(1, step)) : r.points);
  const hov = rows.find((r) => r.id === hoverId) ?? null;
  // dots that sit on top of each other share one name ("Nifty Energy +2"): three names on one spot can't all be read
  const heads = rows.map((r) => { const e = shown(r)[shown(r).length - 1]; return { id: r.id, name: r.name, x: X(e.x), y: Y(e.y) }; });
  const stacked = new Map<string, string[]>();
  const lead = heads.filter((h, i) => {
    const first = heads.findIndex((o) => Math.abs(o.x - h.x) < 7 && Math.abs(o.y - h.y) < 7);
    if (first !== i) { const g = stacked.get(heads[first].id) ?? []; g.push(h.name); stacked.set(heads[first].id, g); return h.id === hover; }
    return true;
  });
  const labels = placeLabels(lead.map((h) => ({ ...h, name: stacked.has(h.id) && h.id !== hover ? `${h.name} +${stacked.get(h.id)!.length}` : h.name })),
    { l: pad.l, r: W - pad.r, t: pad.t, b: H - pad.b }, hover, phone);
  const last = hov ? shown(hov)[shown(hov).length - 1] : null;

  return (
    <div className="rot-chart" ref={box}>
      {/* a group, not an image: it holds the points you can tab to and press (R6O-024: axe nested-interactive) */}
      <svg width={W} height={H} role="group" aria-label={`Rotation of ${rows.length} items against ${benchmark}. The table below lists every value.`}>
        {/* quadrant backgrounds, then hairline grid and the 100 cross */}
        <rect x={pad.l} y={pad.t} width={cx - pad.l} height={cy - pad.t} fill={qColor("improving")} className="rot-tint" />
        <rect x={cx} y={pad.t} width={W - pad.r - cx} height={cy - pad.t} fill={qColor("leading")} className="rot-tint" />
        <rect x={cx} y={cy} width={W - pad.r - cx} height={H - pad.b - cy} fill={qColor("weakening")} className="rot-tint" />
        <rect x={pad.l} y={cy} width={cx - pad.l} height={H - pad.b - cy} fill={qColor("lagging")} className="rot-tint" />
        {ticks(sx).map((v) => <line key={`gx${v}`} x1={X(v)} x2={X(v)} y1={pad.t} y2={H - pad.b} stroke="var(--rule)" strokeWidth={1} />)}
        {ticks(sy).map((v) => <line key={`gy${v}`} y1={Y(v)} y2={Y(v)} x1={pad.l} x2={W - pad.r} stroke="var(--rule)" strokeWidth={1} />)}
        <line x1={cx} x2={cx} y1={pad.t} y2={H - pad.b} stroke="var(--line-2)" strokeWidth={1} />
        <line y1={cy} y2={cy} x1={pad.l} x2={W - pad.r} stroke="var(--line-2)" strokeWidth={1} />
        {ticks(sx).map((v) => <text key={`tx${v}`} x={X(v)} y={H - pad.b + 14} textAnchor="middle" className="rot-tick">{v}</text>)}
        {ticks(sy).map((v) => <text key={`ty${v}`} x={pad.l - 6} y={Y(v) + 4} textAnchor="end" className="rot-tick">{v}</text>)}
        <text x={W - pad.r} y={H - 4} textAnchor="end" className="rot-axis">Relative strength vs {benchmark} →</text>
        <text x={pad.l} y={pad.t - 9} className="rot-axis">↑ Momentum</text>
        {([["improving", pad.l + 8, pad.t + 16, "start"], ["leading", W - pad.r - 8, pad.t + 16, "end"],
          ["weakening", W - pad.r - 8, H - pad.b - 8, "end"], ["lagging", pad.l + 8, H - pad.b - 8, "start"]] as const).map(([q, x, y, a]) => (
          <g key={q}>
            <circle cx={a === "start" ? x + 4 : x - Q_NAME[q].length * 7.4 - 8} cy={y - 4} r={4} fill={qColor(q)} />
            <text x={a === "start" ? x + 12 : x} y={y} textAnchor={a} className="rot-quad">{Q_NAME[q]}</text>
          </g>
        ))}
        {/* trails: faint history, the latest move and the current position in full; the focused one stands out */}
        {rows.map((r) => {
          const pts = shown(r);
          const end = pts[pts.length - 1];
          const prev = pts.length > 1 ? pts[pts.length - 2] : null;
          const q = step ? quadrantOf(end.x, end.y) : r.quadrant;
          const on = hover === r.id, dim = hover !== null && !on;
          return (
            <g key={r.id} className="rot-g" opacity={dim ? 0.12 : 1}>
              <polyline points={pts.map((p) => `${X(p.x)},${Y(p.y)}`).join(" ")} fill="none" stroke={qColor(q)}
                strokeWidth={on ? 2 : 1.5} className={on ? undefined : "rot-trail"} strokeLinejoin="round" strokeLinecap="round" />
              {on && pts.slice(0, -1).map((p) => <circle key={p.t} cx={X(p.x)} cy={Y(p.y)} r={2.5} fill={qColor(q)} />)}
              {prev && !on && <line x1={X(prev.x)} y1={Y(prev.y)} x2={X(end.x)} y2={Y(end.y)} stroke={qColor(q)} strokeWidth={2} strokeLinecap="round" />}
              <circle cx={X(end.x)} cy={Y(end.y)} r={on ? 6 : 5} fill={qColor(q)} stroke="var(--card)" strokeWidth={2} />
            </g>
          );
        })}
        {/* names: placed greedily so none overlap; a hidden one still shows when its trail is hovered or focused */}
        {labels.map((l) => (
          <text key={l.id} x={l.x} y={l.y} textAnchor={l.anchor} className={`rot-label${hover === l.id ? " hl" : ""}`} opacity={hover !== null && hover !== l.id ? 0.25 : 1}>{l.name}</text>
        ))}
        {rows.map((r) => {
          const end = shown(r)[shown(r).length - 1];
          return (
            <circle key={`hit-${r.id}`} cx={X(end.x)} cy={Y(end.y)} r={12} fill="transparent" tabIndex={0} role="button" aria-pressed={focus === r.id} aria-label={`${r.name}: ${Q_NAME[quadrantOf(end.x, end.y)]}`}
              onMouseEnter={() => setHover(r.id)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(r.id)} onBlur={() => setHover(null)}
              onClick={() => onFocus?.(focus === r.id ? null : r.id)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onFocus?.(focus === r.id ? null : r.id); } }} className="rot-hit" />
          );
        })}
      </svg>
      {hov && last && (
        <div className="rot-tip" style={{ left: Math.min(W - 220, Math.max(4, X(last.x) + 14)), top: Math.max(4, Y(last.y) - 70) }}>
          <b>{hov.name}</b>
          <QuadrantTag q={quadrantOf(last.x, last.y)} />
          <span className="tiny muted">Strength {last.x.toFixed(2)} · Momentum {last.y.toFixed(2)}</span>
          <span className="tiny muted">{shown(hov).length > 1 ? `Over ${shown(hov).length} points, from ${Q_NAME[quadrantOf(shown(hov)[0].x, shown(hov)[0].y)]}` : ""}</span>
        </div>
      )}
    </div>
  );
}

function quadrantOf(x: number, y: number): Quadrant {
  return x >= 100 ? (y >= 100 ? "leading" : "weakening") : y >= 100 ? "improving" : "lagging";
}

/** Replays the trails point by point. */
export function useAnimate(len: number): [number | null, () => void] {
  const [step, setStep] = useState<number | null>(null);
  useEffect(() => {
    if (step === null) return;
    if (step >= len) { const t = window.setTimeout(() => setStep(null), 600); return () => window.clearTimeout(t); }
    const t = window.setTimeout(() => setStep(step + 1), 450);
    return () => window.clearTimeout(t);
  }, [step, len]);
  return [step, () => setStep(1)];
}

type Placed = { id: string; name: string; x: number; y: number; anchor: "start" | "end" };

/** Put each name beside its dot (right, else left, else above/below) where it overlaps no other name or dot;
 *  names that fit nowhere are left out. The hovered/focused one is placed first so it always shows. */
function placeLabels(heads: { id: string; name: string; x: number; y: number }[], plot: { l: number; r: number; t: number; b: number },
                     first: string | null, phone: boolean): Placed[] {
  const out: Placed[] = [], boxes: [number, number, number, number][] = heads.map((h) => [h.x - 8, h.y - 8, h.x + 8, h.y + 8]);      // a dot is 5 wide with its 2 ring: a name keeps clear of all of it
  const hit = (a: [number, number, number, number]) => boxes.some((b) => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1]);
  const order = [...heads].sort((a, b) => (a.id === first ? -1 : b.id === first ? 1 : 0));
  for (const h of order) {
    if (phone && h.id !== first) continue;
    const w = h.name.length * 6.6 + 4, own = heads.indexOf(h);
    const tries: [number, number, "start" | "end"][] = [[h.x + 13, h.y + 4, "start"], [h.x - 13, h.y + 4, "end"], [h.x - w / 2, h.y - 15, "start"], [h.x - w / 2, h.y + 22, "start"]];
    for (const [x, y, anchor] of tries) {
      const x0 = anchor === "end" ? x - w : x, box: [number, number, number, number] = [x0, y - 11, x0 + w, y + 3];
      if (box[0] < plot.l || box[2] > plot.r || box[1] < plot.t || box[3] > plot.b) continue;
      const mine = boxes[own]; boxes[own] = [0, 0, 0, 0];       // its own dot doesn't block it
      const clash = hit(box); boxes[own] = mine;
      if (clash && h.id !== first) continue;
      boxes.push(box); out.push({ id: h.id, name: h.name, x, y, anchor }); break;
    }
  }
  return out;
}
