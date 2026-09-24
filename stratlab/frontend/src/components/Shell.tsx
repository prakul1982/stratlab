import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import type { Market } from "../lib/types";
import { Book, Flask, Menu, Moon, Plus, Pulse, Star, Sun, User } from "./Icons";
import { VerdictBadge } from "./ui";

function marketNow(m: Market): string {
  if (m.status === "offline") return "offline";
  if (!m.hours || !m.hours.open || !m.hours.close) return m.id === "CRYPTO" ? "always open" : "open";
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: m.tz, weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const day = get("weekday"), hm = `${get("hour")}:${get("minute")}`;
  const weekend = day === "Sat" || day === "Sun";
  return !weekend && hm >= m.hours.open && hm < m.hours.close ? "open" : "closed";
}

export function Shell({ children }: { children: ReactNode }) {
  const { notebooks, markets, theme, setTheme, me } = useApp();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const nav = useNavigate();
  useEffect(() => setOpen(false), [loc.pathname]);
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  const live = markets.filter((m) => m.status !== "soon" && m.id !== "CSV");

  const sidebar = (
    <aside className={`sidebar${open ? " open" : ""}`} aria-label="Notebooks and navigation">
      <Link to="/" className="brand"><Flask />StratLab</Link>
      <button className="btn" onClick={() => nav("/new")}><Plus size={18} />New notebook</button>
      <nav className="stack" style={{ gap: 4 }} aria-label="Notebooks">
        <div className="eyebrow" style={{ padding: "0 8px 6px" }}>Notebooks</div>
        {notebooks === null && <span className="small muted" style={{ padding: "0 12px" }}>Loading…</span>}
        {notebooks?.length === 0 && <span className="small muted" style={{ padding: "0 12px" }}>Your notebooks will show up here.</span>}
        {notebooks?.map((n) => {
          const inst = n.instrument && "symbol" in n.instrument ? n.instrument.symbol : null;
          const count = n.summary?.experiments ?? 0;
          return (
            <NavLink key={n.id} to={`/n/${n.id}`} className={({ isActive }) => `nb-link${isActive || loc.pathname.startsWith(`/n/${n.id}/`) ? " active" : ""}`}>
              <b>{n.name}</b>
              <span>{[inst, `${count} experiment${count === 1 ? "" : "s"}`].filter(Boolean).join(" · ")}</span>
            </NavLink>
          );
        })}
      </nav>
      <nav className="side-nav stack" style={{ gap: 2 }} aria-label="Main">
        <NavLink to="/paper"><Pulse />Paper trading</NavLink>
        <NavLink to="/plans"><Star />Plans</NavLink>
        <NavLink to="/account"><User />Account{me && <span className="badge skip" style={{ marginLeft: "auto" }}>{me.plan_info.name}</span>}</NavLink>
        <NavLink to="/" end><Book />All notebooks</NavLink>
      </nav>
      <div className="stack small muted" style={{ marginTop: "auto", gap: 8 }}>
        {live.length > 0 && <div className="eyebrow">Markets now</div>}
        {live.map((m) => {
          const s = marketNow(m);
          return (
            <div key={m.id} className="row" style={{ gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", flex: "none", boxSizing: "border-box",
                background: s === "open" || s === "always open" ? "var(--blue)" : "transparent", border: `1.5px solid ${s === "offline" ? "var(--orange)" : "var(--muted)"}` }} />
              {m.name} · {s}
            </div>
          );
        })}
        <button className="link" style={{ alignSelf: "flex-start", display: "flex", gap: 8, alignItems: "center", color: "var(--muted)" }}
          onClick={() => setTheme(dark ? "light" : "dark")}>{dark ? <Sun size={16} /> : <Moon size={16} />}{dark ? "Light pages" : "Night mode"}</button>
      </div>
    </aside>
  );

  return (
    <div className="shell">
      <header className="topbar">
        <button className="icon-btn" aria-label="Open menu" onClick={() => setOpen(true)}><Menu /></button>
        <Link to="/" className="brand" style={{ fontSize: 21 }}><Flask size={24} />StratLab</Link>
        <button className="icon-btn" aria-label="New notebook" onClick={() => nav("/new")}><Plus /></button>
      </header>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      {sidebar}
      <main className="main">{children}</main>
    </div>
  );
}

export { VerdictBadge };
