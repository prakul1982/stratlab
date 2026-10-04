import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { Bell, Book, Calendar, Chevron, Close, Compass, Layers, Library, Lens, Menu, News, Pin, Plus, Pulse, Receipt, Search, Sparkle, Upload, Wallet } from "./Icons";
import { Logo } from "./Logo";
import { AccountMenu, MarketsNow } from "./SideMenus";
import { FAMILIES, NAV_GROUPS, familyOf } from "../lib/navGroups";
import { ALL_GROUPS, SPACE_IDS, SPACES, spaceOf, type GroupId, type SpaceView } from "../lib/spaces";

// the pop-ups load when they first open, so they don't slow down the first page
const SearchPalette = lazy(() => import("./SearchPalette").then((m) => ({ default: m.SearchPalette })));
const LevelPrompt = lazy(() => import("./LevelPrompt").then((m) => ({ default: m.LevelPrompt })));
const Tour = lazy(() => import("./Tour").then((m) => ({ default: m.Tour })));

export const TOUR_SEEN = "stratlab.tour.v1";
const tourSeen = () => { try { return localStorage.getItem(TOUR_SEEN) === "1"; } catch { return true; } };

/** The menu lists this many notebooks (pinned first, then the latest); the rest are one tap away on the notebooks page. */
const SIDE_NOTEBOOKS = 6;

/** Icons a menu entry kept as data (NAV_GROUPS) can name. */
const ICONS: Record<string, (p: { size?: number }) => ReactNode> = { book: Book, receipt: Receipt, bell: Bell, lens: Lens, news: News, pin: Pin, pulse: Pulse, layers: Layers, library: Library, upload: Upload, search: Search, compass: Compass, wallet: Wallet, calendar: Calendar };
const SHUT_KEY = "stratlab.side.shut";
/** Which menu groups you closed, remembered on this device. */
function readShut(): Partial<Record<GroupId, boolean>> {
  try { return JSON.parse(localStorage.getItem(SHUT_KEY) || "{}") ?? {}; } catch { return {}; }
}
function saveShut(v: Partial<Record<GroupId, boolean>>) { try { localStorage.setItem(SHUT_KEY, JSON.stringify(v)); } catch { /* private mode */ } }


