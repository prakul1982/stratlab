import type { ReactNode } from "react";
import { Logo } from "./Logo";

/** LIVE21B-001: the app's frame while a saved sign-in is read and the data status is asked (main.tsx), the same as the one public/boot.js
 * draws from the page's HTML: the menu's panel and the phone's top bar with the logo (its buttons' places held), and the page column. So a
 * signed-in load goes from this frame to the Shell's own with nothing but the menu filling in: never the landing's header with "Sign in",
 * never "Opening StratLab" alone on a bare page. Both keep the same classes; unit/site85 holds them equal. */
export function BootFrame({ children }: { children: ReactNode }) {
  return (
    <div className="shell boot-shell">
      <header className="topbar" aria-hidden="true"><span className="icon-btn" /><span className="brand"><Logo size={40} /></span><span className="row tight"><span className="icon-btn" /><span className="icon-btn" /><span className="icon-btn" /></span></header>
      <aside className="sidebar" aria-hidden="true"><div className="side-top"><div className="side-brand"><span className="brand"><Logo size={40} /></span></div></div></aside>
      <main className="main" id="main"><div className="page">{children}</div></main>
    </div>
  );
}
