import { Badge } from "./kit";
import { PLAN_NAME, planOf } from "../lib/plans";
import type { NavPage } from "../lib/nav";
import { NEW_SINCE } from "../lib/nav";

/** The small tags on a page's card: "New" for what shipped lately and the plan, when the page is on a paid one. */
export function PageTags({ page }: { page: NavPage }) {
  const plan = page.flag ? planOf(page.flag) : "free";
  if (!page.isNew && plan === "free") return null;
  return (
    <span className="page-tags">
      {page.isNew && <span title={`Shipped by ${NEW_SINCE}`}><Badge tone="ok" dot={false}>New</Badge></span>}
      {plan !== "free" && <span title={`${PLAN_NAME[plan]} plan`}><Badge tone="plain" dot={false}>{PLAN_NAME[plan]}</Badge></span>}
    </span>
  );
}
