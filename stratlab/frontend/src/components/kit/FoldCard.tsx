import { useEffect, useId, useState, type ReactNode } from "react";
import { Info } from "../ui";
import { textOf } from "./Card";

/** A card that is one row until it is opened: its title (the button that opens it, inside the heading), its (i) beside the
 * title, and on the right a short summary of what is inside ("9 tools", "2 held · ₹42,500") and a chevron. The whole row is
 * the tap target. Closed by default (owner, 5 Nov: "More in Money" and "Your schemes" were walls of cards and rows). The
 * contents stay on the page while closed (hidden), so a link into them still finds them; `openWhen` opens it from outside
 * (a link to something inside). */
export function FoldCard({ title, meta, info, infoLabel, open: initial = false, openWhen, id, label, testId, className, level = 2, actions, children }: {
  title: string; meta?: ReactNode; info?: ReactNode; infoLabel?: string; open?: boolean; openWhen?: boolean; id?: string; label?: string;
  testId?: string; className?: string; level?: 2 | 3;
  /** a small control on the head row, before the summary (a "Download CSV"): not a row of its own under the head (R15 #7) */
  actions?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(initial);
  useEffect(() => { if (openWhen) setOpen(true); }, [openWhen]);
  const body = useId();
  const H = `h${level}` as "h2" | "h3";
  const said = typeof meta === "string" || typeof meta === "number" ? String(meta) : textOf(meta);
  return (
    <section id={id} className={`k-card k-foldcard${open ? " open" : ""}${className ? ` ${className}` : ""}`} aria-label={label ?? title} data-testid={testId}>
      <div className="k-foldcard-head">
        <div className="k-card-titlerow">
          <H className="k-card-title">
            <button type="button" className="k-foldcard-btn" aria-expanded={open} aria-controls={body} onClick={() => setOpen(!open)}>
              {title}{said && <span className="sr-only">, {said}</span>}
            </button>
          </H>
          {info && <Info label={infoLabel ?? `About ${title}`}>{info}</Info>}
        </div>
        {actions ? (
          <span className="k-foldcard-end">
            <span className="k-foldcard-actions">{actions}</span>
            <span className="k-foldcard-meta" aria-hidden="true">{meta}<span className="k-foldcard-chev" /></span>
          </span>
        ) : <span className="k-foldcard-meta" aria-hidden="true">{meta}<span className="k-foldcard-chev" /></span>}
      </div>
      <div id={body} className="k-foldcard-body" hidden={!open}>{children}</div>
    </section>
  );
}
