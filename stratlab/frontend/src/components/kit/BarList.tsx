import type { ReactNode } from "react";

/** A thin bar filled to `pct` percent (decoration; the figure beside it says the same in words). */
export function Meter({ pct }: { pct: number | null | undefined }) {
  return <div className="k-meter" aria-hidden="true"><i style={{ width: `${Math.max(1, Math.min(100, pct ?? 0))}%` }} /></div>;
}

/** A share of a whole as rows of bars: the name (and a small note), its figure on the right, a bar under it. For
 * "by sector", "by asset class". `pct` is 0 to 100 (null draws the thinnest bar). */
export function BarList({ label, rows, footnote }: { label: string; rows: { key: string; name: ReactNode; note?: ReactNode; value: ReactNode; pct: number | null; title?: string }[]; footnote?: ReactNode }) {
  return (
    <>
      <div className="k-bars" role="list" aria-label={label}>
        {rows.map((r) => (
          <div key={r.key} className="k-bar" role="listitem" title={r.title}>
            <div className="k-bar-top"><span>{r.name}{r.note && <span className="k-muted k-note"> · {r.note}</span>}</span><span className="k-bar-v">{r.value}</span></div>
            <Meter pct={r.pct} />
          </div>
        ))}
      </div>
      {footnote && <p className="k-note">{footnote}</p>}
    </>
  );
}
