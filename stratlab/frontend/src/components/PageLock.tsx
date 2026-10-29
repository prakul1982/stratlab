import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { CFG } from "../lib/api";
import { useApp } from "../lib/app";
import { featureName, gateFor, gatePlan } from "../lib/gates";
import { unlockHint, EARLY_ACCESS_EMAIL } from "../lib/offer";
import { PLAN_NAME } from "../lib/plans";
import { lockWords } from "../lib/lockText";
import { useLockSlot } from "../lib/lockSlot";
import { usePlanPrice } from "../lib/currency";
import { Notice } from "./kit";
import { PlanActions } from "./PlanInterest";
import { Lock } from "./Icons";

/** At the top of a page holding a paid feature the person's plan doesn't include: which plan has it, and what to do,
 * honestly (no checkout while paid plans aren't on sale). The server refuses the feature either way (plans.allows).
 * A page that already says it in its own plan note (PlanNote) keeps that one: one note, not two. */
export function PageLock() {
  const { me } = useApp();
  const { pathname } = useLocation();
  const gate = gateFor(pathname);
  const locked = !!gate && !!me && me.plan_info?.features?.[gate.feature] === false;
  const unlocks = locked && gate ? gatePlan(gate) : null;
  const price = usePlanPrice(unlocks === "basic" || unlocks === "pro" ? unlocks : null);
  const [own, setOwn] = useState(false);
  const slot = useLockSlot();           // the page's title draws it: the note goes under the title, on every page (RC7-003)
  useEffect(() => {
    setOwn(false);
    if (!locked) return;
    // a page that words each of its locks where it applies (Tax tools: Basic's dividend detail, Pro's amounts) says so with
    // data-plan-notes, so its tabs don't get the page's note on one tab and their own on another (DP2-012)
    const look = () => setOwn(!!document.querySelector("main .plan-note:not(.page-lock), main [data-plan-notes]"));
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
  const hint = unlockHint(me.offer, CFG.CONTACT_EMAIL || EARLY_ACCESS_EMAIL, price);
  const note = (
    <Notice className="page-lock plan-note" label={`${plan} feature`} actions={<PlanActions source="lock" />}>
      <b><Lock />{gate.whole ? `This page is on the ${plan} plan.` : `Part of this page is on the ${plan} plan.`}</b>{" "}
      {lockWords(what, plan, yours, gate.whole)}{" "}
      {hint}
    </Notice>
  );
  // under the page's title when it has one; at the top for a page with no title component
  return slot && slot.isConnected ? createPortal(note, slot) : note;
}
