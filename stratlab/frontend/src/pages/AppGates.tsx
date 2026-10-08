import { Link } from "react-router-dom";
import { Card, CardHead, LinkCard, PageHeader } from "../components/kit";
import { openTour } from "../components/Onboarding";
import { useDocTitle } from "../lib/title";

/* The pages for someone who is signed in and asked for something they can't have, and Help. (The pages for a visitor, "Sign
 * in to see …" and "Page not found", are in Gate.tsx, which doesn't need the app's account code.) */

/** A page this account can't open (Admin for someone who isn't an admin): say so, rather than going home in silence. */
export function NoAccess({ what, email }: { what: string; email?: string | null }) {
  useDocTitle("No access");
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
      <PageHeader eyebrow="Help" title="Help" lede="Find your way around StratLab, or reach a person." />
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
