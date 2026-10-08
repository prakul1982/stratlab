import { useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { plansCall } from "../lib/offer";
import { JOINED, JOIN_LABEL, joinInterest, leaveInterest, useInterest, type InterestSource } from "../lib/planInterest";
import { track } from "../lib/analytics";

/* While paid plans can't be bought, a lock or a limit offers "Tell me when plans open" (one tap, kept per person)
 * where it used to offer a "See plans" that led to "Opens soon". Once they can be bought, it is "See plans" again. */

/** The button for a lock banner or the Plans page: "Tell me when plans open", then "You're on the list" with Undo. */
export function PlanInterestButton({ source, quiet }: { source: InterestSource; quiet?: boolean }) {
  const { me, notify, fail } = useApp();
  const have = useInterest(!!me);
  if (!me) return null;
  if (have?.registered) return (
    <span className="k-row k-tight" role="status">
      <span className="k-note">You're on the list. We'll tell you when plans open.</span>
      <button type="button" className="btn quiet sm" onClick={() => void leaveInterest().then(() => notify("Removed. We won't tell you.")).catch(fail)}>Undo</button>
    </span>
  );
  return (
    <button type="button" className={`btn sm${quiet ? " quiet" : ""}`} disabled={have === null}
      onClick={() => { track("plan interest", { source }); void joinInterest(source).then(() => notify(JOINED)).catch(fail); }}>{JOIN_LABEL}</button>
  );
}

/** What a lock banner offers: "See plans" once they can be bought, else the interest button. Goes in a Notice's `actions`. */
export function PlanActions({ source = "lock" }: { source?: InterestSource }) {
  const { me } = useApp();
  if (!me || plansCall(me.offer, false).kind === "see") return <Link className="btn sm" to="/plans">See plans</Link>;
  return <PlanInterestButton source={source} />;
}

/** The same for a sentence: a link-looking button in the words. */
export function PlanInline({ source = "inline" }: { source?: InterestSource }) {
  const { me, notify, fail } = useApp();
  const have = useInterest(!!me);
  if (!me || plansCall(me.offer, false).kind === "see") return <Link className="link" to="/plans">See plans</Link>;
  if (have?.registered) return <span>You're on the list; we'll tell you when plans open.</span>;
  return <button type="button" className="link" disabled={have === null} onClick={() => void joinInterest(source).then(() => notify(JOINED)).catch(fail)}>{JOIN_LABEL}</button>;
}

/** For a state box's one button (an EmptyState's `action`). */
export function usePlansAction(source: InterestSource = "lock"): { label: string; to?: string; onClick?: () => void } {
  const { me, notify, fail } = useApp();
  const have = useInterest(!!me);
  const call = plansCall(me?.offer, !!have?.registered);
  if (call.kind === "see") return { label: call.label, to: "/plans" };
  return { label: call.label, onClick: () => { if (have?.registered) notify("You're on the list. We'll tell you when plans open."); else void joinInterest(source).then(() => notify(JOINED)).catch(fail); } };
}

/** A toast when a limit is reached: with "See plans", or "Tell me when plans open" while they can't be bought. */
export function usePlansToast(): (msg: string) => void {
  const { me, notify, fail } = useApp();
  const nav = useNavigate();
  const offer = me?.offer;
  return useCallback((msg: string) => {
    if (plansCall(offer, false).kind === "see") notify(msg, { label: "See plans", run: () => nav("/plans") });
    else notify(msg, { label: JOIN_LABEL, run: () => void joinInterest("limit").then(() => notify(JOINED)).catch(fail) });
  }, [offer, notify, fail, nav]);
}
