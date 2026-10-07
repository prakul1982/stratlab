import { useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { supabase } from "../lib/api";
import { inWords, marketState } from "../lib/marketHours";
import type { Market, Me } from "../lib/types";
import { Close, Compass, Download, Layers, LogOut, Pencil, Share, Shield, Updown, User, Wallet } from "./Icons";

// The two small menus at the foot of the sidebar: which markets are open, and the account. Each is one line until
// opened; opened, it floats above the line (a sheet from the bottom on a phone) and closes with Esc or a click outside.

// the old fold-out list remembered whether it was open; the pop-up always starts shut, so that note is dropped
try { localStorage.removeItem("stratlab.markets.open"); } catch { /* storage off */ }

const SHORT: Record<string, string> = { IN: "India", CRYPTO: "Crypto", US: "US", UK: "UK", EU: "Europe", JP: "Japan", FX: "Forex", MCX: "MCX", CDS: "Currency F&O", CMDTY: "Commodities" };

/** Open and close a pop-up: Esc or a click outside closes it, and Esc hands focus back to the button that opened it. */
function usePop() {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    // the first thing to act on gets focus, so the keyboard carries on inside
    (panel.current?.querySelector<HTMLElement>("[role=menuitem]") ?? panel.current)?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();          // only the pop-up closes, not the drawer behind it
      setOpen(false);
      btn.current?.focus();
    };
    const down = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !btn.current?.contains(t)) setOpen(false);
    };
    document.addEventListener("keydown", key, true);
    document.addEventListener("pointerdown", down);
    return () => { document.removeEventListener("keydown", key, true); document.removeEventListener("pointerdown", down); };
  }, [open]);
  return { open, setOpen, btn, panel };
}

/** What a market is doing, in a few words: "Closes in 3h", "Opens in 1d 4h", "Holiday · opens in 2d". */
function when(m: Market) {
  const st = marketState(m);
  if (st.always) return { st, text: "Open 24/7" };
  if (st.offline) return { st, text: "Data offline" };
  const mins = st.change ? (st.change.getTime() - Date.now()) / 60000 : null;
  if (st.open) return { st, text: mins === null ? "Open" : `Closes in ${inWords(mins)}` };
  const opens = mins === null ? "Closed" : `Opens in ${inWords(mins)}`;
  return { st, text: st.closedFor === "holiday" ? `Holiday · ${opens.toLowerCase()}` : opens };
}

/** "● 1 of 10 markets open": one line that opens the list of markets. */
export function MarketsNow({ markets }: { markets: Market[] }) {
  const { open, setOpen, btn, panel } = usePop();
  const id = useId();
  const live = markets.filter((m) => m.status !== "soon" && m.id !== "CSV");
  if (!live.length) return null;
  const rows = live.map((m) => ({ m, ...when(m) }));
  const openCount = rows.filter((r) => r.st.open).length;
  // India leads (the dot is India's), so the line agrees with "Indian markets open in …" on My space (R1-070)
  const india = rows.find((r) => r.m.id === "IN");
  return (
    <div className="side-pop-wrap">
      <button ref={btn} className="mkt-btn" aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => setOpen(!open)}>
        <span className={`mkt-dot${(india ? india.st.open : openCount) ? " on" : ""}`} aria-hidden="true" />
        <span>{india ? `India ${india.st.open ? "open" : "closed"} · ` : ""}{openCount}/{live.length} markets open</span>
      </button>
      {open && <>
        <div className="side-pop-back" aria-hidden="true" />
        <div ref={panel} id={id} className="side-pop mkt-pop" role="dialog" aria-label="Markets now" tabIndex={-1}>
          <div className="side-pop-head">
            <b>Markets now</b><span className="muted">in your time</span>
            <button className="side-pop-x" aria-label="Close" onClick={() => { setOpen(false); btn.current?.focus(); }}><Close size={16} /></button>
          </div>
          <ul className="mkt-list">
            {rows.map(({ m, st, text }) => (
              <li key={m.id} title={[m.name, st.hoursLocal, st.hoursYours].filter(Boolean).join(" · ")}>
                <span className={`mkt-dot${st.open ? " on" : ""}${st.offline ? " off" : ""}`} aria-hidden="true" />
                <span className="mkt-name">{SHORT[m.id] ?? m.name}</span>
                <span className={st.open ? "mkt-when" : "mkt-when muted"}>{text}</span>
              </li>
            ))}
          </ul>
        </div>
      </>}
    </div>
  );
}

/** The person's initials button, with the plan, opening Account, Settings, Plan, Invite, Get the app, All features, Help and Sign out. */
export function AccountMenu({ me, onTour, onGo }: { me: Me | null; onTour: () => void; onGo: () => void }) {
  const { open, setOpen, btn, panel } = usePop();
  const id = useId();
  const email = me?.email ?? "";
  const initial = (email.match(/[a-z0-9]/i)?.[0] ?? "?").toUpperCase();
  const plan = me?.plan_info.name;
  // the item goes with the menu, so focus goes back to the button first (and a dialog the item opens returns it there)
  const done = (f?: () => void) => () => { setOpen(false); btn.current?.focus(); f?.(); };
  // up and down move between the items, as in any menu
  const keys = (e: ReactKeyboardEvent) => {
    const items = Array.from(panel.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []);
    const i = items.indexOf(document.activeElement as HTMLElement);
    const to = e.key === "ArrowDown" ? (i + 1) % items.length : e.key === "ArrowUp" ? (i - 1 + items.length) % items.length
      : e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : null;
    if (to !== null) { e.preventDefault(); items[to]?.focus(); }
    else if (e.key === "Tab") setOpen(false);
  };
  return (
    <div className="side-pop-wrap">
      {/* named by what it shows, then what it opens: "owner Pro plan, account menu" */}
      <button ref={btn} className="acct-btn" aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => setOpen(!open)}>
        <span className="avatar" aria-hidden="true">{initial}</span>
        <span className="acct-name">{email.split("@")[0] || "Account"}</span>
        {plan && <span className="plan-tag">{plan}</span>}
        <span className="sr-only">{plan ? " plan" : ""}, account menu</span>
        <Updown size={14} />
      </button>
      {open && <>
        <div className="side-pop-back" aria-hidden="true" />
        <div ref={panel} id={id} className="side-pop acct-pop" role="menu" aria-label="Account" onKeyDown={keys}>
          {email && <div className="side-pop-head" role="presentation"><span className="muted acct-email">{email}</span></div>}
          <Link role="menuitem" to="/account" onClick={done(onGo)}><User size={16} />Account{plan && <span className="plan-tag">{plan}</span>}</Link>
          <Link role="menuitem" to="/settings" onClick={done(onGo)}><Pencil size={16} />Settings</Link>
          <Link role="menuitem" to="/plans" onClick={done(onGo)}><Wallet size={16} />Plan</Link>
          <Link role="menuitem" to="/invite" onClick={done(onGo)}><Share size={16} />Invite friends</Link>
          <Link role="menuitem" to="/app" onClick={done(onGo)}><Download size={16} />Get the app</Link>
          <hr />
          {me?.is_admin && <Link role="menuitem" to="/admin" onClick={done(onGo)}><Shield size={16} />Admin</Link>}
          <Link role="menuitem" to="/features" onClick={done(onGo)}><Layers size={16} />All features</Link>
          <button role="menuitem" onClick={done(onTour)}><Compass size={16} />Help</button>
          <hr />
          <button role="menuitem" onClick={done(() => supabase.auth.signOut())}><LogOut size={16} />Sign out</button>
        </div>
      </>}
    </div>
  );
}
