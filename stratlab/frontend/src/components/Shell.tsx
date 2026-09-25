import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { Book, Compass, Layers, Library, Upload, Lens, Menu, Pin, Shield, Moon, Plus, Pulse, Search, Star, Sun, User } from "./Icons";
import { SearchPalette } from "./SearchPalette";
import { LevelPrompt } from "./LevelPrompt";
import { Tour, tourSeen } from "./Tour";
import { Logo } from "./Logo";
import { inWords, marketState } from "../lib/marketHours";

const SHORT: Record<string, string> = { IN: "India", CRYPTO: "Crypto", US: "US", UK: "UK", EU: "Europe", JP: "Japan", FX: "Forex" };


export function Shell({ children }: { children: ReactNode }) {
  const { notebooks, markets, theme, setTheme, me, level } = useApp();
  const [open, setOpen] = useState(false);
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
  const askLevel = !!me && !level;
  useEffect(() => { if (me && level && !tourSeen()) setTour(true); }, [me, level]);
  const loc = useLocation();
  const nav = useNavigate();
  useEffect(() => setOpen(false), [loc.pathname]);
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  const live = markets.filter((m) => m.status !== "soon" && m.id !== "CSV");

  const sidebar = (
    <aside className={`sidebar${open ? " open" : ""}`} aria-label="Notebooks and navigation">
      <Link to="/" className="brand" aria-label="StratLab home"><Logo size={54} /></Link>
      <button className="btn" onClick={() => nav("/new")}><Plus size={18} />New notebook</button>
      <button className="search-btn" onClick={() => setSearch(true)} aria-label="Search or ask anything (Ctrl+K)">
        <Search size={17} /><span>Search or ask</span><kbd>{/Mac/.test(navigator.platform) ? "⌘K" : "Ctrl K"}</kbd>
      </button>
      <nav className="stack" style={{ gap: 4 }} aria-label="Notebooks">
        <div className="eyebrow" style={{ padding: "0 8px 6px" }}>Notebooks</div>
        {notebooks === null && <span className="small muted" style={{ padding: "0 12px" }}>Loading…</span>}
        {notebooks?.length === 0 && <span className="small muted" style={{ padding: "0 12px" }}>Your notebooks will show up here.</span>}
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
      <nav className="side-nav stack" style={{ gap: 2 }} aria-label="Main">
        <NavLink to="/research" className={() => (loc.pathname.startsWith("/research") ? "active" : "")}><Lens />Research</NavLink>
        <NavLink to="/library"><Library />Strategy library</NavLink>
        <NavLink to="/import"><Upload />Import a strategy</NavLink>
        <NavLink to="/options"><Layers />Options</NavLink>
        <NavLink to="/paper"><Pulse />Paper trading</NavLink>
        <NavLink to="/" end><Book />All notebooks</NavLink>
        <NavLink to="/plans"><Star />Plans</NavLink>
        <NavLink to="/account"><User />Account{me && <span className="badge skip" style={{ marginLeft: "auto" }}>{me.plan_info.name}</span>}</NavLink>
        {me?.is_admin && <NavLink to="/admin"><Shield />Admin</NavLink>}
      </nav>
      <div className="stack small muted" style={{ marginTop: "auto", gap: 8 }}>
        {live.length > 0 && <div className="eyebrow">Markets now</div>}
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
                        <span>{st.open ? `Open now · closes in ${inWords(mins!)}` : `Closed · opens in ${inWords(mins!)}`}</span>
                        {st.change && <span className="muted">{st.open ? "Closes" : "Opens"} {st.change.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })} your time</span>}
                        {st.hoursLocal && <span className="muted">Hours: {st.hoursLocal}</span>}
                        {st.hoursYours && <span className="muted">{st.hoursYours}</span>}
                        <span className="muted" style={{ fontSize: 11 }}>Exchange holidays aren't shown.</span>
                      </>}
                </span>
              </div>
            );
          })}
        </div>
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
      {tour && <Tour onClose={() => setTour(false)} />}
      {search && <SearchPalette onClose={() => setSearch(false)} />}
      {askLevel && !tour && <LevelPrompt onDone={() => undefined} />}
    </div>
  );
}

