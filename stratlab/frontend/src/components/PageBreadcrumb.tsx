import { useLocation } from "react-router-dom";
import { Breadcrumb } from "./kit";
import { MINE_HOME } from "../lib/spaces";
import { NAV, groupPath, locate, locateGroup } from "../lib/nav";
import { usePins } from "../lib/pins";

/** The personal pages that are not in a space: "Mine › Settings". */
const PERSONAL: Record<string, string> = { "/account": "Account", "/settings": "Settings", "/assistant": "AI assistant", "/app": "Get the app", "/invite": "Invite friends" };

/** The breadcrumb for the page showing, drawn from the one map of pages (lib/nav.ts): "Space › Group › Page ▾". It sits
 * at the top of every page that is in the menu, so no page needs its own row of tabs. */
export function PageBreadcrumb() {
  const { pathname } = useLocation();
  const pins = usePins();
  if (pathname === MINE_HOME) return <Breadcrumb trail={[{ label: "Mine", to: MINE_HOME }]} />;
  // every space's home starts the same way as My space: its one-word name (R1-028)
  const home = (Object.keys(NAV) as (keyof typeof NAV)[]).find((k) => NAV[k].home === pathname);
  if (home) return <Breadcrumb trail={[{ label: NAV[home].label, to: NAV[home].home }]} />;
  if (pathname === "/features") return <Breadcrumb trail={[{ label: "StratLab", to: "/" }]} page="All features" />;
  if (pathname === "/admin" || pathname.startsWith("/admin/")) return <Breadcrumb trail={[{ label: "Mine", to: MINE_HOME }]} page="Admin" />;
  if (PERSONAL[pathname]) return <Breadcrumb trail={[{ label: "Mine", to: MINE_HOME }]} page={PERSONAL[pathname]} />;
  const g = locateGroup(pathname);
  if (g) return <Breadcrumb trail={[{ label: NAV[g.space].label, to: NAV[g.space].home }, { label: g.group.label, to: groupPath(g.space, g.group) }]} />;
  const at = locate(pathname);
  if (!at) return null;
  const { space, group, page } = at;
  return (
    <Breadcrumb
      trail={[{ label: NAV[space].label, to: NAV[space].home }, { label: group.label, to: groupPath(space, group) }]}
      page={page.label}
      siblings={group.pages.map((p) => ({ to: p.to, label: p.label, current: p.to === page.to }))}
      seeAll={{ label: `All of ${group.label}`, to: groupPath(space, group) }}
      pinned={pins.has(page.to)} onTogglePin={() => pins.toggle(page.to)}
    />
  );
}
