import { Link } from "react-router-dom";
import { useFoChanges } from "../lib/foChanges";
import { Info } from "./ui";

/** A stock's or index's coming F&O contract changes as small factual badges ("Leaves F&O after 28 Jul", "Lot 75→65 from
 * 31 Dec"), with an (i) that says each change in full. Nothing for a symbol with none, or outside India. `plain` leaves
 * the (i) out, for badges inside a button or a link, where the badge's title carries the words. */
export function FoBadges({ region, symbol, plain }: { region: string | undefined; symbol: string; plain?: boolean }) {
  const v = useFoChanges(region === "IN" && !!symbol);
  const mine = region === "IN" && v ? v.badges[symbol.toUpperCase()] ?? [] : [];
  if (!mine.length) return null;
  return (
    <span className="surv" data-fo-changes={symbol}>
      {mine.map((b) => <span key={b.kind + b.date} className="surv-badge fo-badge" title={b.text}>{b.short}</span>)}
      {!plain && <Info label={`${symbol}'s F&O contract changes`}>
        {mine.map((b) => <span key={b.kind + b.date} className="surv-line">{b.text}</span>)}
        <span className="surv-line">From the exchange's F&amp;O contract file and circulars. <Link className="link" to="/trade/fo-changes">Every change</Link></span>
      </Info>}
    </span>
  );
}
