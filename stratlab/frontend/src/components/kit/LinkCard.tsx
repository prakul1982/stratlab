import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/** A card that is one link: a title, a line on what is there, and a small note (when it was last updated). For a list of
 * places to go (connected accounts, where your data lives). */
export function LinkCard({ to, title, children, note }: { to: string; title: string; children?: ReactNode; note?: ReactNode }) {
  return (
    <Link className="k-linkcard" to={to}>
      <b>{title}</b>
      {children && <span className="k-sub-line">{children}</span>}
      {note && <span className="k-note">{note}</span>}
    </Link>
  );
}
