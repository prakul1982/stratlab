import { Badge } from "./kit";
import { Lock } from "./Icons";
import { planOf } from "../lib/plans";
import type { NavPage } from "../lib/nav";
import { useApp } from "../lib/app";
import { featureTag } from "../lib/offer";
import { gateFor } from "../lib/gates";

/** The small tag on a page's card: the plan, when the page is on a paid one this viewer lacks (no "New" tags: everything
 * is new at launch, owner 25 Oct). A paid
 * page the person can use today without that plan (early access, the launch offer) says "open now", as Pricing does. */
export function PageTags({ page }: { page: NavPage }) {
  const { me } = useApp();
  // a page with a paid part carries its plan from lib/gates.ts when nav.ts names none (R76-002: Positioning, Journal and
  // the rest had no tag); looked up here, not in nav.ts, so the public pages that use the menu don't load the plans
  const gate = gateFor(page.to);
  const flag = page.flag ?? gate?.feature;
  const plan = flag ? planOf(flag) : "free";
  if (plan === "free") return null;
  // lib/gates.ts: the lock is for whole pages only (as in the menu); a page with a paid part and no gate of its own says so in
  // nav.ts (`part`: My Holdings' filings and dividends, DP2-009)
  const part = gate ? gate.whole === false : !!page.part;
  const got = featureTag(plan, me?.offer, { paid: me?.paid_plan ?? me?.plan, canUse: !!(flag && me?.plan_info?.features?.[flag]), part });
  // a page the person's own plan has needs no plan badge: badges say what is locked (or open only for now) for this viewer
  // (DI-031: Basic saw "Basic (On the Basic plan)" on every page it already had)
  const tag = got && (got.locked || got.label !== (plan === "pro" ? "Pro" : "Basic")) ? got : null;
  if (!tag) return null;
  return (
    <span className="page-tags">
      {tag && <span title={tag.why}><Badge tone="plain" dot={false}>{tag.locked && <Lock size={12} />}{tag.label}</Badge><span className="sr-only"> ({tag.why})</span></span>}
    </span>
  );
}
