import type { ReactNode } from "react";
import { asOf as asOfText } from "../../lib/format";
import { Info } from "../ui";
import { Badge } from "./Badge";

/** The top of every page: where you are ("Invest · Research"), the title, one line on what the page is for, and when its
 * data is from (a "Data up to 30 Sep 2026" badge, with an (i) for where the numbers come from). `asOf` is an ISO date or
 * time; leave it out for a page without dated data. A time is written in the market's zone with the zone's name
 * ("7 Oct 2026, 13:26 IST"): India's, unless `asOfTz` names another (`marketTz("US")` on a US page). */
export function PageHeader({ eyebrow, title, lede, asOf, asOfLabel = "Data up to", asOfTz, info, infoLabel = "About this data", actions }: {
  eyebrow: string; title: string; lede?: ReactNode; asOf?: string | null; asOfLabel?: string; asOfTz?: string; info?: ReactNode; infoLabel?: string; actions?: ReactNode;
}) {
  const when = asOfText(asOf, { tz: asOfTz });
  // an (i) with nothing else to sit beside ends the lede's line, instead of standing alone on a row of its own
  const inline = !!info && !!lede && !when && !actions;
  return (
    <header className="k-page-head">
      <span className="k-eyebrow">{eyebrow}</span>
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
  );
}
