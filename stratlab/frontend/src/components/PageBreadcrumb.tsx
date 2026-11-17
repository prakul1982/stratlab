import { useLocation } from "react-router-dom";
import { Breadcrumb, usePhone } from "./kit";
import { MINE_HOME, MINE_NAME, type SpaceView } from "../lib/spaces";
import { NAV, groupPath, locate, locateGroup } from "../lib/nav";
import { usePins } from "../lib/pins";

/** The personal pages that are not in a space: "My space › Settings". Plans, Help and All features too, so every page of
 * the account menu has the same trail (DI-019: /plans and /help had none, /features said "StratLab › All features"). */
const PERSONAL: Record<string, string> = { "/account": "Account", "/settings": "Settings", "/assistant": "Connect an AI assistant", "/app": "Get the app", "/invite": "Invite friends",
  "/plans": "Plans", "/help": "Help", "/features": "All features" };
/** The menu entries My space's own menu links to (Shell's MINE_LINKS and MINE_GROUPS): opened from My space, their trail says so. */
const MINE_LINKED = ["/news"];
const MINE_ENTRIES = ["watch", "calendar"];

/** The breadcrumb for the page showing, drawn from the one map of pages (lib/nav.ts): "Space › Entry › Tab ▾" (IA-1), or
 * "Space › Page ▾" for an entry that is one page. On a laptop the tabs are the row beside it (HubTabs), so its menu is the
 * pin only; on a phone, where that row would push every title down (ui-lint R17), its menu lists the entry's tabs, as it
 * listed a group's pages before. The Calendar every space shares takes the space whose menu is showing. */
export function PageBreadcrumb({ mine = false, space: showing }: { mine?: boolean; space?: SpaceView }) {
  const { pathname } = useLocation();
  const pins = usePins();
  const phone = usePhone();
  if (pathname === MINE_HOME) return <Breadcrumb trail={[{ label: MINE_NAME, to: MINE_HOME }]} />;
  // every space's home starts the same way as My space: its one-word name (R1-028)
  const home = (Object.keys(NAV) as (keyof typeof NAV)[]).find((k) => NAV[k].home === pathname);
  if (home) return <Breadcrumb trail={[{ label: NAV[home].label, to: NAV[home].home }]} />;
  if (pathname === "/admin" || pathname.startsWith("/admin/")) return <Breadcrumb trail={[{ label: MINE_NAME, to: MINE_HOME }]} page="Admin" />;
  if (PERSONAL[pathname]) return <Breadcrumb trail={[{ label: MINE_NAME, to: MINE_HOME }]} page={PERSONAL[pathname]} />;
  const g = locateGroup(pathname);
  if (g) return <Breadcrumb trail={[{ label: NAV[g.space].label, to: NAV[g.space].home }, { label: g.group.label, to: groupPath(g.space, g.group) }]} />;
  const at = locate(pathname);
  if (!at) return null;
  const { group, page } = at;
  const pin = { pinned: pins.has(page.to), onTogglePin: () => pins.toggle(page.to) };
  const one = group.pages.length === 1;
  const tabs = !one && phone ? group.pages.map((p) => ({ to: p.to, label: p.label, current: p.to === page.to })) : [];
  // opened from My space's own menu (Briefs, Watchlist, Calendar), the trail is My space's, as the menu beside it is
  // (DI-017: Briefs showed My space in the menu and "Invest › Company news" above the page)
  if (mine && (MINE_LINKED.includes(page.to) || MINE_ENTRIES.includes(group.id)))
    return <Breadcrumb trail={[{ label: MINE_NAME, to: MINE_HOME }, ...(one || MINE_LINKED.includes(page.to) ? [] : [{ label: group.label, to: group.pages[0].to }])]} page={page.label} siblings={tabs} {...pin} />;
  const space = group.start && showing && showing !== "mine" ? showing : at.space;
  return (
    <Breadcrumb
      trail={[{ label: NAV[space].label, to: NAV[space].home }, ...(one ? [] : [{ label: group.label, to: groupPath(space, group) }])]}
      page={page.label} siblings={tabs} {...pin}
    />
  );
}
