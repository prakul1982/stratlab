import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { gateFor, gatePlan } from "../lib/gates";
import { PLAN_NAME } from "../lib/plans";
import type { Located } from "../lib/nav";

/** The other views of a tab that keep the tabs in view: the watchlist's "At a glance", Positioning's stock futures. A tab's
 * own detail pages (a company, a notebook, an IPO, a session) have the breadcrumb, not the row of tabs. */
const TAB_VIEWS = ["/research/investor", "/trade/positioning/stocks"];

/** IA-1: the tabs of a menu entry, under the breadcrumb on each of its pages ("Find stocks: Figures · Chart rules ·
 * Filings"). Each tab is a page at the address it always had, so a link to it opens it and Back goes to the tab before.
 * A tab that is a paid page this plan lacks carries the lock the menu used to show (lib/gates.ts), so the plan locks are
 * the ones they were. Links, not ARIA tabs: each one opens a page. They wrap on a phone, never cut off at its edge. */
export function HubTabs({ at, path }: { at: Located; path: string }) {
  const { me } = useApp();
  const p = path.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  if (at.group.pages.length < 2 || (p !== at.page.to && !TAB_VIEWS.includes(p))) return null;
  return (
    <nav className="hub-tabs" aria-label={at.group.label} data-testid="hub-tabs" data-group={at.group.id}>
      {at.group.pages.map((t) => {
        const gate = gateFor(t.to);
        const off = !!gate && me?.plan_info?.features?.[gate.feature] === false;
        const locked = off && gate!.whole;
        const plan = gate ? PLAN_NAME[gatePlan(gate)] : "";
        const here = t.to === at.page.to;
        return (
          <Link key={t.to} to={t.to} className={`hub-tab${here ? " active" : ""}`} aria-current={here ? "page" : undefined}
            title={off ? `${t.line} (${gate!.whole ? "" : "part of it "}on the ${plan} plan)` : t.line}>
            {t.label}{locked && <span className="side-lock" data-plan={plan} aria-hidden="true" />}
          </Link>
        );
      })}
    </nav>
  );
}