export function Shell({ children }: { children: ReactNode }) {
  const { notebooks, markets, theme, setTheme, me, level, focus, space, setSpace } = useApp();
  const [open, setOpen] = useState(false);
  const [shut, setShut] = useState(readShut);
  const [tour, setTour] = useState(false);
  const [search, setSearch] = useState(false);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearch((x) => !x); }
      else if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test((e.target as HTMLElement).tagName) && !(e.target as HTMLElement).isContentEditable) { e.preventDefault(); setSearch(true); }
    };
    const open = () => setSearch(true);
    window.addEventListener("keydown", k);
    window.addEventListener("stratlab:search", open);
    return () => { window.removeEventListener("keydown", k); window.removeEventListener("stratlab:search", open); };
  }, []);
  const [, tick] = useState(0);
  useEffect(() => { const t = window.setInterval(() => tick((x) => x + 1), 60000); return () => window.clearInterval(t); }, []);
  // ask the experience level once, then show the tour to anyone who hasn't seen it
  const askLevel = !!me && (!level || !focus);
  useEffect(() => { if (me && level && !tourSeen()) setTour(true); }, [me, level]);
  const loc = useLocation();
  const nav = useNavigate();
  useEffect(() => setOpen(false), [loc.pathname]);
  // Esc closes the drawer on a phone (a pop-up inside it closes first, on its own)
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open]);
  // a link into another space shows that space's menu, so where you are is always in it ("All" already shows it)
  const here = spaceOf(loc.pathname);
  useEffect(() => { if (here && space !== "all" && here !== space) setSpace(here, false); }, [here]);   // eslint-disable-line react-hooks/exhaustive-deps
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  // pinned first, then the latest; the one you have open always stays in the list
  const openId = loc.pathname.match(/^\/n\/([^/]+)/)?.[1];
  const sideNotebooks = notebooks && [...notebooks].sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
    .filter((n, i) => i < SIDE_NOTEBOOKS || n.id === openId);

  const path = loc.pathname;
  const fam = familyOf(path);
  const item = (to: string, icon: ReactNode, label: string, active?: boolean, title?: string) => (
    <NavLink key={to} to={to} title={title} {...(active === undefined ? {} : { className: () => (active ? "active" : ""), "aria-current": active ? "page" as const : false })}>{icon}{label}</NavLink>
  );
  // a few short groups instead of one long list; pages that share a section switch with tabs on the page
  const groups: Record<GroupId, { label: string; items: ReactNode[]; on: boolean }> = {
    research: { label: "Research", on: /^\/(research|news)/.test(path) && fam !== "watch", items: [
      item("/research", <Lens />, "Companies", path.startsWith("/research") && !fam),
      item("/news", <News />, "News"),
      item(FAMILIES.scans.home, <Search />, "Scans", fam === "scans", "Trend scan, screener, sector rotation and red flags"),
    ] },
    money: { label: "Money", on: SPACES.money.paths.test(path) && path !== SPACES.money.home, items: NAV_GROUPS.Money.map((e) => {
      const Icon = ICONS[e.icon ?? ""] ?? Compass;
      return item(e.to, <Icon />, e.label, undefined, e.title);
    }) },
    watch: { label: "Watch", on: fam === "watch" || path === "/alerts", items: [
      item(FAMILIES.watch.home, <Pin />, "Watchlist", fam === "watch", "Your watchlist, as a list or every company at a glance"),
      item("/alerts", <Bell />, "Alerts"),
    ] },
    notebooks: { label: "Notebooks", on: path.startsWith("/n/") || path === "/notebooks", items: [] },
    trading: { label: "Trading", on: /^\/(paper|options|import|library)/.test(path), items: [
      item("/options", <Layers />, "Options"),
      item("/paper", <Pulse />, "Paper trading"),
      item("/library", <Library />, "Strategy library"),
      item("/import", <Upload />, "Import a strategy"),
    ] },
  };
  // one space's groups, or every group (Trade's first) folded until opened
  const order: GroupId[] = space === "all" ? ALL_GROUPS : SPACES[space].groups;
  const isShut = (g: GroupId) => shut[g] ?? space === "all";
  const toggle = (g: GroupId) => setShut((s) => { const next = { ...s, [g]: !isShut(g) }; saveShut(next); return next; });
  // opening a page in a closed group opens that group, so where you are is always in view
  const activeGroup = order.find((g) => groups[g].on);
  useEffect(() => { if (activeGroup && isShut(activeGroup)) toggle(activeGroup); }, [activeGroup, space]);   // eslint-disable-line react-hooks/exhaustive-deps
  const allNotebooks = "/notebooks";
  const notebookList = (
    <>
      {notebooks === null && <span className="small muted side-note">Loading…</span>}
      {notebooks?.length === 0 && <span className="small muted side-note">None yet.</span>}
      {sideNotebooks?.map((n) => {
        const inst = n.instrument && "symbol" in n.instrument ? n.instrument.symbol : null;
        const count = n.summary?.experiments ?? 0;
        const verdict = n.summary?.last_verdict ? `last verdict: ${n.summary.last_verdict.replace("_", " ")}` : "no experiments yet";
        return (
          <NavLink key={n.id} to={`/n/${n.id}`} title={[n.name, inst, `${count} experiment${count === 1 ? "" : "s"}`, verdict].filter(Boolean).join(" · ")}
            className={({ isActive }) => `nb-link${isActive || path.startsWith(`/n/${n.id}/`) ? " active" : ""}`}>
            <span className="nb-dot"><span className={`vdot ${n.summary?.last_verdict ?? "none"}`} /></span>
            <span className="nb-text">{n.name}</span>
            {n.pinned && <span className="nb-pin" title="Pinned"><Pin size={13} filled /></span>}
          </NavLink>
        );
      })}
      {!!notebooks?.length && <Link to={allNotebooks} className="nb-more">{notebooks.length > SIDE_NOTEBOOKS ? `All ${notebooks.length} notebooks` : "All notebooks"}</Link>}
    </>
  );
  const sidebar = (
    <aside className={`sidebar${open ? " open" : ""}`} aria-label="Notebooks and navigation">
      <div className="side-top">
        <div className="side-brand">
          <Link to="/" className="brand" aria-label="StratLab home"><Logo size={40} /></Link>
          <button className="side-close" aria-label="Close menu" onClick={() => setOpen(false)}><Close size={18} /></button>
        </div>
        <SpaceSwitch space={space} onPick={(s) => setSpace(s)} />
        {space === "invest" || (space === "all" && focus === "invest")
          ? <button className="side-new" onClick={() => nav("/research")}><Lens size={16} />Look up a company</button>
          : space === "money" || (space === "all" && focus === "money")
          ? <button className="side-new" onClick={() => nav("/holdings")}><Book size={16} />Add your holdings</button>
          : <button className="side-new" onClick={() => nav("/new")}><Plus size={16} />New notebook</button>}
        <button className="search-btn" onClick={() => setSearch(true)} aria-label="Ask or do anything (Ctrl+K)">
          <Sparkle size={16} /><span>Ask or do anything</span><kbd>{/Mac/.test(navigator.platform) ? "⌘K" : "Ctrl K"}</kbd>
        </button>
      </div>
      <nav className="side-groups" aria-label="Main">
        {space !== "all" && (
          <div className="side-list">
            <NavLink to={SPACES[space].home} end><Compass size={16} />{SPACES[space].label} home</NavLink>
          </div>
        )}
        {order.map((g) => {
          const { label, items } = groups[g];
          const shutNow = isShut(g);
          return (
            <section key={g} className="side-group" data-group={g}>
              <div className="side-head">
                <button className="side-toggle" aria-expanded={!shutNow} aria-controls={`side-${g}`} onClick={() => toggle(g)}>
                  {label}<span className="side-chev" aria-hidden="true"><Chevron size={12} /></span>
                </button>
                {g === "notebooks" && <Link to="/new" className="side-act" aria-label="New notebook" title="New notebook"><Plus size={15} /></Link>}
              </div>
              <div id={`side-${g}`} className={`side-list ${g === "notebooks" ? "side-nbs" : "side-nav"}`} hidden={shutNow}>
                {g === "notebooks" ? notebookList : items}
              </div>
            </section>
          );
        })}
      </nav>
      <div className="side-foot">
        <MarketsNow markets={markets} />
        <AccountMenu me={me} dark={dark} onTheme={() => setTheme(dark ? "light" : "dark")} onTour={() => { setOpen(false); setTour(true); }} onGo={() => setOpen(false)} />
      </div>
    </aside>
  );

  return (
    <div className="shell">
      <header className="topbar">
        <button className="icon-btn" aria-label="Open menu" onClick={() => setOpen(true)}><Menu /></button>
        <Link to="/" className="brand" aria-label="StratLab home"><Logo size={40} /></Link>
        <span className="row" style={{ gap: 4 }}>
          <button className="icon-btn" aria-label="Search or ask anything" onClick={() => setSearch(true)}><Search /></button>
          <button className="icon-btn" aria-label="New notebook" onClick={() => nav("/new")}><Plus /></button>
        </span>
      </header>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      {sidebar}
      <main className="main"><div className="page">{children}</div></main>
      <Suspense fallback={null}>
        {tour && <Tour onClose={() => setTour(false)} />}
        {search && <SearchPalette onClose={() => setSearch(false)} />}
        {askLevel && !tour && <LevelPrompt onDone={() => undefined} />}
      </Suspense>
    </div>
  );
}


/** Trade · Invest · Money · All at the top of the menu: which space's menu shows. Every page stays reachable from
 * any of them (search, links, "All"). */
function SpaceSwitch({ space, onPick }: { space: SpaceView; onPick: (s: SpaceView) => void }) {
  const views: [SpaceView, string, string][] = [...SPACE_IDS.map((s) => [s, SPACES[s].label, SPACES[s].what] as [SpaceView, string, string]),
    ["all", "All", "Every menu group, folded"]];
  return (
    <div className="space-switch" role="radiogroup" aria-label="Space">
      {views.map(([v, label, what]) => (
        <button key={v} role="radio" aria-checked={space === v} title={what} data-space={v} onClick={() => onPick(v)}>{label}</button>
      ))}
    </div>
  );
}
