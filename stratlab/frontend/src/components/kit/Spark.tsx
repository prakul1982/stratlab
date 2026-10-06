/** A tiny line of recent values, with no axes: for a tile that says "how it has moved lately" (a market on the strip, the net
 * worth card). Drawn from real values only; fewer than two points draw nothing. `tone` colours it up, down or neutral (use
 * `neutral` where a rise is not good news); `label` is what a screen reader hears ("NIFTY 50, last month"). */
export function Spark({ values, tone = "neutral", label, area = false, height = 36 }: {
  values: number[]; tone?: "up" | "down" | "neutral"; label: string; area?: boolean; height?: number;
}) {
  const v = values.filter((x) => Number.isFinite(x));
  if (v.length < 2) return null;
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
  const W = 100, H = 30, pad = 2;
  const pts = v.map((y, i) => [(i / (v.length - 1)) * W, H - pad - ((y - lo) / span) * (H - pad * 2)] as const);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
  return (
    <svg className={`k-spark ${tone}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height }} role="img" aria-label={label}>
      {area && <path className="fill" d={`${line} L${W} ${H} L0 ${H} Z`} />}
      <path className="line" d={line} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
