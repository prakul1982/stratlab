import { useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { LegalLinks } from "./LegalLinks";
import { Logo } from "./Logo";
import { SkipLink } from "./SkipLink";
import { signedInHere, signIn } from "../lib/signin";
import { useDetailsDismiss } from "../lib/useDetailsDismiss";

/** The landing page's sections and Plans, for the phone Menu (the company pages carry the same links). */
export const PUBLIC_MENU: [string, string][] = [["/#trade", "Trade"], ["/#invest", "Invest"], ["/#money", "Money"], ["/pricing", "Plans"], ["/stocks", "Companies"]];

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
        {/* on a phone (640px and under) the way to the rest of the site: the same `details` Menu the landing page has */}
        <details className="lp-menu pub-menu" ref={menu}>
          <summary>Menu</summary>
          <nav aria-label="Site (menu)">
            {PUBLIC_MENU.map(([to, label]) => <a key={to} href={to}>{label}</a>)}
          </nav>
        </details>
        {action ?? (signedInHere() ? <OpenApp /> : <button type="button" className="btn outline sm" onClick={() => void signIn()}>Sign in</button>)}
      </header>
      <main id="main" tabIndex={-1} className={`pub-main k-page ${className}`.trim()}>{children}</main>
      <footer className={`pub-main ${className}`.trim()}><LegalLinks /></footer>
    </div>
  );
}
