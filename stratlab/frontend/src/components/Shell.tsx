import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { Book, Compass, Layers, Library, News, Upload, Lens, Menu, Pin, Shield, Moon, Plus, Pulse, Search, Sparkle, Sun, User } from "./Icons";
import { Logo } from "./Logo";
import { inWords, marketState } from "../lib/marketHours";

// the pop-ups load when they first open, so they don't slow down the first page
const SearchPalette = lazy(() => import("./SearchPalette").then((m) => ({ default: m.SearchPalette })));
const LevelPrompt = lazy(() => import("./LevelPrompt").then((m) => ({ default: m.LevelPrompt })));
const Tour = lazy(() => import("./Tour").then((m) => ({ default: m.Tour })));

export const TOUR_SEEN = "stratlab.tour.v1";
const tourSeen = () => { try { return localStorage.getItem(TOUR_SEEN) === "1"; } catch { return true; } };

const SHORT: Record<string, string> = { IN: "India", CRYPTO: "Crypto", US: "US", UK: "UK", EU: "Europe", JP: "Japan", FX: "Forex", MCX: "MCX", CDS: "Currency F&O", CMDTY: "Cmdty" };


export function Shell({ children }: { children: ReactNode }) {
  const { notebooks, markets, theme, setTheme, me, level, focus } = useApp();
  const [open, setOpen] = useState(false);
  const [mktOpen, setMktOpen] = useState(() => { try { return localStorage.getItem("stratlab.markets.open") === "1"; } catch { return false; } });
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
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  const live = markets.filter((m) => m.status !== "soon" && m.id !== "CSV");

  const onResearch = (p: string, exact = false) => () => (exact ? loc.pathname === p : loc.pathname.startsWith(p)) ? "active" : "";
  // the investor tools, each one tap away instead of hidden behind a single "Research" link
  const investing = (
    <nav className="side-nav stack side-group" style={{ gap: 2 }} aria-label="Investing">
      <div className="eyebrow" style={{ padding: "0 8px 6px" }}>Investing</div>
      <NavLink to="/research" className={() => (/^\/research(\/(IN|US)\/.*)?$/.test(loc.pathname) ? "active" : "")}><Lens />Companies</NavLink>
      <NavLink to="/holdings"><Book />My Holdings</NavLink>
      <NavLink to="/research/investor" className={onResearch("/research/investor")}><Compass />Investor home</NavLink>
      <NavLink to="/news"><News />News</NavLink>
      <NavLink to="/research/scan" className={onResearch("/research/scan")}><Search />Stage 2 scan</NavLink>
      <NavLink to="/research/rotation" className={onResearch("/research/rotation")}><Pulse />Sector rotation</NavLink>
      <NavLink to="/research/filings" className={onResearch("/research/filings")}><Shield />Red flags</NavLink>
      <NavLink to="/research/watchlist" className={onResearch("/research/watchlist")}><Pin />Watchlist</NavLink>
    </nav>
  );
  const trading = (
    <div className="stack side-group" style={{ gap: 12 }}>
      <nav className="side-nav stack" style={{ gap: 2 }} aria-label="Trading">
        <div className="eyebrow" style={{ padding: "0 8px 6px" }}>Trading</div>
        <NavLink to={focus === "invest" ? "/notebooks" : "/"} end><Book />All notebooks</NavLink>
        <NavLink to="/paper"><Pulse />Paper trading</NavLink>
        <NavLink to="/options"><Layers />Options</NavLink>
        <NavLink to="/import"><Upload />Import a strategy</NavLink>
        <NavLink to="/library"><Library />Strategy library</NavLink>
      </nav>
      <nav className="stack" style={{ gap: 4 }} aria-label="Notebooks">
        {!(focus === "invest" && notebooks?.length === 0) && <div className="eyebrow" style={{ padding: "0 8px 6px" }}>Your notebooks</div>}
        {notebooks === null && <span className="small muted" style={{ padding: "0 12px" }}>Loading…</span>}
        {notebooks?.length === 0 && focus !== "invest" && <span className="small muted" style={{ padding: "0 12px" }}>Each idea you test becomes a notebook here.</span>}
        {notebooks?.map((n) => {
          const inst = n.instrument && "symbol" in n.instrument ? n.instrument.symbol : null;
          const count = n.summary?.experiments ?? 0;
          return (
            <NavLink key={n.id} to={`/n/${n.id}`} className={({ isActive }) => `nb-link${isActive || loc.pathname.startsWith(`/n/${n.id}/`) ? " active" : ""}`}>
              <b className="row" style={{ gap: 7 }}>
                <span className={`vdot ${n.summary?.last_verdict ?? "none"}`} title={n.summary?.last_verdict ? `Last verdict: ${n.summary.last_verdict.replace("_", " ")}` : "No experiments yet"} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", flex: 1, minWidth: 0 }}>{n.name}</span>
                {n.pinned && <span className="muted" title="Pinned" style={{ flex: "none", display: "inline-flex" }}><Pin size={14} filled /></span>}
              </b>
              <span>{[inst, `${count} experiment${count === 1 ? "" : "s"}`].filter(Boolean).join(" · ")}</span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );

  const sidebar = (
    <aside className={`sidebar${open ? " open" : ""}`} aria-label="Notebooks and navigation">
      <Link to="/" className="brand" aria-label="StratLab home"><Logo size={54} /></Link>
      {focus === "invest"
        ? <button className="btn" onClick={() => nav("/research")}><Lens size={18} />Look up a company</button>
        : <button className="btn" onClick={() => nav("/new")}><Plus size={18} />New notebook</button>}
      <button className="search-btn" onClick={() => setSearch(true)} aria-label="Ask or do anything (Ctrl+K)">
        <Sparkle size={17} /><span>Ask or do anything</span><kbd>{/Mac/.test(navigator.platform) ? "⌘K" : "Ctrl K"}</kbd>
      </button>
      {focus === "invest" ? <>{investing}{trading}</> : <>{trading}{investing}</>}
      <nav className="side-nav stack" style={{ gap: 2 }} aria-label="Account">
        <NavLink to="/account" className={() => (loc.pathname === "/account" || loc.pathname === "/plans" ? "active" : "")}><User />Account{me && <span className="badge skip" style={{ marginLeft: "auto" }}>{me.plan_info.name}</span>}</NavLink>
        {me?.is_admin && <NavLink to="/admin"><Shield />Admin</NavLink>}
      </nav>
      <div className="stack small muted" style={{ marginTop: "auto", gap: 8 }}>
        {live.length > 0 && (
        <details className="mkt-box" open={mktOpen} onToggle={(e) => { const o = (e.currentTarget as HTMLDetailsElement).open; setMktOpen(o); try { localStorage.setItem("stratlab.markets.open", o ? "1" : "0"); } catch { /* private mode */ } }}>
          <summary><span className="eyebrow">Markets now</span><span className="tiny muted">{live.filter((m) => marketState(m).open).length} of {live.length} open</span></summary>
        <div className="mkt-grid">
          {live.map((m) => {
            const st = marketState(m);
            const mins = st.change ? (st.change.getTime() - Date.now()) / 60000 : null;
            return (
              <div key={m.id} className="mkt-now" tabIndex={0} aria-label={`${m.name}: ${st.open ? "open" : st.short}`}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", flex: "none", boxSizing: "border-box",
                  background: st.open ? "var(--blue)" : "transparent", border: `1.5px solid ${st.offline ? "var(--orange)" : st.open ? "var(--blue)" : "var(--muted)"}` }} />
                {SHORT[m.id] ?? m.name}<span className={st.open ? "" : "muted"} style={{ marginLeft: "auto", fontSize: 11.5, whiteSpace: "nowrap" }}>{st.short}</span>
                <span className="mkt-tip" role="tooltip">
                  <b>{m.name}</b>
                  {st.always ? <span>Trades around the clock, every day.</span>
                    : st.offline ? <span>Market data is offline right now.</span>
                    : <>
                        <span>{st.open ? `Open now · closes in ${inWords(mins!)}` : `${st.closedFor === "holiday" ? "Closed today for an exchange holiday" : st.closedFor === "weekend" ? "Closed for the weekend" : "Closed"} · opens in ${inWords(mins!)}`}</span>
                        {st.change && <span className="muted">{st.open ? "Closes" : "Opens"} {st.change.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })} your time</span>}
                        {st.hoursLocal && <span className="muted">Hours: {st.hoursLocal}</span>}
                        {st.hoursYours && <span className="muted">{st.hoursYours}</span>}
                      </>}
                </span>
              </div>
            );
          })}
        </div>
        </details>
        )}
        <div className="row side-foot" style={{ gap: 14 }}>
          <button className="link" onClick={() => setTheme(dark ? "light" : "dark")}>{dark ? <Sun size={16} /> : <Moon size={16} />}{dark ? "Light mode" : "Night mode"}</button>
          <button className="link" onClick={() => { setOpen(false); setTour(true); }} title="A quick tour of what StratLab can do"><Compass size={16} />Tour</button>
        </div>
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

