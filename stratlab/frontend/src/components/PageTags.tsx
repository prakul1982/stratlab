import { Badge } from "./kit";
import { planOf } from "../lib/plans";
import type { NavPage } from "../lib/nav";
import { NEW_SINCE } from "../lib/nav";
import { useApp } from "../lib/app";
import { featureTag } from "../lib/offer";

/** The small tags on a page's card: "New" for what shipped lately and the plan, when the page is on a paid one. A paid
 * page the person can use today without that plan (early access, the launch offer) says "open now", as Pricing does. */
export function PageTags({ page }: { page: NavPage }) {
  const { me } = useApp();
  const plan = page.flag ? planOf(page.flag) : "free";
  if (!page.isNew && plan === "free") return null;
  const tag = plan !== "free" ? featureTag(plan, me?.offer, { paid: me?.paid_plan ?? me?.plan, canUse: !!(page.flag && me?.plan_info?.features?.[page.flag]) }) : null;
  return (
    <span className="page-tags">
      {page.isNew && <span title={`Shipped by ${NEW_SINCE}`}><Badge tone="ok" dot={false}>New</Badge></span>}
      {tag && <span title={tag.why}><Badge tone="plain" dot={false}>{tag.label}</Badge><span className="sr-only"> ({tag.why})</span></span>}
    </span>
  );
}
