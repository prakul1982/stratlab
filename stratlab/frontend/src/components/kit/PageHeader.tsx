import type { ReactNode } from "react";
import { asOf as asOfText } from "../../lib/format";
import { Info } from "../ui";
import { Badge } from "./Badge";

/** The top of every page: where you are ("Invest · Research"), the title, one line on what the page is for, and when its
 * data is from (a "Data up to 30 Sep 2026" badge, with an (i) for where the numbers come from). `asOf` is an ISO date or
 * time; leave it out for a page without dated data. */
export function PageHeader({ eyebrow, title, lede, asOf, asOfLabel = "Data up to", info, infoLabel = "About this data", actions }: {
  eyebrow: string; title: string; lede?: ReactNode; asOf?: string | null; asOfLabel?: string; info?: ReactNode; infoLabel?: string; actions?: ReactNode;
}) {
  const when = asOfText(asOf);
  return (
    <header className="k-page-head">
      <span className="k-eyebrow">{eyebrow}</span>
      <h1 className="k-h1">{title}</h1>
      {lede && <p className="k-lede">{lede}</p>}
      {(when || info || actions) && (
        <div className="k-meta">
          {when && <Badge>{asOfLabel} {when}</Badge>}
          {info && <Info label={infoLabel}>{info}</Info>}
          {actions}
        </div>
      )}
    </header>
  );
}
