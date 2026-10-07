import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { CFG } from "../lib/api";
import { useApp } from "../lib/app";
import { featureName, gateFor, gatePlan } from "../lib/gates";
import { unlockHint, EARLY_ACCESS_EMAIL } from "../lib/offer";
import { PLAN_NAME } from "../lib/plans";
import { Notice } from "./kit";

/** At the top of a page holding a paid feature the person's plan doesn't include: which plan has it, and what to do,
 * honestly (no checkout while paid plans aren't on sale). The server refuses the feature either way (plans.allows).
 * A page that already says it in its own plan note (PlanNote) keeps that one: one note, not two. */
export function PageLock() {
  const { me } = useApp();
  const { pathname } = useLocation();
  const gate = gateFor(pathname);
  const locked = !!gate && !!me && me.plan_info?.features?.[gate.feature] === false;
  const [own, setOwn] = useState(false);
  useEffect(() => {
    setOwn(false);
    if (!locked) return;
    const look = () => setOwn(!!document.querySelector("main .plan-note:not(.page-lock)"));
    look();
    const mo = new MutationObserver(look);
    const main = document.querySelector("main");
    if (main) mo.observe(main, { childList: true, subtree: true });
    return () => mo.disconnect();
  }, [locked, pathname]);
  if (!locked || own || !gate || !me) return null;
  const plan = PLAN_NAME[gatePlan(gate)];
  const yours = PLAN_NAME[(me.plan ?? "free") as "free" | "basic" | "pro"] ?? "Free";
  const what = featureName(gate.feature);
  const hint = unlockHint(me.offer, CFG.CONTACT_EMAIL || EARLY_ACCESS_EMAIL);
  return (
    <Notice className="page-lock plan-note" label={`${plan} feature`} action={{ label: "See plans", to: "/plans" }}>
      <b>🔒 {gate.whole ? `This page is a ${plan} feature.` : `Part of this page is on ${plan}.`}</b>{" "}
      {gate.whole ? `${what}. You're on ${yours}.` : `${what}: on the ${plan} plan. You're on ${yours}; the rest of the page is yours.`}{" "}
      {hint}
    </Notice>
  );
}
