import { Link } from "react-router-dom";

// kept apart from the policy texts, so the app shell and footers don't download them
export const LEGAL_PAGES: { path: string; title: string }[] = [
  { path: "/terms", title: "Terms of service" },
  { path: "/privacy", title: "Privacy policy" },
  { path: "/refunds", title: "Cancellation and refunds" },
  { path: "/contact", title: "Contact us" },
];

/** The row of policy links for footers. */
export function LegalLinks() {
  return (
    <nav className="k-row k-small legal-links" aria-label="Policies">
      {LEGAL_PAGES.map((p) => <Link key={p.path} className="muted" to={p.path}>{p.title}</Link>)}
    </nav>
  );
}
