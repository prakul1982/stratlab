import { useMemo, useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { Card, EmptyState, PageHeader } from "../components/kit";
import { PageTags } from "../components/PageTags";
import { NAV, SPACE_LIST, groupPath, locateGroup, type NavPage } from "../lib/nav";

/* The two pages that list the menu as cards: a group's own page (/trade/g/practise, from the group's title in the sidebar)
 * and "All features" (/features). Both are drawn from lib/nav.ts, so a page added there appears in the sidebar, here,
 * in the breadcrumb and in ⌘K together. */

/** One page as a card: its name, what it is for in a line, and the way in. */
function FeatureCard({ page }: { page: NavPage }) {
  return (
    <Card testId="group-card">
      <div className="nav-card">
        <h2 className="k-card-title"><Link to={page.to}>{page.label}</Link></h2>
        <p className="nav-card-line">{page.blurb}</p>
        <div className="nav-card-foot">
          <Link className="btn quiet sm" to={page.to} aria-label={`Open ${page.label}`}>Open</Link>
          <PageTags page={page} />
        </div>
      </div>
    </Card>
  );
}

/** /trade/g/<group>, /invest/g/<group>, /money/g/<group>: one card for each page in the group. */
export function GroupPage() {
  const { pathname } = useLocation();
  const g = locateGroup(pathname);
  if (!g) return <Navigate to="/features" replace />;
  return (
    <div className="stack nav-page" data-testid="group-page" data-group={g.group.id}>
      <PageHeader eyebrow={`${NAV[g.space].label} · ${g.group.label}`} title={g.group.label} lede={g.group.blurb} />
      <div className="nav-cards">
        {g.group.pages.map((p) => <FeatureCard key={p.to} page={p} />)}
      </div>
    </div>
  );
}

/** Mine's own pages, listed beside the three spaces' groups. */
const MINE_PAGES: { to: string; label: string; line: string }[] = [
  { to: "/mine", label: "My space", line: "Your net worth, today's change, the markets, what is coming up and your watchlist, in the order you choose." },
  { to: "/news", label: "Briefs", line: "A short brief after each market close, for India, the US and the companies you follow." },
  { to: "/holdings", label: "Connected accounts", line: "Bring in your broker's file: the stocks you hold." },
];

/** /features: every page by space and group with its one-liner, and a box to narrow the list. */
export function FeaturesPage() {
  const [q, setQ] = useState("");
  const t = q.trim().toLowerCase();
  const has = (p: { label: string; line: string; words?: string }) => !t || `${p.label} ${p.line} ${p.words ?? ""}`.toLowerCase().includes(t);
  const spaces = useMemo(() => SPACE_LIST.map((s) => ({
    id: s, label: NAV[s].label, home: NAV[s].home,
    groups: NAV[s].groups.map((g) => ({ g, pages: g.pages.filter(has) })).filter((x) => x.pages.length),
  })).filter((s) => s.groups.length), [t]);   // eslint-disable-line react-hooks/exhaustive-deps
  const mine = MINE_PAGES.filter(has);
  return (
    <div className="stack nav-page" data-testid="features-page">
      <PageHeader eyebrow="StratLab" title="All features" lede="Every page in StratLab by space and group, with what it is for in a line. Press Ctrl K or ⌘K to go to any of them by name." />
      <div className="k-field wide">
        <input className="k-input" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Narrow the list: a page, or a word like “tax” or “options”" aria-label="Narrow the list of features" />
      </div>
      {!spaces.length && !mine.length && <EmptyState title="No page matches that" action={{ label: "Show everything", onClick: () => setQ("") }}>Try a shorter word, or press Ctrl K to ask in your own words.</EmptyState>}
      {mine.length > 0 && (
        <Card testId="features-mine">
          <h2 className="k-card-title"><Link to="/mine">Mine</Link></h2>
          <ul className="feat-list">
            {mine.map((p) => <li key={p.to}><Link to={p.to}><b>{p.label}</b></Link><span className="feat-line">{p.line}</span></li>)}
          </ul>
        </Card>
      )}
      {spaces.map((s) => (
        <Card key={s.id} testId={`features-${s.id}`}>
          <h2 className="k-card-title"><Link to={s.home}>{s.label}</Link></h2>
          {s.groups.map(({ g, pages }) => (
            <section key={g.id} className="feat-group" aria-label={`${s.label}: ${g.label}`}>
              <h3 className="feat-group-title"><Link to={groupPath(s.id, g)}>{g.label}</Link></h3>
              <ul className="feat-list">
                {pages.map((p) => (
                  <li key={p.to}><Link to={p.to}><b>{p.label}</b></Link><PageTags page={p} /><span className="feat-line">{p.line}</span></li>
                ))}
              </ul>
            </section>
          ))}
        </Card>
      ))}
    </div>
  );
}
