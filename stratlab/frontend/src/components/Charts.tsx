import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";

/* Hand-drawn-feeling SVG charts in the notebook style. Colors come from CSS variables so both themes work. */

export interface Line {
  values: (number | null)[];
  color: string;          // a CSS color or var(--x)
  width?: number;
  dash?: string;
  label: string;
}
export interface Marker { i: number; side: "buy" | "sell" }

interface LineChartProps {
  lines: Line[];
  labels: string[];                 // tooltip label per point
  axisLabels?: string[];            // x-axis labels at evenly spaced points
  height?: number;
  format: (v: number) => string;
  axisFormat?: (v: number) => string;   // shorter numbers for the y axis
  split?: number | null;            // index where "unseen data" starts
  splitNotes?: [string, string];    // annotations either side of the split
  markers?: Marker[];
  baseline?: number | null;
  ariaLabel: string;
  levels?: { v: number; color: string; label: string }[];
}

const PAD = { l: 58, r: 12, t: 30, b: 26 };

export function LineChart({ lines, labels, axisLabels, height = 250, format, axisFormat, split, splitNotes, markers = [], baseline,
  ariaLabel, levels = [] }: LineChartProps) {
  // draw at the real width, so text stays readable on phones
  const wrap = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(800);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = W < 560 ? Math.round(height * 0.8) : height;
  const yFmt = axisFormat ?? format;
  const n = labels.length;
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);

  const { min, max } = useMemo(() => {
    let lo = Infinity, hi = -Infinity;
    for (const l of lines) for (const v of l.values) if (v != null && Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    for (const lv of levels) { lo = Math.min(lo, lv.v); hi = Math.max(hi, lv.v); }
    if (baseline != null) { lo = Math.min(lo, baseline); hi = Math.max(hi, baseline); }
    if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08;
    return { min: lo - pad, max: hi + pad };
  }, [lines, levels, baseline]);

  const x = (i: number) => PAD.l + (n <= 1 ? 0 : (i / (n - 1)) * (W - PAD.l - PAD.r));
  const y = (v: number) => PAD.t + (1 - (v - min) / (max - min)) * (H - PAD.t - PAD.b);
  const path = (vals: (number | null)[]) => {
    let d = "", pen = false;
    vals.forEach((v, i) => {
      if (v == null || !Number.isFinite(v)) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  const ticks = [0, 1, 2, 3].map((k) => min + ((max - min) * (k + 0.5)) / 4);
  const axis = axisLabels ?? labels;
  const xTicks = n > 1 ? (W < 560 ? [0, 0.5, 1] : [0, 0.25, 0.5, 0.75, 1]).map((f) => Math.round(f * (n - 1))) : [0];

  const move = (e: PointerEvent<SVGSVGElement>) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box || n < 2) return;
    const px = ((e.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  };

  const hx = hover != null ? x(hover) : 0;
  const first = lines[0]?.values[hover ?? 0];

  return (
    <div ref={wrap} style={{ position: "relative" }}>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={ariaLabel}
        onPointerMove={move} onPointerLeave={() => setHover(null)} style={{ touchAction: "pan-y", overflow: "visible" }}>
        {split != null && split > 0 && split < n && (
          <>
            <rect x={x(split)} y={PAD.t - 22} width={W - PAD.r - x(split)} height={H - PAD.b - PAD.t + 22} fill="var(--orange-soft)" opacity={0.6} />
            <line x1={x(split)} x2={x(split)} y1={PAD.t - 22} y2={H - PAD.b} stroke="var(--ink)" strokeDasharray="3 4" />
            {splitNotes && (
              <>
                <text x={x(split) - 8} y={PAD.t - 8} textAnchor="end" fontFamily="var(--serif)" fontStyle="italic" fontSize={W < 560 ? 12 : 15} fill="var(--ink)">{splitNotes[0]}</text>
                <text x={Math.min(x(split) + 8, W - PAD.r - 4)} y={PAD.t - 8} textAnchor={x(split) > W * 0.8 ? "end" : "start"} fontFamily="var(--serif)" fontStyle="italic" fontSize={W < 560 ? 12 : 15} fill="var(--orange-ink)">{splitNotes[1]}</text>
              </>
            )}
          </>
        )}
        {ticks.map((t, k) => (
          <g key={k}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke="var(--line)" />
            <text x={PAD.l - 8} y={y(t) + 4} textAnchor="end" fontFamily="var(--mono)" fontSize={11} fill="var(--muted)">{yFmt(t)}</text>
          </g>
        ))}
        {baseline != null && <line x1={PAD.l} x2={W - PAD.r} y1={y(baseline)} y2={y(baseline)} stroke="var(--dash)" strokeDasharray="4 4" />}
        {levels.map((lv) => (
          <line key={lv.label} x1={PAD.l} x2={W - PAD.r} y1={y(lv.v)} y2={y(lv.v)} stroke={lv.color} strokeDasharray="5 4" strokeWidth={1.2} />
        ))}
        {lines.map((l) => (
          <path key={l.label} d={path(l.values)} fill="none" stroke={l.color} strokeWidth={l.width ?? 1.8} strokeDasharray={l.dash} strokeLinejoin="round" />
        ))}
        {markers.map((m, k) => {
          const v = lines[0]?.values[m.i];
          if (v == null) return null;
          const cx = x(m.i), cy = y(v);
          return m.side === "buy"
            ? <path key={k} d={`M${cx},${cy + 7} l6,10 h-12z`} fill="var(--blue)" />
            : <path key={k} d={`M${cx},${cy - 7} l6,-10 h-12z`} fill="var(--orange)" />;
        })}
        {xTicks.map((i, k) => (
          <text key={k} x={x(i)} y={H - 6} textAnchor={k === 0 ? "start" : k === xTicks.length - 1 ? "end" : "middle"}
            fontFamily="var(--mono)" fontSize={11} fill="var(--muted)">{axis[i]}</text>
        ))}
        {hover != null && <line x1={hx} x2={hx} y1={PAD.t} y2={H - PAD.b} stroke="var(--ink)" strokeWidth={1} opacity={0.35} />}
        {hover != null && first != null && <circle cx={hx} cy={y(first)} r={4} fill="var(--ink)" />}
      </svg>
      {hover != null && (
        <div className="mono" style={{
          position: "absolute", top: 0, left: `${(hx / W) * 100}%`, transform: `translateX(${hx > W * 0.7 ? "-105%" : "8px"})`,
          background: "var(--card)", border: "1px solid var(--line-2)", borderRadius: 8, padding: "6px 10px", fontSize: 12.5,
          pointerEvents: "none", whiteSpace: "nowrap", boxShadow: "var(--shadow)",
        }}>
          <div className="muted">{labels[hover]}</div>
          {lines.map((l) => l.values[hover] != null && (
            <div key={l.label} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ width: 10, height: 3, background: l.color, display: "inline-block" }} />{l.label}: {format(l.values[hover] as number)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dash?: boolean }[] }) {
  return (
    <div className="row wrap small muted" style={{ gap: 16 }}>
      {items.map((i) => (
        <span key={i.label} className="row" style={{ gap: 6 }}>
          <span style={{ width: 16, height: 0, borderTop: `2px ${i.dash ? "dashed" : "solid"} ${i.color}`, display: "inline-block" }} />{i.label}
        </span>
      ))}
    </div>
  );
}

/* 5×5 grid of returns for nearby indicator settings; yours outlined. */
export function Heatmap({ grid, yours, label }: { grid: number[][]; yours: [number, number]; label: string }) {
  const cols = grid[0]?.length ?? 0;
  return (
    <div role="img" aria-label={label} style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 3 }}>
      {grid.flatMap((row, r) => row.map((v, c) => {
        const a = Math.min(1, 0.25 + Math.abs(v) / 20).toFixed(2);
        const mine = r === yours[0] && c === yours[1];
        return (
          <span key={`${r}-${c}`} title={`${v > 0 ? "+" : ""}${v.toFixed(1)}%`} style={{
            height: 28, borderRadius: 4,
            background: v > 0 ? `color-mix(in srgb, var(--blue) ${+a * 100}%, transparent)` : `color-mix(in srgb, var(--orange) ${+a * 100}%, transparent)`,
            outline: mine ? "2.5px solid var(--ink)" : undefined, outlineOffset: 1,
          }} />
        );
      }))}
    </div>
  );
}

/* Where your drawdown sits among 1,000 reshuffles. */
export function DrawdownBand({ yours, p95, worst }: { yours: number; p95: number; worst: number }) {
  const max = Math.max(worst, yours, 1) * 1.05;
  const X = (v: number) => 8 + (v / max) * 264;
  return (
    <svg viewBox="0 0 280 64" width="100%" role="img" aria-label={`Your drawdown ${yours.toFixed(0)}%, 95% of reshuffles under ${p95.toFixed(0)}%, worst ${worst.toFixed(0)}%`}>
      <line x1={8} y1={30} x2={272} y2={30} stroke="var(--line)" strokeWidth={10} strokeLinecap="round" />
      <line x1={X(yours)} y1={30} x2={X(p95)} y2={30} stroke="var(--orange-soft)" strokeWidth={10} />
      <line x1={X(yours)} y1={16} x2={X(yours)} y2={44} stroke="var(--ink)" strokeWidth={2} />
      <circle cx={X(worst)} cy={30} r={5} fill="var(--orange)" />
      <text x={Math.max(30, X(yours))} y={60} textAnchor="middle" fontFamily="var(--mono)" fontSize={11} fill="var(--ink)">yours −{yours.toFixed(0)}%</text>
      <text x={272} y={12} textAnchor="end" fontFamily="var(--mono)" fontSize={11} fill="var(--orange-ink)">worst −{worst.toFixed(0)}%</text>
      <text x={8} y={12} fontFamily="var(--mono)" fontSize={11} fill="var(--muted)">0%</text>
    </svg>
  );
}

/* Built-on vs unseen returns as two bars. */
export function SplitBars({ built, unseen, builtLabel, unseenLabel }: { built: number; unseen: number; builtLabel: string; unseenLabel: string }) {
  const max = Math.max(Math.abs(built), Math.abs(unseen), 1);
  const bar = (v: number) => (
    <div className="row" style={{ gap: 8 }}>
      <span style={{ height: 14, width: `${Math.max(4, (Math.abs(v) / max) * 150)}px`, borderRadius: 3, background: v >= 0 ? "var(--blue)" : "var(--orange)" }} />
      <span className="mono" style={{ fontSize: 14 }}>{v > 0 ? "+" : v < 0 ? "−" : ""}{Math.abs(v).toFixed(1)}%</span>
    </div>
  );
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="stack" style={{ gap: 5 }}><span className="small muted">{builtLabel}</span>{bar(built)}</div>
      <div className="stack" style={{ gap: 5 }}><span className="small muted">{unseenLabel}</span>{bar(unseen)}</div>
    </div>
  );
}
