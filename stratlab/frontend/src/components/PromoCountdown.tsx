import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Notice } from "./kit";
import { useApp } from "../lib/app";
import { endsAt } from "../lib/offer";

/** "3 days 4 hours", "5 hours 10 minutes" or "12 minutes": the two largest units left. */
function timeLeft(ms: number): string {
  const min = Math.max(0, Math.floor(ms / 60000));
  const d = Math.floor(min / 1440), h = Math.floor((min % 1440) / 60), m = min % 60;
  const unit = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
  if (d) return h ? `${unit(d, "day")} ${unit(h, "hour")}` : unit(d, "day");
  if (h) return m ? `${unit(h, "hour")} ${unit(m, "minute")}` : unit(h, "hour");
  return unit(Math.max(1, m), "minute");
}

/** While the launch offer runs: how long is left, on Home and Plans. Gone by itself when it ends. On Home it can be put
 * away like the site-wide note (the same key: putting either away hides both), R45A-010; Plans always shows it. */
export function PromoCountdown({ plansLink = true }: { plansLink?: boolean }) {
  const { me } = useApp();
  const until = me?.promo?.until;
  const [now, setNow] = useState(() => Date.now());
  const key = until ? `stratlab.promo.seen.${until.slice(0, 10)}` : "";
  const [hidden, setHidden] = useState(() => { try { return !!key && localStorage.getItem(key) === "1"; } catch { return false; } });
  useEffect(() => {
    if (!until) return;
    const t = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(t);
  }, [until]);
  const end = until ? new Date(until).getTime() : NaN;
  if (!until || !Number.isFinite(end) || end <= now || (plansLink && hidden)) return null;
  const day = endsAt(until);
  const hide = () => { try { localStorage.setItem(key, "1"); } catch { /* storage off */ } setHidden(true); };
  return (
    <Notice className="promo-countdown" role="status"
      actions={plansLink ? <><Link className="btn sm promo-plans" to="/plans">See plans</Link><button type="button" className="btn sm quiet" onClick={hide}>Got it</button></> : undefined}>
      <b>Launch offer:</b> every Pro feature is free for <b className="promo-left">{timeLeft(end - now)}</b> more (until {day}).<span className="promo-more"> After that, your plan's limits apply again.</span>
    </Notice>
  );
}
