import type { MouseEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { useApp } from "../lib/app";
import { FEATURES, resolve } from "../lib/features";
import { gateFor } from "../lib/gates";
import { ALL_GROUPS, NAV, locate, startOf, type NavGroup, type SpaceId } from "../lib/nav";
import { PLAN_NAME, planOf } from "../lib/plans";
import { DataTable, type Column } from "./kit";
import { MoreTools, type ToolRow } from "./MoreTools";
import "../pages/trade/trade.css";
import { scrollBehavior } from "../lib/motion";

type Tile = { id: string; title: string; what: string; to: string; flag?: string };

/** Everything StratLab can do, in the menu's own shape (IA-1): each of this space's tools (the tabs of its menu entries, and the
 * tools inside them people look for by name: "Test on a whole group" under Strategies) as rows of one table, then every other
 * space's entries as a second, so the deeper tools aren't hidden and nobody faces a wall of equal choices. All of it in one
 * closed row that says how many tools it holds (owner, 5 Nov: "make it like a dropdown everywhere"; it was a wall of cards).
 * `hide` leaves out the pages (by address) the page above already links to, so a space's home offers each one once. `space`:
 * whose entries come first; left out, the space the person came for. */
export function Explore({ title = "More you can do", hide = [], space }: { title?: string; hide?: string[]; space?: SpaceId }) {
  const { notebooks, level, focus, me } = useApp();
  // a tool the plan doesn't include says which plan has it, on the tile, before the click (DP1-020)
  const lockedOn = (flag?: string) => (flag && me?.plan_info.features?.[flag] === false ? PLAN_NAME[planOf(flag)] : null);
  const loc = useLocation();
  const latest = notebooks?.[0] ? { id: notebooks[0].id } : null;
  const own: SpaceId = space ?? (focus === "invest" || focus === "money" ? focus : "trade");
  // a card never points at the page it is on
  const here = loc.pathname + loc.search;
  const showable = (to: string) => !hide.includes(to.split(/[?#]/)[0]) && resolve(to, loc.pathname, latest) !== here;
  // a tab of the entry, the plan it needs when it is a paid page as a whole (the menu's lock), and the named tools that live inside it
  const tilesOf = (g: NavGroup): Tile[] => [
    ...g.pages.filter((p) => showable(p.to)).map((p) => {
      const gate = gateFor(p.to);
      return { id: p.to, title: p.label, what: p.line, to: p.to, flag: gate?.whole ? gate.feature : undefined };
    }),
    ...FEATURES.filter((f) => f.home && f.goal && !g.pages.some((p) => p.to === f.to) && !(level === "new" && f.level === "advanced") && showable(f.to)
      && locate(resolve(f.to, "/", null))?.group.id === g.id)
      .map((f) => ({ id: f.id, title: f.title, what: f.what, to: f.to, flag: f.flag })),
  ];
  const sections = NAV[own].groups.map((g) => ({ g, tiles: tilesOf(g) })).filter((s) => s.tiles.length);
  const elsewhere = ALL_GROUPS.filter(({ space: s, group }) => s !== own && !NAV[own].groups.includes(group));
  // the box of a notebook's own page ("Describe your idea") when the tool is the page you are on: brought into view, not opened again
  const open = (to: string) => (e: MouseEvent<HTMLAnchorElement>) => {
    if (resolve(to, loc.pathname, latest) !== here) return;
    e.preventDefault();
    const box = document.getElementById("idea"); box?.scrollIntoView({ behavior: scrollBehavior(), block: "center" }); box?.focus();
  };
  const rows: ToolRow[] = sections.flatMap(({ g, tiles }) => tiles.map((f) => {
    const plan = lockedOn(f.flag);
    const tag = plan ? `On the ${plan} plan` : f.to.startsWith("@") && !latest ? "Starts with a notebook" : null;
    return { id: `${g.id}:${f.id}`, title: f.title, line: f.what, to: resolve(f.to, loc.pathname, latest), group: g.label, groupId: g.id,
      tag: tag && <span className="k-more-lock">{tag}</span>, onClick: open(f.to) };
  }));
  type Row = (typeof elsewhere)[number];
  const cols: Column<Row>[] = [
    { key: "entry", header: "Menu entry", rowHeader: true, cell: ({ space: s, group }) => <Link className="link" to={startOf(group, s)}>{group.label}</Link> },
    { key: "space", header: "Space", cell: ({ space: s }) => NAV[s].label },
    { key: "tabs", header: "What is in it", wrap: true, cell: ({ group }) => (group.pages.length > 1 ? group.pages.map((p) => p.label).join(", ") : group.pages[0].line) },
  ];
  // no "Search everything" here: the menu's search box is on every page, and a second one read as another search (DD-002)
  return (
    <MoreTools id="explore" title={title} rows={rows}>
      {elsewhere.length > 0 && (
        <div className="k-stack" data-entry="elsewhere">
          <h3 className="k-sub">Elsewhere in StratLab</h3>
          <DataTable stack label="Menu entries in the other spaces" columns={cols} rows={elsewhere} rowKey={(r) => `${r.space}:${r.group.id}`} />
        </div>
      )}
    </MoreTools>
  );
}
