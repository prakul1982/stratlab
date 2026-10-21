import { Badge } from "./kit";
import { planOf } from "../lib/plans";
import type { NavPage } from "../lib/nav";
import { NEW_SINCE } from "../lib/nav";
import { useApp } from "../lib/app";
import { featureTag } from "../lib/offer";
import { gateFor } from "../lib/gates";

/** The small tags on a page's card: "New" for what shipped lately and the plan, when the page is on a paid one. A paid
 * page the person can use today without that plan (early access, the launch offer) says "open now", as Pricing does. */
export function PageTags({ page }: { page: NavPage }) {
  const { me } = useApp();
  // a page with a paid part carries its plan from lib/gates.ts when nav.ts names none (R76-002: Positioning, Journal and
  // the rest had no tag); looked up here, not in nav.ts, so the public pages that use the menu don't load the plans
  const gate = gateFor(page.to);
  const flag = page.flag ?? gate?.feature;
  const plan = flag ? planOf(flag) : "free";
  if (!page.isNew && plan === "free") return null;
  const part = gate?.whole === false;       // lib/gates.ts: the lock is for whole pages only (as in the menu)
  const tag = plan !== "free" ? featureTag(plan, me?.offer, { paid: me?.paid_plan ?? me?.plan, canUse: !!(flag && me?.plan_info?.features?.[flag]), part }) : null;
  return (
    <span className="page-tags">
      {page.isNew && <span title={`Shipped by ${NEW_SINCE}`}><Badge tone="ok" dot={false}>New</Badge></span>}
      {tag && <span title={tag.why}><Badge tone="plain" dot={false}>{tag.label}</Badge><span className="sr-only"> ({tag.why})</span></span>}
    </span>
  );
}
