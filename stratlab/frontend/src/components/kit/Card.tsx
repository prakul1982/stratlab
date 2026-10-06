import type { ReactNode } from "react";
import { Info } from "../ui";

/** The one card: 24px padding (16px on a phone), 14px radius, 16px between its parts. `compact` lays its children in one
 * row, for a card that has little to say (an empty list). */
export function Card({ id, children, compact, label, testId }: { id?: string; children: ReactNode; compact?: boolean; label?: string; testId?: string }) {
  return <section id={id} className={`k-card${compact ? " compact" : ""}`} aria-label={label} data-testid={testId}>{children}</section>;
}

/** The row at the top of a card: the title and its (i) on the left, the card's controls (range, Table, a button) on the
 * right in the same row. It wraps under the title on a narrow screen. */
export function CardHead({ title, info, infoLabel, actions, level = 2 }: { title: ReactNode; info?: ReactNode; infoLabel?: string; actions?: ReactNode; level?: 2 | 3 }) {
  const H = `h${level}` as "h2" | "h3";
  return (
    <div className="k-card-head">
      <H className="k-card-title">{title}{info && <Info label={infoLabel ?? "About this"}>{info}</Info>}</H>
      {actions && <div className="k-card-actions">{actions}</div>}
    </div>
  );
}
