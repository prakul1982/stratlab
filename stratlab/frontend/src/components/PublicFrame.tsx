import { useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { LegalLinks } from "./LegalLinks";
import { Logo } from "./Logo";
import { SkipLink } from "./SkipLink";
import { signedInHere, signIn, warmSignIn } from "../lib/signin";
import { useDetailsDismiss } from "../lib/useDetailsDismiss";

/** The landing page's sections and Plans, for the phone Menu (the company pages carry the same links). */
export const PUBLIC_MENU: [string, string][] = [["/#trade", "Trade"], ["/#invest", "Invest"], ["/#money", "Money"], ["/#alerts", "Alerts"], ["/pricing", "Plans"], ["/#faq", "FAQ"], ["/stocks", "Companies"]];

/** For someone already signed in: a plain link (a whole page load, so the app starts, not the visitor's landing page). */
export const OpenApp = ({ className = "btn outline sm" }: { className?: string }) => <a className={className} href="/">Open StratLab</a>;

/** The frame around every public page that isn't the landing page itself (a shared verdict, StratLab's library, "Sign in
 * to see …", "Page not found"): the logo home, a way in, the page in a `main`, and the policies at the bottom. */
export function PublicFrame({ children, className = "", action }: { children: ReactNode; className?: string; action?: ReactNode }) {
  const menu = useRef<HTMLDetailsElement>(null);
  useDetailsDismiss(menu);
  return (
    <div className="pub">
      <SkipLink />
      <header className="pub-nav">
        <Link to="/" aria-label="StratLab home"><Logo size={40} /></Link>
        {/* wider screens: the same links as a row, as on the landing page and the company pages (R80-017: a visitor reading a
            strategy had no way to Plans or the questions but the logo) */}
        <nav className="pub-links" aria-label="Site">
          {PUBLIC_MENU.map(([to, label]) => <a key={to} href={to}>{label}</a>)}
        </nav>
        {/* on a phone (640px and under) the way to the rest of the site: the same `details` Menu the landing page has. Beside a
            page's own wide button (/library's "Continue with Google") the Menu sits mid-header, so its list opens from the
            button's left edge, under it, not out to the screen's left edge (R29A-009) */}
        <details className={`lp-menu pub-menu${action ? " pub-menu-start" : ""}`} ref={menu}>
          <summary>Menu</summary>
          <nav aria-label="Site (menu)">
            {PUBLIC_MENU.map(([to, label]) => <a key={to} href={to}>{label}</a>)}
          </nav>
        </details>
        {action ?? (signedInHere() ? <OpenApp /> : <a className="btn outline sm" href="/" onPointerEnter={warmSignIn} onFocus={warmSignIn} onTouchStart={warmSignIn} onClick={(e) => { e.preventDefault(); void signIn(); }}>Sign in</a>)}
      </header>
      <main id="main" tabIndex={-1} className={`pub-main k-page ${className}`.trim()}>{children}</main>
      <footer className={`pub-main ${className}`.trim()}><LegalLinks /></footer>
    </div>
  );
}
