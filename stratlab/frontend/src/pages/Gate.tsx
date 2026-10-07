import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Card, CardHead, LinkCard, PageHeader } from "../components/kit";
import { Google } from "../components/Icons";
import { LegalLinks } from "../components/LegalLinks";
import { Logo } from "../components/Logo";
import { openTour } from "../components/Onboarding";
import { api } from "../lib/api";
import { describePath } from "../lib/deepLinks";
import { signIn } from "../lib/signin";

/* The pages between a person and what they asked for: signed out on an app address ("Sign in to see …"), an address
 * nothing is at ("Page not found"), a page that isn't theirs ("You don't have access"), and Help. Each says what
 * happened and offers the way on; none moves anyone somewhere else without saying so. */

/** The frame for a visitor who isn't signed in: the logo home, and Sign in. */
function Public({ children }: { children: ReactNode }) {
  return (
    <div className="pub">
      <header className="pub-nav">
        <Link to="/" aria-label="StratLab home"><Logo size={40} /></Link>
        <button type="button" className="btn outline sm" onClick={() => void signIn()}>Sign in</button>
      </header>
      <main className="pub-main k-page gate">{children}</main>
      <footer className="pub-main gate"><LegalLinks /></footer>
    </div>
  );
}

const SignInButton = ({ label = "Sign in with Google" }: { label?: string }) => (
  <button type="button" className="btn lp-cta" onClick={() => void signIn()}><Google />{label}</button>
);

type PublicCompany = { region: string; symbol: string; name: string; page: string };

/** A visitor on an app address (a company, a notebook, Holdings): what is there, and sign-in that comes back to it. A
 * company with a public page offers that page too, no sign-in needed. */
export function SignInGate() {
  const loc = useLocation();
  const d = describePath(loc.pathname) ?? { what: "this page" };
  const [co, setCo] = useState<PublicCompany | null>(null);
  const region = d.company?.region, symbol = d.company?.symbol;
  useEffect(() => {
    if (!region || !symbol) return;
    let live = true;
    api<PublicCompany>(`/public/company/${region}/${encodeURIComponent(symbol)}`).then((c) => { if (live && c?.page?.startsWith("/stocks/")) setCo(c); }).catch(() => undefined);
    return () => { live = false; };
  }, [region, symbol]);
  const name = co?.name || symbol;
  const what = d.company ? (d.company.deep ? `the deep dive on ${name}` : name!) : d.what;
  return (
    <Public>
      <PageHeader eyebrow="StratLab" title={`Sign in to see ${what}`}
        lede={d.company
          ? "Company pages, with their numbers, filings, owners and charts, are inside StratLab. It's free to start: sign in with Google and this page opens."
          : `${what.charAt(0).toUpperCase()}${what.slice(1)} ${/s$/.test(what) && !/^this /.test(what) ? "are" : "is"} in your StratLab account. Sign in with Google and this page opens.`} />
      <div className="gate-actions">
        <SignInButton />
        <Link className="btn quiet" to="/">What is StratLab?</Link>
      </div>
      {co && (
        <Card label="Public page">
          <CardHead title={`${co.name} without signing in`} level={2} />
          <p className="k-small k-muted">The public page has the price, the year's range, key reported numbers and recent filings.</p>
          <a className="link" href={co.page}>Open the public page for {co.name}</a>
        </Card>
      )}
      <p className="k-small k-muted">Signing in only reads your name and email from Google. No card needed.</p>
    </Public>
  );
}

/** An address nothing is at: say so, show it, and offer search and the homes. Signed out, the landing page and sign-in. */
export function NotFound({ signedIn }: { signedIn: boolean }) {
  const loc = useLocation();
  const body = (
    <>
      <PageHeader eyebrow="Not found" title="Page not found"
        lede={<>There's no page at <span className="gate-path">{loc.pathname}</span>. The address may be mistyped, or the page has moved.</>} />
      {signedIn ? (
        <>
          <div className="gate-actions">
            <button type="button" className="btn" onClick={() => window.dispatchEvent(new Event("stratlab:search"))}>Search StratLab</button>
            <Link className="btn quiet" to="/">Go to your home</Link>
          </div>
          <div className="gate-links" aria-label="Places to go">
            <LinkCard to="/trade" title="Trade">Test trading ideas and paper trade them.</LinkCard>
            <LinkCard to="/invest" title="Invest">Research any Indian or US company.</LinkCard>
            <LinkCard to="/money" title="Money">Holdings, tax and what you own.</LinkCard>
            <LinkCard to="/help" title="Help">The tour, search and how to reach a person.</LinkCard>
          </div>
        </>
      ) : (
        <div className="gate-actions">
          <Link className="btn" to="/">Go to the StratLab home page</Link>
          <Link className="btn quiet" to="/pricing">Pricing</Link>
          <button type="button" className="btn quiet" onClick={() => void signIn(null)}>Sign in</button>
        </div>
      )}
    </>
  );
  return signedIn ? <div className="k-page gate">{body}</div> : <Public>{body}</Public>;
}

/** A page this account can't open (Admin for someone who isn't an admin): say so, rather than going home in silence. */
export function NoAccess({ what, email }: { what: string; email?: string | null }) {
  return (
    <div className="k-page gate">
      <PageHeader eyebrow="No access" title="You don't have access to this page"
        lede={`${what} ${/s$/.test(what) ? "are" : "is"} only for StratLab's team.${email ? ` You're signed in as ${email}.` : ""}`} />
      <div className="gate-actions">
        <Link className="btn" to="/">Go to your home</Link>
        <Link className="btn quiet" to="/contact">Contact us</Link>
      </div>
    </div>
  );
}

/** /help: the tour, search, plans, the connection check and a person. */
export function HelpPage() {
  return (
    <div className="k-page gate">
      <PageHeader eyebrow="Mine · Help" title="Help" lede="Find your way around StratLab, or reach a person." />
      <Card label="A quick tour">
        <CardHead title="A quick tour" actions={<button type="button" className="btn sm" onClick={openTour}>Start the tour</button>} />
        <p className="k-small k-muted">Four short steps: the spaces, search, each space's main button and your account.</p>
      </Card>
      <Card label="Search">
        <CardHead title="Search" actions={<button type="button" className="btn quiet sm" onClick={() => window.dispatchEvent(new Event("stratlab:search"))}>Search StratLab</button>} />
        <p className="k-small k-muted">Ctrl K (⌘K on a Mac) opens search on any page: companies, pages and ideas to test.</p>
      </Card>
      <div className="gate-links">
        <LinkCard to="/plans" title="Plans">What each plan includes, and what is open today.</LinkCard>
        <LinkCard to="/settings#check" title="Connection check">If prices or the idea builder look stuck.</LinkCard>
        <LinkCard to="/contact" title="Contact us">Questions reach a person.</LinkCard>
      </div>
    </div>
  );
}
