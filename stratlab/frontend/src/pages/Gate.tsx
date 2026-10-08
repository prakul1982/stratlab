import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Card, CardHead } from "../components/kit/Card";
import { LinkCard } from "../components/kit/LinkCard";
import { PageHeader } from "../components/kit/PageHeader";
import { Google } from "../components/Icons";
import { PublicFrame } from "../components/PublicFrame";
import { publicGet, type ApiError } from "../lib/http";
import { describePath } from "../lib/deepLinks";
import { signIn } from "../lib/signin";
import { useDocTitle, withBrand } from "../lib/title";

/* The pages between a visitor and what they asked for: signed out on an app address ("Sign in to see …") and an address
 * nothing is at ("Page not found"). Each says what happened and offers the way on; none moves anyone somewhere else
 * without saying so. These need no account code, so they load with the landing page's small start-up. (A signed-in
 * person's "You don't have access" and Help are in AppGates.tsx.) */

const SignInButton = ({ label = "Continue with Google" }: { label?: string }) => (
  <button type="button" className="btn lp-cta" onClick={() => void signIn()}><Google />{label}</button>
);

type PublicCompany = { region: string; symbol: string; name: string; page: string };
/** What the lookup of a company's public page found: not yet, the page, or no company at the address. */
type Lookup = { state: "checking" } | { state: "found"; co: PublicCompany } | { state: "none" } | { state: "unknown" };

/** A visitor on an app address (a company, a notebook, Holdings): what is there, and sign-in that comes back to it. A
 * company is looked up first, so the page never promises "Sign in to see NOPESYMBOL": it names the company once it is
 * known, says there is none when there isn't, and until then says "this company". */
export function SignInGate() {
  const loc = useLocation();
  const d = describePath(loc.pathname) ?? { what: "this page" };
  const [look, setLook] = useState<Lookup>({ state: "checking" });
  const region = d.company?.region, symbol = d.company?.symbol;
  useEffect(() => {
    if (!region || !symbol) return;
    let live = true;
    setLook({ state: "checking" });
    publicGet<PublicCompany>(`/public/company/${region}/${encodeURIComponent(symbol)}`)
      .then((c) => { if (live) setLook(c?.page?.startsWith("/stocks/") ? { state: "found", co: c } : { state: "none" }); })
      .catch((e: ApiError) => { if (live) setLook(e.status === 404 ? { state: "none" } : { state: "unknown" }); });
    return () => { live = false; };
  }, [region, symbol]);
  const co = look.state === "found" ? look.co : null;
  const deep = !!d.company?.deep;
  const none = !!d.company && look.state === "none";
  const what = d.company ? (co ? (deep ? `the deep dive on ${co.name}` : co.name) : deep ? "this company's deep dive" : "this company's page") : d.what;
  const title = none ? `No company page for ${symbol}` : d.restricted ? "Sign in to StratLab" : `Sign in to see ${what}`;
  useEffect(() => {
    if (none) document.title = withBrand("Company not found");
    else if (co) document.title = withBrand(`Sign in · ${co.name}`);
  }, [none, co]);
  return (
    <PublicFrame className="gate">
      <PageHeader eyebrow="StratLab" title={title}
        lede={none ? "StratLab has no company page at this address. Check the symbol, or sign in with Google to search every listed company."
          : d.company ? "Company pages, with their numbers, filings, owners and charts, are inside StratLab. It's free to start: sign in with Google and the page opens if StratLab has one for this company."
          : d.restricted ? "Sign in with Google to continue. It's free to start."
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
    </PublicFrame>
  );
}

/** An address nothing is at: say so, show it, and offer search and the homes. Signed out, links to the pages anyone can open. */
export function NotFound({ signedIn }: { signedIn: boolean }) {
  const loc = useLocation();
  useDocTitle("Page not found");          // its own tab title (signed out, VisitorApp titles it the same way)
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
        <>
          <div className="gate-actions">
            <Link className="btn" to="/">Go to the StratLab home page</Link>
            <button type="button" className="btn quiet" onClick={() => void signIn(null)}>Continue with Google</button>
          </div>
          <nav className="gate-links" aria-label="Places to go">
            <LinkCard to="/pricing" title="Plans">What Free, Basic and Pro include and cost.</LinkCard>
            <LinkCard to="/faq" title="Questions">Tips, real trades, options, invites and your data.</LinkCard>
            <LinkCard to="/library" title="Strategy library">StratLab's own strategies with the verdict each earned.</LinkCard>
            <LinkCard to="/contact" title="Contact us">Questions reach a person.</LinkCard>
          </nav>
          <p className="k-small k-muted">Looking for a company? Public company pages are at <span className="gate-path">/stocks/in/SYMBOL</span> for India and <span className="gate-path">/stocks/us/SYMBOL</span> for the US, for example <a className="link" href="/stocks/in/TCS">TCS</a> or <a className="link" href="/stocks/us/AAPL">AAPL</a>.</p>
        </>
      )}
    </>
  );
  return signedIn ? <div className="k-page gate">{body}</div> : <PublicFrame className="gate">{body}</PublicFrame>;
}

