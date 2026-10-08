import type { ReactNode } from "react";
import { signCls, signed } from "../../lib/format";

/** A signed figure in the kit's colours: green (`--up`) above zero, red (`--down`) below it, plain at zero or when
 * unknown. The sign (+ / −) stays in the text, so the colour is never the only signal.
 *
 * `<Signed value={v} />` writes `signed(v)`; `<Signed value={v} fmt={(x) => pct(x, 2)} />` writes it your way; or pass the
 * text as children (`<Signed value={d}>{signedInrCompact(d)}</Signed>`) when it is already worked out. A figure that
 * rounds to nothing ("0.0%") stays plain. Use it for a change, a gain or loss, a return or a net figure. Not for a level,
 * a price, a total, a count or a size, which have no direction. */
export function Signed({ value, fmt = signed, children }: { value: number | null | undefined; fmt?: (v: number) => string; children?: ReactNode }) {
  const text = children ?? (value == null || !Number.isFinite(value) ? "–" : fmt(value));
  const cls = signCls(value, typeof text === "string" ? text : undefined);
  return cls ? <span className={cls}>{text}</span> : <>{text}</>;
}
