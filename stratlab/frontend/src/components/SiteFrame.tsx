import { useRef, type ReactNode } from "react";
import { LegalLinks } from "./LegalLinks";
import { Logo } from "./Logo";
import { PUBLIC_MENU, SiteLinks } from "./PublicFrame";
import { SkipLink } from "./SkipLink";
import { useDetailsDismiss } from "../lib/useDetailsDismiss";

/** The line under every sign-in page's footer logo: the same words as the landing page's and /login's footer (pages/Login.tsx). */
export const SITE_DISCLAIMER = "Research and paper trading only. No real orders are placed. Past results don't predict future returns, and nothing on StratLab is investment advice.";

/* LIVE11B-002: one sign-in design. A signed-out visit to an app address ("Sign in to see Holdings") is drawn in /login's own frame: its
 * header (the logo home, the public pages' links, the phone's Menu), its ruled band with the sign-in in one centred column, and its
 * footer with the logo, the disclaimer and the links, not the narrower public-page frame with a "Sign in" button and no disclaimer.
 * The classes are /login's (pages/Login.tsx), so both pages share one set of rules in styles.css. */
export function SignInFrame({ children }: { children: ReactNode }) {
  const menu = useRef<HTMLDetailsElement>(null);
  useDetailsDismiss(menu);
  return (
    <div className="lp">
      <SkipLink />
      <header className="lp-nav">
        <a href="/" className="brand" aria-label="StratLab home"><Logo size={46} /></a>
        <nav aria-label="Site">
          {PUBLIC_MENU.map(([to, label]) => <a key={to} href={to}>{label}</a>)}
        </nav>
        <details className="lp-menu" ref={menu}>
          <summary>Menu</summary>
          <nav aria-label="Site (menu)">
            {PUBLIC_MENU.map(([to, label]) => <a key={to} href={to}>{label}</a>)}
          </nav>
        </details>
      </header>
      <main id="main" tabIndex={-1}>
        <section className="lp-hero ruled">
          <div className="lp-wrap lp-hero-grid lp-hero-solo lp-hero-login">
            <div className="stack g22 lp-hero-copy gate">{children}</div>
          </div>
        </section>
      </main>
      <footer className="lp-foot">
        <div className="lp-wrap spread wrap g16">
          <Logo size={30} />
          <p className="small muted k-measure">{SITE_DISCLAIMER} © {new Date().getFullYear()} StratLab.</p>
          <div className="stack g6">
            <SiteLinks />
            <LegalLinks />
          </div>
        </div>
      </footer>
    </div>
  );
}
