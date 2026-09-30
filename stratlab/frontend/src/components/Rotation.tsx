import { useEffect, useLayoutEffect, useRef, useState } from "react";

export type Quadrant = "leading" | "weakening" | "lagging" | "improving";
export interface RotationRow {
  id: string; symbol: string; name: string; points: { t: string; x: number; y: number }[];
  x: number; y: number; quadrant: Quadrant; heading: number | null; moved: Quadrant | null;
}

export const QUADRANTS: { id: Quadrant; name: string; says: string }[] = [
  { id: "leading", name: "Leading", says: "stronger than the benchmark and still gaining" },
  { id: "weakening", name: "Weakening", says: "stronger than the benchmark but losing pace" },
  { id: "lagging", name: "Lagging", says: "weaker than the benchmark and still slipping" },
  { id: "improving", name: "Improving", says: "weaker than the benchmark but picking up" },
];
export const Q_NAME: Record<Quadrant, string> = { leading: "Leading", weakening: "Weakening", lagging: "Lagging", improving: "Improving" };
const qColor = (q: Quadrant) => `var(--q-${q})`;

/** The swatch that carries a quadrant's colour next to its (ink-coloured) name. */
export function QuadrantTag({ q }: { q: Quadrant }) {
  return <span className="q-tag"><i style={{ background: qColor(q) }} />{Q_NAME[q]}</span>;
}

function useWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(800);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** Relative strength (x) against its momentum (y), 100 = the benchmark, with each member's recent trail. */
export function RotationChart({ rows, benchmark, step }: { rows: RotationRow[]; benchmark: string; step?: number | null }) {
  const [box, width] = useWidth();
  const [hover, setHover] = useState<string | null>(null);
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
  const hov = rows.find((r) => r.id === hover) ?? null;
  const last = hov ? shown(hov)[shown(hov).length - 1] : null;

  return (
    <div className="rot-chart" ref={box}>
      <svg width={W} height={H} role="img" aria-label={`Rotation of ${rows.length} items against ${benchmark}. The table below lists every value.`}>
        {/* quadrant backgrounds, then hairline grid and the 100 cross */}
        <rect x={pad.l} y={pad.t} width={cx - pad.l} height={cy - pad.t} fill={qColor("improving")} opacity={0.07} />
        <rect x={cx} y={pad.t} width={W - pad.r - cx} height={cy - pad.t} fill={qColor("leading")} opacity={0.07} />
        <rect x={cx} y={cy} width={W - pad.r - cx} height={H - pad.b - cy} fill={qColor("weakening")} opacity={0.07} />
        <rect x={pad.l} y={cy} width={cx - pad.l} height={H - pad.b - cy} fill={qColor("lagging")} opacity={0.07} />
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
        {/* trails: a thin line through each week, a dot per point, a ringed dot at the latest */}
        {rows.map((r) => {
          const pts = shown(r);
          const end = pts[pts.length - 1];
          const q = step ? quadrantOf(end.x, end.y) : r.quadrant;
          const dim = hover && hover !== r.id ? 0.18 : 1;
          return (
            <g key={r.id} opacity={dim} style={{ transition: "opacity .15s" }}>
              <polyline points={pts.map((p) => `${X(p.x)},${Y(p.y)}`).join(" ")} fill="none" stroke={qColor(q)} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {pts.slice(0, -1).map((p) => <circle key={p.t} cx={X(p.x)} cy={Y(p.y)} r={2.5} fill={qColor(q)} />)}
              <circle cx={X(end.x)} cy={Y(end.y)} r={5} fill={qColor(q)} stroke="var(--card)" strokeWidth={2} />
              {(!phone || hover === r.id) && (X(end.x) + 8 + r.name.length * 7 > W - pad.r
                ? <text x={X(end.x) - 8} y={Y(end.y) - 7} textAnchor="end" className="rot-label">{r.name}</text>
                : <text x={X(end.x) + 8} y={Y(end.y) - 7} className="rot-label">{r.name}</text>)}
              <circle cx={X(end.x)} cy={Y(end.y)} r={14} fill="transparent" tabIndex={0} aria-label={`${r.name}: ${Q_NAME[q]}`}
                onMouseEnter={() => setHover(r.id)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(r.id)} onBlur={() => setHover(null)}
                onClick={() => setHover(hover === r.id ? null : r.id)} style={{ cursor: "pointer", outline: "none" }} />
            </g>
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

export function quadrantOf(x: number, y: number): Quadrant {
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
