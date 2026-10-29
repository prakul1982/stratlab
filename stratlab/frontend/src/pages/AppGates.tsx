import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardHead, DataTable, LinkCard, PageHeader, type Column } from "../components/kit";
import { ALL_PAGES, NAV, type Located } from "../lib/nav";
import { openTour } from "../components/Onboarding";
import { useDocTitle } from "../lib/title";
import { HELP_GROUPS, HELP_TOPICS } from "../lib/helpTopics";

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
        <Link className="btn" to="/">Go to My space</Link>
        <Link className="btn quiet" to="/contact">Contact us</Link>
      </div>
    </div>
  );
}

/** /help: the tour, search, every explanation StratLab has written (the (i) texts search also finds), plans, the
 * connection check and a person. Reached from the account menu and from search (DI-014). */
export function HelpPage() {
  const [q, setQ] = useState("");
  const t = q.trim().toLowerCase();
  const topics = HELP_TOPICS.filter((h) => !t || `${h.title} ${h.words} ${h.text}`.toLowerCase().includes(t));
  // IA-1: every page by the name it had and where it is now, so a feature is found by its old name or its new one
  const places = ALL_PAGES.filter((l) => !t || `${l.page.label} ${l.page.was ?? ""} ${l.group.label} ${l.page.words}`.toLowerCase().includes(t));
  const placeCols: Column<Located>[] = [
    { key: "name", header: "Page", rowHeader: true, cell: (l) => l.page.was ?? l.page.label },
    { key: "now", header: "Where it is now", wrap: true, cell: (l) => <Link className="link" to={l.page.to}>{[NAV[l.space].label, ...(l.group.pages.length > 1 ? [l.group.label] : []), l.page.label].join(" › ")}</Link> },
  ];
  return (
    // the page's own width, like every other page (LIVE1B-043: a 640px column pinned to the left with 40% of the screen empty)
    <div className="k-page">
      <PageHeader title="Help" lede="Find your way around StratLab, read how each check and figure is worked out, or reach a person." />
      <div className="gate-links">
        <LinkCard to="/contact" title="Contact us">Questions reach a person.</LinkCard>
        <LinkCard to="/settings#check" title="Connection check">If prices or the idea builder look stuck.</LinkCard>
        <LinkCard to="/plans" title="Plans">What each plan includes, and what is open today.</LinkCard>
      </div>
      <Card label="A quick tour">
        <CardHead title="A quick tour" actions={<button type="button" className="btn sm" onClick={openTour}>Start the tour</button>} />
        <p className="k-small k-muted">Five short steps: the spaces, search, this space's main button, the menu and its tabs, and your account.</p>
      </Card>
      <Card label="Search">
        <CardHead title="Search" actions={<button type="button" className="btn quiet sm" onClick={() => window.dispatchEvent(new Event("stratlab:search"))}>Search StratLab</button>} />
        <p className="k-small k-muted">Ctrl K (⌘K on a Mac) opens search on any page: companies, pages, these explanations and ideas to test.</p>
      </Card>
      {/* one box narrows both lists below: the pages by their old or new names, and the explanations */}
      <div className="k-field wide">
        <input className="k-input" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Narrow the lists: a page like “Screener”, or a word like “drawdown”" aria-label="Narrow the pages and explanations" />
      </div>
      <Card label="Where things are" testId="help-places">
        <CardHead title="Where things are" info="The menu has one entry for each kind of work; the pages that were entries of their own are its tabs, at the same addresses. A page that was renamed is listed by its old name." />
        {places.length ? <DataTable stack label="Every page and where it is now" columns={placeCols} rows={places} rowKey={(l) => l.page.to} />
          : <p className="k-small k-muted">No page matches that. Try a shorter word, or ask in search (Ctrl K).</p>}
      </Card>
      <Card label="Explanations" testId="help-topics">
        <CardHead title="How things are worked out" />
        {topics.length ? (
          // grouped when nothing is typed, one list of what matches when something is
          <div className="help-topics">
            {(t ? [["", topics] as const] : HELP_GROUPS.map(([g]) => [g, topics.filter((h) => h.group === g)] as const)).map(([g, list]) => list.length > 0 && (
              <section key={g || "found"} className="help-group" aria-label={g || undefined}>
                {g && <h3 className="k-sub">{g}</h3>}
                {list.map((h) => (
                  <details key={h.key} className="help-topic">
                    <summary>{h.title}</summary>
                    <p className="k-small">{h.text}</p>
                  </details>
                ))}
              </section>
            ))}
          </div>
        ) : <p className="k-small k-muted">Nothing matches that. Try a shorter word, or ask in search (Ctrl K).</p>}
      </Card>
    </div>
  );
}
