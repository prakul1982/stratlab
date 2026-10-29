import { Link, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { FEATURES, resolve } from "../lib/features";
import { gateFor } from "../lib/gates";
import { ALL_GROUPS, NAV, locate, startOf, type NavGroup, type SpaceId } from "../lib/nav";
import { PLAN_NAME, planOf } from "../lib/plans";
import { DataTable, type Column } from "./kit";
import { TileGrid } from "./TileGrid";
import "../pages/trade/trade.css";
import { scrollBehavior } from "../lib/motion";

type Tile = { id: string; title: string; what: string; to: string; flag?: string };

/** Everything StratLab can do, in the menu's own shape (IA-1): each of this space's menu entries with its tabs as tiles (and
 * the tools inside them people look for by name: "Test on a whole group" under Strategies), then every other space's entries
 * as one table, so the deeper tools aren't hidden and nobody faces a wall of equal choices. Every entry shows, none folded
 * behind a button (the owner, 29 Oct: a button that folded them away hid most of them). `hide` leaves out the pages (by
 * address) the page above already links to, so a space's home offers each one once. `space`: whose entries come first; left
 * out, the space the person came for. */
export function Explore({ title = "More you can do", hide = [], space }: { title?: string; hide?: string[]; space?: SpaceId }) {
  const { notebooks, level, focus, me } = useApp();
  // a tool the plan doesn't include says which plan has it, on the tile, before the click (DP1-020)
  const lockedOn = (flag?: string) => (flag && me?.plan_info.features?.[flag] === false ? PLAN_NAME[planOf(flag)] : null);
  const nav = useNavigate();
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
  // an entry with one tile left would be a heading over a card saying the same, stretched across the page: those share one row at the end
  const many = sections.filter((x) => x.tiles.length > 1);
  const ones = sections.filter((x) => x.tiles.length === 1).flatMap((x) => x.tiles);
  const elsewhere = ALL_GROUPS.filter(({ space: s, group }) => s !== own && !NAV[own].groups.includes(group));
  const open = (to: string) => {
    const dest = resolve(to, loc.pathname, latest);
    if (dest === loc.pathname + loc.search) { const box = document.getElementById("idea"); box?.scrollIntoView({ behavior: scrollBehavior(), block: "center" }); box?.focus(); }
    else nav(dest);
  };
  type Row = (typeof elsewhere)[number];
  const cols: Column<Row>[] = [
    { key: "entry", header: "Menu entry", rowHeader: true, cell: ({ space: s, group }) => <Link className="link" to={startOf(group, s)}>{group.label}</Link> },
    { key: "space", header: "Space", cell: ({ space: s }) => NAV[s].label },
    { key: "tabs", header: "What is in it", wrap: true, cell: ({ group }) => (group.pages.length > 1 ? group.pages.map((p) => p.label).join(", ") : group.pages[0].line) },
  ];
  return (
    <section className="k-stack k-explore" aria-labelledby="explore-h">
      {/* no "Search everything" here: the menu's search box is on every page, and a second one read as another search (DD-002) */}
      <h2 id="explore-h" className="h2">{title}</h2>
      {[...many, ...(ones.length ? [{ g: { id: "more", label: `More in ${NAV[own].label}`, blurb: "" }, tiles: ones }] : [])].map(({ g, tiles }) => (
        <div key={g.id} className="k-stack" data-entry={g.id}>
          <div className="k-stack k-tight">
            <b>{g.label}</b>
            {g.blurb && <span className="small muted">{g.blurb}</span>}
          </div>
          <TileGrid className="explore-grid">
            {tiles.map((f) => (
              <button key={f.id} className="k-linkcard explore-card" onClick={() => open(f.to)}>
                <b>{f.title}</b>
                <span className="small muted">{f.what}</span>
                <span className="small explore-go">{lockedOn(f.flag) ? `On the ${lockedOn(f.flag)} plan →` : f.to.startsWith("@") && !latest ? "Starts with a notebook →" : "Open →"}</span>
              </button>
            ))}
          </TileGrid>
        </div>
      ))}
      {elsewhere.length > 0 && (
        <div className="k-stack" data-entry="elsewhere">
          <b>Elsewhere in StratLab</b>
          <DataTable stack label="Menu entries in the other spaces" columns={cols} rows={elsewhere} rowKey={(r) => `${r.space}:${r.group.id}`} />
        </div>
      )}
    </section>
  );
}
