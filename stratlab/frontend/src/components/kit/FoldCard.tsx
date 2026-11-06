import { useEffect, useId, useRef, type ReactNode } from "react";
import { Info } from "../ui";
import { textOf } from "./Card";
import { SectionMenu, useSectionFrame } from "./Section";

/** A card that is one row until it is opened: its title (the button that opens it, inside the heading), its (i) beside the
 * title, and on the right a short summary of what is inside ("9 tools", "2 held · ₹42,500") and a chevron. The whole row is
 * the tap target. Closed by default (owner, 5 Nov: "More in Money" and "Your schemes" were walls of cards and rows). The
 * contents stay on the page while closed (hidden), so a link into them still finds them; `openWhen` opens it from outside
 * (a link to something inside). Opened or closed, it stays that way for the person on this page, and it moves up or down like every
 * other section (kit/Section.tsx). */
export function FoldCard({ title, meta, info, infoLabel, open: initial = false, openWhen, id, label, testId, className, level = 2, children }: {
  title: string; meta?: ReactNode; info?: ReactNode; infoLabel?: string; open?: boolean; openWhen?: boolean; id?: string; label?: string;
  testId?: string; className?: string; level?: 2 | 3; children: ReactNode;
}) {
  const el = useRef<HTMLElement>(null);
  const frame = useSectionFrame(el, { id, title, defaultOpen: initial });
  const { open, setOpen } = frame;
  useEffect(() => { if (openWhen) setOpen(true); }, [openWhen]);    // eslint-disable-line react-hooks/exhaustive-deps
  const body = useId();
  const hid = useId();
  const { setHeadingId } = frame;
  useEffect(() => { setHeadingId(hid); }, [hid, setHeadingId]);
  const H = `h${level}` as "h2" | "h3";
  const said = typeof meta === "string" || typeof meta === "number" ? String(meta) : textOf(meta);
  return (
    <section ref={el} id={id} className={`k-card k-foldcard${open ? " open" : ""}${className ? ` ${className}` : ""}`} aria-label={label ?? title} data-testid={testId}
      data-section={frame.on ? frame.key ?? undefined : undefined}>
      <div className="k-foldcard-head">
        <div className="k-card-titlerow">
          <H className="k-card-title" id={hid}>
            <button type="button" className="k-foldcard-btn" aria-expanded={open} aria-controls={body} onClick={() => setOpen(!open)}>
              {title}{said && <span className="sr-only">, {said}</span>}
            </button>
          </H>
          {info && <Info label={infoLabel ?? `About ${title}`}>{info}</Info>}
        </div>
        <span className="k-foldcard-end">
          <span className="k-foldcard-meta" aria-hidden="true">{meta}<span className="k-foldcard-chev" /></span>
          {frame.on && <SectionMenu frame={frame} />}
        </span>
      </div>
      <div id={body} className="k-foldcard-body" hidden={!open}>{children}</div>
    </section>
  );
}
