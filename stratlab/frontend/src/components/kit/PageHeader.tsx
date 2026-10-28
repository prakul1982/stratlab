import { useRef, type ReactNode } from "react";
import { lockSlotRef } from "../../lib/lockSlot";
import { asOf as asOfText } from "../../lib/format";
import { Info } from "../ui";
import { Badge } from "./Badge";

/** The top of every page: where you are ("Invest · Research"), the title, one line on what the page is for, and when its
 * data is from (a "Data up to 30 Sep 2026" badge, with an (i) for where the numbers come from). `asOf` is an ISO date or
 * time; leave it out for a page without dated data. A time is written in the market's zone with the zone's name
 * ("7 Oct 2026, 13:26 IST"): India's, unless `asOfTz` names another (`marketTz("US")` on a US page). */
export function PageHeader({ eyebrow, title, lede, asOf, asOfLabel = "Data up to", asOfTz, info, infoLabel = "About this data", actions }: {
  /** Left out where it would only repeat the title ("SETTINGS / Settings", DI-019): the breadcrumb gives the place. */
  eyebrow?: string; title: string; lede?: ReactNode; asOf?: string | null; asOfLabel?: string; asOfTz?: string; info?: ReactNode; infoLabel?: string; actions?: ReactNode;
}) {
  const when = asOfText(asOf, { tz: asOfTz });
  // an (i) with nothing else to sit beside ends the lede's line, instead of standing alone on a row of its own
  const inline = !!info && !!lede && !when && !actions;
  const slot = useRef<HTMLDivElement | null>(null);
  return (
    <>
    <header className="k-page-head">
      {eyebrow && <span className="k-eyebrow">{eyebrow}</span>}
      <h1 className="k-h1">{title}</h1>
      {lede && (inline ? <div className="k-lede">{lede} <Info label={infoLabel}>{info}</Info></div> : <p className="k-lede">{lede}</p>)}
      {(when || (info && !inline) || actions) && (
        <div className="k-meta">
          {when && <Badge>{asOfLabel} {when}</Badge>}
          {info && !inline && <Info label={infoLabel}>{info}</Info>}
          {actions}
        </div>
      )}
    </header>
    {/* where the page's plan-lock note goes, straight under the title on every page (RC7-003; lib/lockSlot.ts) */}
    <div className="page-lock-slot" ref={(el) => { if (el) { slot.current = el; lockSlotRef(el); } else { lockSlotRef(null, slot.current); slot.current = null; } }} />
    </>
  );
}
