import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { LegalLinks } from "./LegalLinks";
import { Logo } from "./Logo";
import { SkipLink } from "./SkipLink";
import { signIn } from "../lib/signin";

/** The frame around every public page that isn't the landing page itself (a shared verdict, StratLab's library, "Sign in
 * to see …", "Page not found"): the logo home, a way in, the page in a `main`, and the policies at the bottom. */
export function PublicFrame({ children, className = "", action }: { children: ReactNode; className?: string; action?: ReactNode }) {
  return (
    <div className="pub">
      <SkipLink />
      <header className="pub-nav">
        <Link to="/" aria-label="StratLab home"><Logo size={40} /></Link>
        {action ?? <button type="button" className="btn outline sm" onClick={() => void signIn()}>Sign in</button>}
      </header>
      <main id="main" tabIndex={-1} className={`pub-main k-page ${className}`.trim()}>{children}</main>
      <footer className={`pub-main ${className}`.trim()}><LegalLinks /></footer>
    </div>
  );
}
