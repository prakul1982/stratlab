import { Link } from "react-router-dom";
import { useEvents } from "../lib/marketEvents";
import { Info } from "./ui";

/** A stock going into or out of a main index, as a small factual badge ("Joins NIFTY 50 from 30 Sep"), with an (i) that
 * says it in full. Nothing for a stock with no change, or outside India. */
export function IndexBadges({ region, symbol }: { region: string | undefined; symbol: string }) {
  const v = useEvents(region === "IN" && !!symbol);
  const mine = region === "IN" && v ? v.badges[symbol.toUpperCase()] ?? [] : [];
  if (!mine.length) return null;
  return (
    <span className="surv" data-index-badges={symbol}>
      {mine.map((b) => <span key={b.way + b.index} className="surv-badge fo-badge" title={b.text}>{b.short}</span>)}
      <Info label={`${symbol}'s index changes`}>
        {mine.map((b) => <span key={b.way + b.index} className="surv-line">{b.text}</span>)}
        <span className="surv-line">From the index provider's press releases. <Link className="link" to="/trade/events">Market events</Link></span>
      </Info>
    </span>
  );
}
