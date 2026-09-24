import { useId } from "react";
import { MARK, MARK_COLORS, MARK_RATIO, MARK_VIEWBOX } from "../lib/brand";

/** The S-candlestick mark. `size` is its height in px. */
export function LogoMark({ size = 32, title }: { size?: number; title?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg width={Math.round(size * MARK_RATIO)} height={size} viewBox={MARK_VIEWBOX} role={title ? "img" : undefined}
      aria-label={title} aria-hidden={title ? undefined : true} style={{ flex: "none" }}>
      <defs>
        <linearGradient id={`${id}g`} gradientUnits="userSpaceOnUse" x1="392" y1="228" x2="300" y2="365">
          {MARK_COLORS.green.map(([o, c]) => <stop key={o} offset={o} stopColor={c} />)}
        </linearGradient>
        <linearGradient id={`${id}r`} gradientUnits="userSpaceOnUse" x1="285" y1="525" x2="345" y2="395">
          {MARK_COLORS.red.map(([o, c]) => <stop key={o} offset={o} stopColor={c} />)}
        </linearGradient>
      </defs>
      <path fill={MARK_COLORS.ribbon} d={MARK.ribbon} />
      <rect {...MARK.greenWick} rx={1.5} fill={MARK_COLORS.greenWick} />
      <path fill={`url(#${id}g)`} d={MARK.green} />
      <rect {...MARK.redWick} rx={1.5} fill={MARK_COLORS.redWick} />
      <path fill={`url(#${id}r)`} d={MARK.red} />
    </svg>
  );
}

/** Mark plus the "StratLab" wordmark. `size` is the mark height; the text scales with it. */
export function Logo({ size = 34 }: { size?: number }) {
  return (
    <span className="logo" style={{ fontSize: size * 0.42, gap: size * 0.2 }}>
      <LogoMark size={size} />
      <span className="logo-word"><b>Strat</b>Lab</span>
    </span>
  );
}
