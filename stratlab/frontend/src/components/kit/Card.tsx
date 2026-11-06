import { isValidElement, useEffect, useId, useRef, type ReactNode } from "react";
import { Info } from "../ui";
import { SectionControls, SectionCtx, useSection, useSectionFrame } from "./Section";

/** The one card: 24px padding (16px on a phone), 14px radius, 16px between its parts. `compact` lays its children in one
 * row, for a card that has little to say (an empty list). */
export function Card({ id, children, compact, label, testId, className }: { id?: string; children: ReactNode; compact?: boolean; label?: string; testId?: string; className?: string }) {
  // a page section (a card with a title) can be closed to its header and moved among the cards beside it, remembered (kit/Section.tsx)
  const el = useRef<HTMLElement>(null);
  const frame = useSectionFrame(el, { id, allowed: !compact });
  const folded = frame.on && !frame.open;
  return (
    <section ref={el} id={id} className={`k-card${compact ? " compact" : ""}${folded ? " k-folded" : ""}${className ? ` ${className}` : ""}`} aria-label={label}
      data-testid={testId} data-section={frame.on ? frame.key ?? undefined : undefined}>
      <SectionCtx.Provider value={frame}>{children}</SectionCtx.Provider>
    </section>
  );
}

/** The words in a title, for names built from it ("About Markets"). */
export function textOf(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

/** The row at the top of a card: the title and its (i) on the left, the card's controls (range, Table, a button) on the
 * right in the same row. It wraps under the title on a narrow screen. The (i) sits beside the heading, not inside it,
 * and is named after the title ("About Markets") unless `infoLabel` says otherwise. */
export function CardHead({ title, info, infoLabel, actions, level = 2 }: { title: ReactNode; info?: ReactNode; infoLabel?: string; actions?: ReactNode; level?: 2 | 3 }) {
  const H = `h${level}` as "h2" | "h3";
  const words = textOf(title).replace(/\s+/g, " ").trim();
  // a card's main title (h2) names its section, which gets the close and move buttons; a sub-title (h3) does not
  const frame = useSection();
  const hid = useId();
  const mine = !!frame && level === 2;
  const { setTitle, setHeadingId } = frame ?? {};
  useEffect(() => {
    if (!mine || !setTitle || !setHeadingId) return;
    setTitle(words);
    setHeadingId(hid);
    return () => { setTitle(""); setHeadingId(null); };
  }, [mine, words, hid, setTitle, setHeadingId]);
  return (
    <div className="k-card-head">
      {info ? (
        <div className="k-card-titlerow">
          <H className="k-card-title" id={mine ? hid : undefined}>{title}</H>
          <Info label={infoLabel ?? (words ? `About ${words}` : "About this card")}>{info}</Info>
        </div>
      ) : <H className="k-card-title" id={mine ? hid : undefined}>{title}</H>}
      {actions && <div className="k-card-actions">{actions}</div>}
      {mine && frame.on && <SectionControls frame={frame} />}
    </div>
  );
}
