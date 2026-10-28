import { Children, createContext, useContext, useLayoutEffect, type ReactNode } from "react";
import { changeDir, minusNode } from "../../lib/format";
import { useNoOrphan } from "../../lib/noOrphan";

/** Inside a labelled StatRow (a list for screen readers), each Stat is one of its items. */
const InList = createContext(false);

/** The text a node prints (strings and numbers in it, in order), to tell whether the figure rounds to zero. */
function textOf(node: ReactNode): string {
  return Children.toArray(node).map((c) => (typeof c === "string" || typeof c === "number" ? String(c) : "")).join("");
}

/** A change as a pill: ▲ up, ▼ down. The colour follows the sign (`tone="auto"`); pass `tone="neutral"` where a rise is
 * not good news and a fall is not bad (the market's margin-funded book, open interest): the arrow still shows the
 * direction, the colour does not judge. Screen readers hear "up" or "down". `value` decides the direction, except that a change whose printed
 * figure rounds to nothing ("0.00%") is flat: no arrow, and screen readers hear "Unchanged", not "Up 0.00%" (R11P-010). */
export function Delta({ value, children, tone = "auto" }: { value: number | null | undefined; children: ReactNode; tone?: "auto" | "neutral" }) {
  if (value == null || !Number.isFinite(value)) return null;
  const dir = changeDir(value, textOf(children));
  const cls = tone === "neutral" ? "flat" : dir;
  return (
    <span className={`k-delta ${cls}`}>
      {dir !== "flat" && <span aria-hidden="true">{dir === "up" ? "▲" : "▼"}</span>}
      <span className="sr-only">{dir === "up" ? "Up " : dir === "down" ? "Down " : "Unchanged "}</span>
      {children}
    </span>
  );
}

/** One figure: a small label, a big number (the page's sans font, never mono) and a note under it. `tone` colours the
 * number up or down; `delta` puts a Delta pill in the note line. In a labelled StatRow it is a list item by itself
 * (`item` is the old way to say so). */
export function Stat({ label, value, note, delta, tone, item, testId }: { label: ReactNode; value: ReactNode; note?: ReactNode; delta?: ReactNode; tone?: "up" | "down"; item?: boolean; testId?: string }) {
  const listed = useContext(InList) || item;
  return (
    <div className="k-stat" role={listed ? "listitem" : undefined} data-testid={testId}>
      <span className="k-stat-k">{label}</span>
      <span className={`k-stat-v${tone ? ` k-${tone}` : ""}`}>{minusNode(value)}</span>
      {(delta || note) && <span className="k-stat-d">{delta}{delta && note ? " " : ""}{note}</span>}
    </div>
  );
}

/** VR5-006: on a phone the figures of a row were one under another, each with the right half of its line empty (Invest's market breadth,
 * Holdings' totals). When they would be one per row, they go two across (`.duo`) if every figure still fits its half on one line; a
 * figure that would wrap ("₹1,06,50,136" in a half) keeps the row as it was. A last one alone takes the whole line (CSS). */
function useDuo(ref: { current: HTMLDivElement | null }) {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    let width = -1;
    const fix = () => {
      el.classList.remove("duo");
      if (window.innerWidth > 640 || el.children.length < 2) return;
      const cols = getComputedStyle(el).gridTemplateColumns.split(" ").filter(Boolean).length;
      if (cols !== 1) return;
      el.classList.add("duo");
      const wraps = Array.from(el.querySelectorAll<HTMLElement>(".k-stat-v")).some((v) => v.getBoundingClientRect().height > parseFloat(getComputedStyle(v).lineHeight) * 1.5);
      if (wraps) el.classList.remove("duo");
    };
    const ro = new ResizeObserver(() => { const w = el.clientWidth; if (w !== width) { width = w; fix(); } });
    const mo = new MutationObserver(fix);
    ro.observe(el);
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    fix();
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [ref]);
}

/** Stats side by side; they wrap to the width (about three across on a desktop card, one on a phone). */
export function StatRow({ children, label }: { children: ReactNode; label?: string }) {
  const ref = useNoOrphan<HTMLDivElement>();      // 4 + 1 and 5 + 1 become 3 + 2 and 3 + 3 (UI-FIX-1, R9)
  useDuo(ref);
  return <div className="k-stats" ref={ref} role={label ? "list" : undefined} aria-label={label}><InList.Provider value={!!label}>{children}</InList.Provider></div>;
}
