import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { useDialogFocus } from "./kit/Dialog";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { Bell, Book, Calendar, Chevron, Close, Compass, Layers, Library, Lens, Menu, News, Pin, Plus, Pulse, Receipt, Search, Sparkle, Upload, Wallet } from "./Icons";
import { Logo } from "./Logo";
import { AccountMenu, MarketsNow } from "./SideMenus";
import { NAV, groupPath, locate, locateGroup, type NavPage } from "../lib/nav";
import { SPACE_IDS, SPACES, homeOf, spaceOf, type SpaceView } from "../lib/spaces";
import { usePersisted } from "../lib/persist";
import { usePins } from "../lib/pins";
import { PageBreadcrumb } from "./PageBreadcrumb";
import { Onboarding, openTour } from "./Onboarding";

// the pop-ups load when they first open, so they don't slow down the first page
const SearchPalette = lazy(() => import("./SearchPalette").then((m) => ({ default: m.SearchPalette })));

/** The menu lists this many notebooks (pinned first, then the latest) under Notebooks; the rest are one tap away on the notebooks page. */
const SIDE_NOTEBOOKS = 6;

/** Icons a menu entry can name (NavPage.icon). */
const ICONS: Record<string, (p: { size?: number }) => ReactNode> = { book: Book, receipt: Receipt, bell: Bell, lens: Lens, news: News, pin: Pin, pulse: Pulse, layers: Layers, library: Library, upload: Upload, search: Search, compass: Compass, wallet: Wallet, calendar: Calendar };
/** Which menu groups are open, remembered on this device. */
const OPEN_KEY = "stratlab.side.groups";
const NO_GROUPS: Record<string, boolean> = {};
/** The pages Mine's own menu links to: opening one keeps Mine's menu showing. */
const MINE_LINKS = ["/news"];
/** Pages that belong to the person, not to a space (Account, Settings, the assistant, the app, invites): they open Mine's menu. */
const MINE_PAGES = ["/account", "/settings", "/assistant", "/app", "/invite"];

