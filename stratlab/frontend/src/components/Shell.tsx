import { Fragment, lazy, Suspense, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useDialogFocus } from "./kit/Dialog";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { Bell, Book, Calendar, Chevron, Close, Compass, Gear, Layers, Library, Lens, Markets, Menu, News, Pin, Plus, Pulse, Receipt, Search, Sparkle, Upload, Wallet } from "./Icons";
import { Logo } from "./Logo";
import { VERDICT_FACT } from "./ui";
import { AccountMenu, MarketsNow } from "./SideMenus";
import { useScrollMemory } from "../lib/scrollMemory";
import { NAV, locate, locateGroup, startOf, type NavGroup, type NavPage } from "../lib/nav";
import { MINE_HOME, MINE_NAME, SPACE_IDS, SPACES, homeOf, menuView, spaceOf, type SpaceView } from "../lib/spaces";
import { titleFor } from "../lib/title";
import { usePersisted } from "../lib/persist";
import { usePins } from "../lib/pins";
import { PageBreadcrumb } from "./PageBreadcrumb";
import { HubTabs } from "./HubTabs";
import { Onboarding, openTour } from "./Onboarding";
import { MarketsLauncher, openMarkets } from "./watch/Launcher";
import { gateFor, gatePlan } from "../lib/gates";
import { PLAN_NAME } from "../lib/plans";
import { watchSize } from "../lib/resize";
import { importWithRetry } from "../lib/lazyRetry";
import { scrollBehavior } from "../lib/motion";

// the pop-ups load when they first open, so they don't slow down the first page
const SearchPalette = lazy(() => importWithRetry(() => import("./SearchPalette")).then((m) => ({ default: m.SearchPalette })));

/** The menu lists this many notebooks (pinned first, then the latest) under Notebooks; the rest are one tap away on the notebooks page. */
const SIDE_NOTEBOOKS = 6;

/** Icons a menu entry can name (NavPage.icon). */
const ICONS: Record<string, (p: { size?: number }) => ReactNode> = { book: Book, receipt: Receipt, bell: Bell, lens: Lens, news: News, pin: Pin, pulse: Pulse, layers: Layers, library: Library, upload: Upload, search: Search, compass: Compass, wallet: Wallet, calendar: Calendar };
/** Which menu sections the person opened or folded (IA-2, item 36), remembered on this device per person ("stratlab.side.open.<id>"),
 * so two people on one browser keep their own menus. A section with no entry follows the rule: the one you are in is open. */
const OPEN_KEY = "stratlab.side.open";
const NO_CHOICE: Record<string, boolean> = {};
/** The pages Mine's own menu links to: opening one keeps Mine's menu showing. */
export const MINE_LINKS = ["/news", "/alerts", "/research/watchlist", "/calendar"];
/** Menu entries Mine's own menu has too (IA-1): moving between their tabs keeps Mine's menu showing. */
export const MINE_GROUPS = ["watch", "calendar"];
/** Pages that belong to the person, not to a space (Account, Settings, the assistant, the app, invites): they open Mine's menu. */
const MINE_PAGES = ["/account", "/settings", "/assistant", "/app", "/invite"];

