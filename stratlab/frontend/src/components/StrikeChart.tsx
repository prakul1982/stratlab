import { useEffect, useRef, useState } from "react";
import "../pages/trade/options.css";
import { contracts, contractsShort, signed, strike as strikeText, type StrikeRow } from "../lib/positioning";

/* Open interest by strike as a butterfly: one row per strike, calls to the left of the strike column and puts to the
 * right, each growing out from the middle. In "change" mode each side's zero sits in the middle of its half: open
 * interest added grows outward, open interest cut grows inward. One series colour per side (calls, puts), validated
 * for both themes; the strike nearest the spot is marked, and every number is in the tooltip and the table view. */

const ROW = 18, BAR = 12, MID = 70, TOP = 26, BOTTOM = 8;

/** A bar from x0 (its baseline) to x1, square at the baseline and rounded 4px at the data end. */
function barPath(x0: number, x1: number, y: number, h: number): string {
  const w = Math.abs(x1 - x0);
  if (w < 0.5) return "";
  const r = Math.min(4, w / 2, h / 2), dir = x1 > x0 ? 1 : -1;
  const xe = x1 - dir * r;
  return `M${x0},${y}H${xe}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${xe},${y + h}H${x0}Z`;
}

export function StrikeChart({ rows, mode, spot, label }: { rows: StrikeRow[]; mode: "oi" | "chg"; spot?: number | null; label: string }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(720);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // highest strike on top, as an option chain is read
  const list = [...rows].sort((a, b) => b.strike - a.strike);
  const H = TOP + list.length * ROW + BOTTOM;
  const half = (W - MID) / 2 - 4;
  const cx0 = half, cx1 = half + MID;            // the strike column sits between these
  const val = (r: StrikeRow, side: "call" | "put") => (mode === "oi" ? r[`${side}_oi`] : r[`${side}_chg`]) ?? null;
  const max = Math.max(1, ...list.flatMap((r) => [Math.abs(val(r, "call") ?? 0), Math.abs(val(r, "put") ?? 0)]));
  // where each side's zero is, and how far a value reaches from it
  const span = mode === "oi" ? half - 2 : half / 2 - 2;
  const zero = { call: mode === "oi" ? cx0 : cx0 - half / 2, put: mode === "oi" ? cx1 : cx1 + half / 2 };
  const reach = (side: "call" | "put", v: number) => zero[side] + (side === "call" ? -1 : 1) * (v / max) * span;
  const nearest = spot != null && list.length ? list.reduce((b, r) => (Math.abs(r.strike - spot) < Math.abs(b.strike - spot) ? r : b)).strike : null;
  const y = (i: number) => TOP + i * ROW;
  const h = hover != null ? list[hover] : null;

  return (
    <div ref={wrap} className="strike-chart k-strike-chart">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={label} onPointerLeave={() => setHover(null)}>
        <text x={cx0 - 4} y={14} textAnchor="end" fontFamily="var(--sans)" fontSize={12} fill="var(--muted)">Calls{mode === "chg" ? ": change" : ""}</text>
        <text x={cx1 + 4} y={14} fontFamily="var(--sans)" fontSize={12} fill="var(--muted)">Puts{mode === "chg" ? ": change" : ""}</text>
        <text x={(cx0 + cx1) / 2} y={14} textAnchor="middle" fontFamily="var(--sans)" fontSize={12} fill="var(--muted)">Strike</text>
        {mode === "chg" && (["call", "put"] as const).map((s) => (
          <line key={s} x1={zero[s]} x2={zero[s]} y1={TOP - 4} y2={H - BOTTOM} stroke="var(--line-2)" strokeWidth={1} />
        ))}
        {list.map((r, i) => {
          const at = y(i), on = hover === i;
          return (
            <g key={r.strike} onPointerEnter={() => setHover(i)} onPointerMove={() => setHover(i)}>
              <rect x={0} y={at} width={W} height={ROW} fill={on ? "var(--chip)" : r.strike === nearest ? "var(--paper-2)" : "transparent"} />
              {(["call", "put"] as const).map((s) => {
                const v = val(r, s);
                if (v == null || v === 0) return null;
                const d = barPath(zero[s], reach(s, v), at + (ROW - BAR) / 2, BAR);
                if (!d) return null;             // under half a pixel at this width: no empty shape (the tooltip and table have it)
                return <path key={s} d={d} fill={`var(--pos-${s})`} opacity={v < 0 ? 0.55 : 1} />;
              })}
              <text x={(cx0 + cx1) / 2} y={at + ROW / 2 + 4} textAnchor="middle" fontFamily="var(--sans)" fontSize={11.5}
                fill={r.strike === nearest ? "var(--ink)" : "var(--muted)"} fontWeight={r.strike === nearest ? 600 : 400}>{strikeText(r.strike)}</text>
            </g>
          );
        })}
      </svg>
      {h && (
        <div className="strike-tip ch-num" role="status" style={{ top: Math.min(y(hover!) + ROW + 4, H - 70), left: "50%" }}>
          <div className="muted">Strike {strikeText(h.strike)}{h.strike === nearest ? " · nearest the spot" : ""}</div>
          <div className="k-row"><span className="key-line call" /><b>{contracts(h.call_oi)}</b> calls <span className="muted">({signed(h.call_chg)})</span></div>
          <div className="k-row"><span className="key-line put" /><b>{contracts(h.put_oi)}</b> puts <span className="muted">({signed(h.put_chg)})</span></div>
        </div>
      )}
      <p className="k-note">
        Scale: the longest bar is {contractsShort(max)} contracts{mode === "chg" ? ". Bars growing outward: open interest added; inward (lighter): open interest cut" : ""}.
      </p>
    </div>
  );
}
