import { isValidElement, type ReactNode } from "react";
import { Info } from "../ui";

/** The one card: 24px padding (16px on a phone), 14px radius, 16px between its parts. `compact` lays its children in one
 * row, for a card that has little to say (an empty list). */
export function Card({ id, children, compact, label, testId, className }: { id?: string; children: ReactNode; compact?: boolean; label?: string; testId?: string; className?: string }) {
  return <section id={id} className={`k-card${compact ? " compact" : ""}${className ? ` ${className}` : ""}`} aria-label={label} data-testid={testId}>{children}</section>;
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
  return (
    <div className="k-card-head">
      {info ? (
        <div className="k-card-titlerow">
          <H className="k-card-title">{title}</H>
          <Info label={infoLabel ?? (words ? `About ${words}` : "About this card")}>{info}</Info>
        </div>
      ) : <H className="k-card-title">{title}</H>}
      {actions && <div className="k-card-actions">{actions}</div>}
    </div>
  );
}