export function Shell({ children }: { children: ReactNode }) {
  useScrollMemory();
  const { notebooks, markets, me, focus, space: saved, setSpace } = useApp();
  const [open, setOpen] = useState(false);
  const pins = usePins();
  const [opened, setOpened] = usePersisted<Record<string, boolean>>(`${OPEN_KEY}.${me?.id ?? "guest"}`, NO_CHOICE);
  // on a laptop the menu can fold away for wide tables, remembered on this device (R1-082); a phone has its drawer
  const [slim, setSlim] = usePersisted<boolean>("stratlab.side.slim", false);
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
  // the menu scrolls inside its own box: the edge with more behind it fades out, so a half-hidden row reads as "more below"
  const sideScroll = useRef<HTMLElement>(null);
  const fade = useScrollFade(sideScroll);
  // the tour opens the phone's menu to point at what is in it (DI-023); held open by the tour, the menu is not a modal of its
  // own, so the tour's note keeps the keyboard and Esc
  const [tourMenu, setTourMenu] = useState(false);
  useEffect(() => {
    const hold = (e: Event) => { const on = !!(e as CustomEvent<{ open: boolean }>).detail?.open; setTourMenu(on); setOpen(on); };
    window.addEventListener("stratlab:tour-menu", hold);
    return () => window.removeEventListener("stratlab:tour-menu", hold);
  }, []);
  useDialogFocus(aside, open && !tourMenu, { onEscape: () => setOpen(false), initial: () => aside.current?.querySelector<HTMLElement>(".side-close") });
  const path = loc.pathname;
  const at = locate(path);
  const onGroup = locateGroup(path);
  // a link into another space shows that space's menu, so where you are is always in it. Mine keeps its own menu on the
  // pages it links to (pinned pages, Briefs, Connected accounts): that is what it is for.
  const keepsMine = !!at && (pins.has(at.page.to) || MINE_LINKS.includes(at.page.to) || MINE_GROUPS.includes(at.group.id));
  // the menu comes from the address itself (lib/spaces menuView), so it can't lag behind a saved choice that loads later
  const space = menuView(path, saved, keepsMine);
  // remember it on this device, so the front door opens the space last used (only real spaces and Mine's own pages).
  // Runs when the page changes, not when the saved choice does: picking a space in the switcher saves it first and
  // navigates a moment later, and the page still showing must not save its own space over that choice.
  useEffect(() => {
    if (space !== saved && (spaceOf(path) || MINE_PAGES.includes(path) || path === MINE_HOME)) setSpace(space, false);
  }, [space, path]);   // eslint-disable-line react-hooks/exhaustive-deps
  useLayoutEffect(() => { document.title = titleFor(path); }, [path]);    // each page's own title; a page may sharpen it
  // pinned first, then the latest; the one you have open always stays in the list
  const openId = path.match(/^\/n\/([^/]+)/)?.[1];
  const sideNotebooks = notebooks && [...notebooks].sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned))
    .filter((n, i) => i < SIDE_NOTEBOOKS || n.id === openId);

  // a link with its own rule for "you are here" is a plain Link marked by that rule alone: NavLink also marked every link whose
  // address starts the current one, so /research/watchlist had Look up a company and Watchlist both current, and Settings'
  // Notifications tab had Connected accounts (DI-016)
  const item = (to: string, icon: ReactNode, label: ReactNode, active?: boolean, title?: string) => (active === undefined
    ? <NavLink key={to} to={to} title={title} end>{icon}{label}</NavLink>
    : <Link key={to} to={to} title={title} className={active ? "active" : undefined} aria-current={active ? "page" : undefined}>{icon}{label}</Link>);
  // `bare`: a page listed under its section's heading, without an icon (the heading has it), so the list reads as one section's pages
  const pageLink = (p: NavPage, name: string = p.label, bare = false) => {
    const Icon = ICONS[p.icon] ?? Compass;
    // a page that is a paid feature this plan lacks carries its plan, with a lock (lib/gates.ts)
    const gate = gateFor(p.to);
    // the lock is for a page that is locked as a whole (Trend scan). A page that is free in the main and has a paid part
    // (Net worth: 5 entries free, the history on Basic) has no lock: the Plans cards say "5 free", and the page says which
    // part is paid. The part is in the link's title.
    const off = !!gate && me?.plan_info?.features?.[gate.feature] === false;
    const locked = off && gate!.whole;
    // drawn by CSS from data-plan, so the link's name stays the page's own; the plan is in its title
    const label = locked ? <>{name}<span className="side-lock" data-plan={PLAN_NAME[gatePlan(gate!)]} aria-hidden="true" /></> : name;
    // inside a notebook the notebook under Notebooks is the one selected entry: Notebooks itself isn't highlighted too
    // (owner, 26 Oct: both had the selected background)
    const here = at?.page.to === p.to && !(p.to === "/notebooks" && path.startsWith("/n/"));
    return item(p.to, bare ? null : <Icon />, label, here, off ? `${p.line} (${gate!.whole ? "" : "part of it "}on the ${PLAN_NAME[gatePlan(gate!)]} plan)` : p.line);
  };
  const allNotebooks = "/notebooks";
  const notebookList = (
    <div className="side-list side-nbs">
      {notebooks === null && <span className="small muted side-note">Loading…</span>}
      {notebooks?.length === 0 && <span className="small muted side-note">None yet.</span>}
      {sideNotebooks?.map((n) => {
        const inst = n.instrument && "symbol" in n.instrument ? n.instrument.symbol : null;
        const count = n.summary?.experiments ?? 0;
        // the dot's colour in the verdict's own words ("Too few trades"), not its code ("not enough", DA-032)
        const verdict = n.summary?.last_verdict ? `last run: ${VERDICT_FACT[n.summary.last_verdict] ?? n.summary.last_verdict}` : "no experiments yet";
        return (
          <NavLink key={n.id} to={`/n/${n.id}`} title={[n.name, inst, `${count} experiment${count === 1 ? "" : "s"}`, verdict].filter(Boolean).join(" · ")}
            className={({ isActive }) => `nb-link${isActive || path.startsWith(`/n/${n.id}/`) ? " active" : ""}`}>
            <span className="nb-dot" title={`The dot is the ${verdict}`}><span className={`vdot ${n.summary?.last_verdict ?? "none"}`} /></span>
            {/* the dot says what it is on hover (its title) and to a screen reader here; the caption under the list that said it
                for every dot was clutter in the menu (owner, 26 Oct) */}
            <span className="nb-text">{n.name}<span className="sr-only">, {verdict}</span></span>
            {n.pinned && <span className="nb-pin" title="Pinned"><Pin size={13} filled /></span>}
          </NavLink>
        );
      })}
      {!!notebooks?.length && <Link to={allNotebooks} className="nb-more">{notebooks.length > SIDE_NOTEBOOKS ? `All ${notebooks.length} notebooks` : "All notebooks"}</Link>}
    </div>
  );
  // the notebooks list shows under Notebooks while you are in a notebook (or the list), so it never makes the menu long
  const inNotebooks = path === allNotebooks || path.startsWith("/n/") || path === "/new";
  // IA-2 (item 36, owner 30 Oct: "you have squeezed the menu bar too much"): the 14 headings stay, and under each heading are its pages,
  // the same pages, names, plan locks and order as its tabs, so nothing is reachable only through a tab or the breadcrumb's menu. The
  // section you are in is open; the others fold, each with its own open/close button, and what the person opened or folded is kept.
  // A heading with one page (Themes, Trade journal) is that page, with no list under it.
  const current = space === "mine" ? null
    : onGroup?.space === space ? onGroup.group.id
    : at && NAV[space].groups.some((g) => g.id === at.group.id) ? at.group.id : null;
  const isOpen = (g: NavGroup) => opened[g.id] ?? g.id === current;
  const toggle = (g: NavGroup) => { const now = isOpen(g); setOpened((cur) => ({ ...cur, [g.id]: !now })); };
  // coming back into a section opens it again, even if it was folded the last time the person was in it
  useEffect(() => {
    if (current && opened[current] === false) setOpened((cur) => { const { [current]: _, ...rest } = cur; return rest; });
  }, [current, me?.id]);   // eslint-disable-line react-hooks/exhaustive-deps
  // The heading opens its section's first page. It is the selected item only when its own page is showing (a one-page section, or
  // the section's page of cards); when one of its pages is, that page is the selected one and the heading is only bold (owner, 26
  // Oct: never two selected at once). Inside a notebook the notebook is selected, not Strategies or Notebooks too.
  const entryLink = (g: NavGroup, sp: Exclude<SpaceView, "mine">) => {
    const Icon = ICONS[g.icon] ?? Compass;
    const inIt = g.id === current && !(g.id === "strategies" && path.startsWith("/n/"));
    const here = inIt && (g.pages.length === 1 || onGroup?.group.id === g.id);
    // an entry is locked only when every tab of it is a paid page this plan lacks (none is today): a locked tab carries its lock on the tab
    const locks = g.pages.map((p) => { const gate = gateFor(p.to); return gate && gate.whole && me?.plan_info?.features?.[gate.feature] === false ? gate : null; });
    const locked = locks.every(Boolean) ? locks[0] : null;
    const label = locked ? <>{g.label}<span className="side-lock" data-plan={PLAN_NAME[gatePlan(locked)]} aria-hidden="true" /></> : g.label;
    const tabs = g.pages.length > 1 ? `${g.label}: ${g.pages.map((p) => p.label).join(", ")}` : g.pages[0].line;
    const to = startOf(g, sp);
    return <Link key={to} to={to} title={locked ? `${tabs} (on the ${PLAN_NAME[gatePlan(locked)]} plan)` : tabs}
      className={here ? "active" : inIt ? "in-section" : undefined} aria-current={here ? "page" : undefined}><Icon />{label}</Link>;
  };
  const spaceGroups = space === "mine" ? null : (
    <div className="side-list side-nav side-entries">
      {NAV[space].groups.map((g) => {
        const many = g.pages.length > 1;
        const open = many && isOpen(g);
        return (
          <div key={g.id} className="side-entry" data-group={g.id} data-open={many ? String(open) : undefined}>
            <div className="side-head">
              {entryLink(g, space)}
              {many && (
                // named by its words (hidden), not an aria-label, so a page's own "Stock" field is the only thing labelled "Stock"
                <button type="button" className="side-toggle" aria-expanded={open} aria-controls={`side-sub-${g.id}`}
                  title={open ? `Fold ${g.label}` : `Show the pages of ${g.label}`} onClick={() => toggle(g)}>
                  <span className="side-chev" aria-hidden="true"><Chevron size={12} /></span><span className="sr-only">{g.label} pages</span>
                </button>
              )}
            </div>
            {many && (
              <div id={`side-sub-${g.id}`} className="side-list side-sub" hidden={!open}>
                {g.pages.map((p) => (
                  <Fragment key={p.to}>
                    {pageLink(p, p.label, true)}
                    {p.to === allNotebooks && inNotebooks && notebookList}
                  </Fragment>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
  const minePart = (
    <>
      <section className="side-group" data-group="pinned">
        <div className="side-head"><span className="side-title plain">Pinned</span></div>
        <div className="side-list side-nav" id="side-pinned">
          {/* a tab renamed by IA-1 is pinned with its entry's name ("Find stocks: Figures"): "Figures" alone says nothing in this menu */}
          {pins.pins.map((l) => pageLink(l.page, l.page.was ? `${l.group.label}: ${l.page.label}` : l.page.label))}
          {!pins.pins.length && <span className="small muted side-note-wrap" title="Open the menu in a page's breadcrumb to pin it here">Nothing pinned yet. Pin a page from its breadcrumb menu.</span>}
        </div>
      </section>
      {/* the everyday things, each one tap from My space; the AI assistant only for a plan that has it, not as a locked
          upsell on Free and Basic (DI-017, DI-018) */}
      <section className="side-group" data-group="mine-more">
        <div className="side-list side-nav">
          {item("/news", <News />, "Today's brief", at?.page.to === "/news", "Today's brief, past issues and the subscribe switches")}
          {item("/research/watchlist", <Pin />, "Watchlist", at?.group.id === "watch", "Watchlist: the companies you follow, and Alerts: a message when a stock or the market does what you asked about")}
          {item("/calendar", <Calendar />, "Calendar", at?.group.id === "calendar", "Calendar: results, corporate actions, IPOs, market events and your own money dates")}
          {item("/settings#accounts", <Wallet />, "Connected accounts", path === "/settings" && loc.hash === "#accounts", "Your holdings, funds and tradebooks: the files StratLab reads")}
          {item("/settings", <Gear />, "Settings", path === "/settings" && loc.hash !== "#accounts", "Notifications, what you see first, the theme and the connection check")}
          {me?.plan_info?.features?.assistant !== false && item("/assistant", <Sparkle />, "Connect an AI assistant", path === "/assistant", "Keys that let Claude or ChatGPT use your StratLab")}
        </div>
      </section>
    </>
  );
  const goSpace = (s: SpaceView) => {
    setOpen(false);
    if (s !== space) setSpace(s);
    nav(homeOf(s, focus));
  };
  const homeLabel = space === "mine" ? MINE_NAME : `${SPACES[space].label} home`;
  // the space's main action, in the menu and on a phone's top bar alike (DI-021: the phone's "+" was always New notebook)
  const main = mainAction(space, focus, !!me?.has_holdings);
  const sidebar = (
    <aside ref={aside} id="side-menu" className={`sidebar${open ? " open" : ""}`} aria-label={open ? "Menu" : "Navigation"}
      {...(open ? { role: "dialog", "aria-modal": true } : {})}>
      <div className="side-top">
        <div className="side-brand">
          <Link to="/" className="brand" aria-label="StratLab home"><Logo size={40} /></Link>
          <button className="side-close" aria-label="Close menu" onClick={() => setOpen(false)}><Close size={18} /></button>
          <button className="side-hide" aria-label="Hide the menu" title="Hide the menu (more room for the page)" onClick={() => setSlim(true)}><Chevron size={14} /></button>
        </div>
        <SpaceSwitch space={space} onPick={goSpace} />
        {/* the space's main button: never a link to the page you are on */}
        {/* (VR1-102: on that page the button's place is kept, so the menu doesn't jump 42px against the pages around it) */}
        {path !== main.to ? <button className="side-new" onClick={() => nav(main.to)}>{main.icon}{main.label}</button> : <span className="side-new-gap" aria-hidden="true" />}
        <button className="search-btn" onClick={() => setSearch(true)} aria-keyshortcuts={/Mac/.test(navigator.platform) ? "Meta+K" : "Control+K"}>
          <Sparkle size={16} /><span>Ask or do anything</span>{/* no keyboard shortcut on a touch screen (R50-016) */}
          {!window.matchMedia?.("(pointer: coarse)").matches && <kbd>{/Mac/.test(navigator.platform) ? "⌘K" : "Ctrl K"}</kbd>}
        </button>
      </div>
      <nav ref={sideScroll} className="side-groups" aria-label="Main" data-fade={fade}>
        <div className="side-list">
          <NavLink to={homeOf(space)} end><Compass size={16} />{homeLabel}</NavLink>
        </div>
        {spaceGroups ?? minePart}
      </nav>
      {/* the menu's faded bottom edge says there is more; this says it in words and scrolls to it (R5O-038). The mouse
          wheel and the keyboard reach the same items, so it is left out of the Tab order and of screen readers. */}
      {(fade === "bottom" || fade === "both") && (
        <button type="button" className="side-more" tabIndex={-1} aria-hidden="true"
          onClick={() => sideScroll.current?.scrollBy({ top: Math.round((sideScroll.current?.clientHeight ?? 300) * 0.6), behavior: scrollBehavior() })}>
          More below <Chevron size={12} />
        </button>
      )}
      <div className="side-foot">
        <MarketsNow markets={markets} />
        <AccountMenu me={me} onTour={() => { setOpen(false); openTour(); }} onGo={() => setOpen(false)} />
      </div>
    </aside>
  );

  return (
    <div className={`shell${slim ? " slim" : ""}`}>
      {/* skip links: past the 30-odd menu stops straight to the page, to its own sections when it lists them, or to the
          menu (R5O-030) */}
      <a className="skip-link sr-only" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to content</a>
      <a className="skip-link sr-only" href="#main" onClick={(e) => {
        e.preventDefault();
        const first = document.querySelector<HTMLElement>("#main .k-pagenav a");
        const to = first ?? document.querySelector<HTMLElement>("#main h1") ?? document.getElementById("main");
        if (to && !first && !to.hasAttribute("tabindex")) to.setAttribute("tabindex", "-1");
        to?.focus();
      }}>Skip to the page's sections</a>
      <a className="skip-link sr-only" href="#side-menu" onClick={(e) => { e.preventDefault(); sideScroll.current?.querySelector<HTMLElement>("a, button")?.focus(); }}>Skip to the menu</a>
      {slim && <button className="side-show" aria-label="Show the menu" title="Show the menu" onClick={() => setSlim(false)}><Menu /></button>}
      <header className="topbar">
        <button className="icon-btn" aria-label="Open menu" aria-expanded={open} aria-controls="side-menu" onClick={() => setOpen(true)}><Menu /></button>
        <Link to="/" className="brand" aria-label="StratLab home"><Logo size={40} /></Link>
        <span className="row tight">
          <button className="icon-btn" aria-label="Search or ask anything" onClick={() => setSearch(true)}><Search /></button>
          <button className="icon-btn" aria-label="Markets" onClick={() => openMarkets({ open: "toggle" })}><Markets /></button>
          <button className="icon-btn" aria-label={main.label} title={main.label} onClick={() => nav(main.to)}>{main.to === "/new" ? <Plus /> : main.icon}</button>
        </span>
      </header>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      {sidebar}
      <main className="main" id="main" tabIndex={-1}><div className="page"><div className="crumb-row"><PageBreadcrumb mine={space === "mine"} space={space} />{at && <HubTabs at={at} path={path} />}</div>{children}</div></main>
      <Suspense fallback={null}>
        {search && <SearchPalette onClose={() => setSearch(false)} />}
      </Suspense>
      <Onboarding main={main.label} />
      {/* Market Watch: drawn once here, so it stays open and keeps its place from page to page (MW-1) */}
      <MarketsLauncher mode="app" userId={me?.id} />
    </div>
  );
}


/** Each space's main button: what the space is for, in one action. My space's follows what the person came for. */
export function mainAction(space: SpaceView, focus: string | null | undefined, hasHoldings = false): { to: string; icon: ReactNode; label: string } {
  return space === "invest" || (space === "mine" && focus === "invest") ? { to: "/research", icon: <Lens size={16} />, label: "Look up a company" }
    // the next real step: add them when there are none, update them when there are (LIVE1C-055: "Add your holdings" beside three holdings)
    : space === "money" || (space === "mine" && focus === "money") ? { to: "/holdings", icon: <Book size={16} />, label: hasHoldings ? "Update holdings" : "Add your holdings" }
    : { to: "/new", icon: <Plus size={16} />, label: "New notebook" };
}

/** Which edges of a scrolling box have more behind them ("top", "bottom", "both" or "none"): kept as the box scrolls, resizes
 * or its content changes (a group opens). The CSS fades those edges. */
function useScrollFade(ref: { current: HTMLElement | null }): "top" | "bottom" | "both" | "none" {
  const [fade, setFade] = useState<"top" | "bottom" | "both" | "none">("none");
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const look = () => {
      const above = el.scrollTop > 2, below = el.scrollHeight - el.clientHeight - el.scrollTop > 2;
      setFade(above && below ? "both" : above ? "top" : below ? "bottom" : "none");
    };
    look();
    el.addEventListener("scroll", look, { passive: true });
    const stopSize = watchSize(el, look);           // a frame later: no "ResizeObserver loop" page error (R7T-014)
    const mo = new MutationObserver(look);
    mo.observe(el, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
    return () => { el.removeEventListener("scroll", look); stopSize(); mo.disconnect(); };
  }, [ref]);
  return fade;
}

/** Mine · Trade · Invest · Money at the top of the menu: which space's menu shows. A click goes to that space's home (the
 * active one too), so these are buttons (the current one pressed), not a radio group: a radio group moves with the arrow
 * keys, and an arrow key must not open a page. Every page stays reachable from any of them (search, links, the breadcrumb). */
function SpaceSwitch({ space, onPick }: { space: SpaceView; onPick: (s: SpaceView) => void }) {
  const views: [SpaceView, string, string][] = [["mine", MINE_NAME, "Your own space: your money, the markets and what is coming up"],
    ...SPACE_IDS.map((s) => [s, SPACES[s].label, SPACES[s].what] as [SpaceView, string, string])];
  return (
    <div className="space-switch" role="group" aria-label="Space">
      {views.map(([v, label, what]) => (
        <button key={v} type="button" aria-pressed={space === v} title={what} data-space={v} onClick={() => onPick(v)}>{label}</button>
      ))}
    </div>
  );
}