export function Shell({ children }: { children: ReactNode }) {
  const { notebooks, markets, me, focus, space, setSpace } = useApp();
  const [open, setOpen] = useState(false);
  const [openGroups, setOpenGroups] = usePersisted<Record<string, boolean>>(OPEN_KEY, NO_GROUPS);
  const pins = usePins();
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
  const loc = useLocation();
  const nav = useNavigate();
  useEffect(() => setOpen(false), [loc.pathname]);
  // on a phone (or zoomed in) the menu is a drawer: a modal while it's open. Focus moves in and stays in, Esc closes it
  // (a pop-up inside it closes first, on its own), and focus goes back to the menu button.
  const aside = useRef<HTMLElement>(null);
  useDialogFocus(aside, open, { onEscape: () => setOpen(false), initial: () => aside.current?.querySelector<HTMLElement>(".side-close") });
  const path = loc.pathname;
  const at = locate(path);
  const onGroup = locateGroup(path);
  // a link into another space shows that space's menu, so where you are is always in it. Mine keeps its own menu on the
  // pages it links to (pinned pages, Briefs, Connected accounts): that is what it is for.
  const here = spaceOf(path);
  const keepsMine = !!at && (pins.has(at.page.to) || MINE_LINKS.includes(at.page.to));
  useEffect(() => {
    if (MINE_PAGES.includes(path)) { if (space !== "mine") setSpace("mine", false); return; }
    if (!here) return;
    if (space === "mine" ? !keepsMine : here !== space) setSpace(here, false);
  }, [here, path]);   // eslint-disable-line react-hooks/exhaustive-deps
  // pinned first, then the latest; the one you have open always stays in the list
  const openId = path.match(/^\/n\/([^/]+)/)?.[1];
  const sideNotebooks = notebooks && [...notebooks].sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
    .filter((n, i) => i < SIDE_NOTEBOOKS || n.id === openId);

  const item = (to: string, icon: ReactNode, label: string, active?: boolean, title?: string) => (
    <NavLink key={to} to={to} title={title} {...(active === undefined ? {} : { className: () => (active ? "active" : ""), "aria-current": active ? "page" as const : false })}>{icon}{label}</NavLink>
  );
  const pageLink = (p: NavPage) => {
    const Icon = ICONS[p.icon] ?? Compass;
    return item(p.to, <Icon />, p.label, at?.page.to === p.to, p.line);
  };
  // the group holding the page showing is open and stays open; the others are as the person left them
  const activeGroup = space !== "mine" ? (onGroup?.space === space ? onGroup.group.id : at?.space === space ? at.group.id : null) : null;
  const isOpen = (g: string) => openGroups[g] ?? false;
  const toggle = (g: string) => setOpenGroups((cur) => ({ ...cur, [g]: !(cur[g] ?? false) }));
  useEffect(() => { if (activeGroup && !isOpen(activeGroup)) setOpenGroups((cur) => ({ ...cur, [activeGroup]: true })); }, [activeGroup]);   // eslint-disable-line react-hooks/exhaustive-deps
  const allNotebooks = "/notebooks";
  const notebookList = (
    <div className="side-list side-nbs">
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
    </div>
  );
  // the notebooks list shows under Notebooks while you are in a notebook (or the list), so it never makes the menu long
  const inNotebooks = path === allNotebooks || path.startsWith("/n/") || path === "/new";
  const spaceGroups = space === "mine" ? null : NAV[space].groups.map((g) => {
    const shutNow = !isOpen(g.id);
    const here = onGroup?.space === space && onGroup.group.id === g.id;
    return (
      <section key={g.id} className="side-group" data-group={g.id}>
        <div className="side-head">
          <button className="side-toggle" aria-expanded={!shutNow} aria-controls={`side-${g.id}`} aria-label="Open or close this group" onClick={() => toggle(g.id)}>
            <span className="side-chev" aria-hidden="true"><Chevron size={12} /></span>
          </button>
          <Link to={groupPath(space, g)} className={`side-title${here ? " active" : ""}`} aria-current={here ? "page" : undefined} title={`${g.label}: everything in this group`}>{g.label}</Link>
        </div>
        <div id={`side-${g.id}`} className="side-list side-nav" hidden={shutNow}>
          {g.pages.map((p) => (
            <div key={p.to} className="side-entry">
              {pageLink(p)}
              {p.to === "/notebooks" && inNotebooks && notebookList}
            </div>
          ))}
        </div>
      </section>
    );
  });
  const minePart = (
    <>
      <section className="side-group" data-group="pinned">
        <div className="side-head"><span className="side-title plain">Pinned</span></div>
        <div className="side-list side-nav" id="side-pinned">
          {pins.pins.map((l) => pageLink(l.page))}
          {!pins.pins.length && <span className="small muted side-note-wrap">Pin a page from the menu in its breadcrumb at the top of the page.</span>}
        </div>
      </section>
      <section className="side-group" data-group="mine-more">
        <div className="side-list side-nav">
          {item("/news", <News />, "Briefs", at?.page.to === "/news", "Today's brief, past issues and the subscribe switches")}
          {item("/settings#accounts", <Wallet />, "Connected accounts", path === "/settings" && loc.hash === "#accounts", "Your holdings, funds and tradebooks: the files StratLab reads")}
          {item("/assistant", <Sparkle />, "Connect an AI assistant", path === "/assistant", "Keys that let Claude or ChatGPT use your StratLab")}
        </div>
      </section>
    </>
  );
  const goSpace = (s: SpaceView) => {
    setOpen(false);
    if (s !== space) setSpace(s);
    nav(homeOf(s, focus));
  };
  const homeLabel = space === "mine" ? "My space" : `${SPACES[space].label} home`;
  const sidebar = (
    <aside ref={aside} id="side-menu" className={`sidebar${open ? " open" : ""}`} aria-label={open ? "Menu" : "Navigation"}
      {...(open ? { role: "dialog", "aria-modal": true } : {})}>
      <div className="side-top">
        <div className="side-brand">
          <Link to="/" className="brand" aria-label="StratLab home"><Logo size={40} /></Link>
          <button className="side-close" aria-label="Close menu" onClick={() => setOpen(false)}><Close size={18} /></button>
        </div>
        <SpaceSwitch space={space} onPick={goSpace} />
        {space === "invest" || (space === "mine" && focus === "invest")
          ? <button className="side-new" onClick={() => nav("/research")}><Lens size={16} />Look up a company</button>
          : space === "money" || (space === "mine" && focus === "money")
          ? <button className="side-new" onClick={() => nav("/holdings")}><Book size={16} />Add your holdings</button>
          : <button className="side-new" onClick={() => nav("/new")}><Plus size={16} />New notebook</button>}
        <button className="search-btn" onClick={() => setSearch(true)} aria-keyshortcuts={/Mac/.test(navigator.platform) ? "Meta+K" : "Control+K"}>
          <Sparkle size={16} /><span>Ask or do anything</span><kbd>{/Mac/.test(navigator.platform) ? "⌘K" : "Ctrl K"}</kbd>
        </button>
      </div>
      <nav className="side-groups" aria-label="Main">
        <div className="side-list">
          <NavLink to={homeOf(space)} end><Compass size={16} />{homeLabel}</NavLink>
        </div>
        {spaceGroups ?? minePart}
      </nav>
      <div className="side-foot">
        <MarketsNow markets={markets} />
        <AccountMenu me={me} onTour={() => { setOpen(false); openTour(); }} onGo={() => setOpen(false)} />
      </div>
    </aside>
  );

  return (
    <div className="shell">
      <a className="skip-link sr-only" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to content</a>
      <header className="topbar">
        <button className="icon-btn" aria-label="Open menu" aria-expanded={open} aria-controls="side-menu" onClick={() => setOpen(true)}><Menu /></button>
        <Link to="/" className="brand" aria-label="StratLab home"><Logo size={40} /></Link>
        <span className="row tight">
          <button className="icon-btn" aria-label="Search or ask anything" onClick={() => setSearch(true)}><Search /></button>
          <button className="icon-btn" aria-label="New notebook" onClick={() => nav("/new")}><Plus /></button>
        </span>
      </header>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      {sidebar}
      <main className="main" id="main" tabIndex={-1}><div className="page"><PageBreadcrumb />{children}</div></main>
      <Suspense fallback={null}>
        {search && <SearchPalette onClose={() => setSearch(false)} />}
      </Suspense>
      <Onboarding />
    </div>
  );
}


/** Mine · Trade · Invest · Money at the top of the menu: which space's menu shows. A click goes to that space's home (the
 * active one too). Every page stays reachable from any of them (search, links, the breadcrumb). */
function SpaceSwitch({ space, onPick }: { space: SpaceView; onPick: (s: SpaceView) => void }) {
  const views: [SpaceView, string, string][] = [["mine", "Mine", "Your own space: your money, the markets and what is coming up"],
    ...SPACE_IDS.map((s) => [s, SPACES[s].label, SPACES[s].what] as [SpaceView, string, string])];
  return (
    <div className="space-switch" role="radiogroup" aria-label="Space">
      {views.map(([v, label, what]) => (
        <button key={v} role="radio" aria-checked={space === v} title={what} data-space={v} onClick={() => onPick(v)}>{label}</button>
      ))}
    </div>
  );
}
