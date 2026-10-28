import { Link } from "react-router-dom";
import { INSTAGRAM } from "../content/seo";

// kept apart from the policy texts, so the app shell and footers don't download them
export const LEGAL_PAGES: { path: string; title: string }[] = [
  { path: "/terms", title: "Terms of service" },
  { path: "/privacy", title: "Privacy policy" },
  { path: "/refunds", title: "Cancellation and refunds" },
  { path: "/contact", title: "Contact us" },
];

/** The row of policy links for footers. `blog`: a link to the blog after them, for a footer inside the signed-in app (the
 * public pages carry it in their own site links; the blog is a page of the API, so a plain link, BLOG-1). */
export function LegalLinks({ blog = false }: { blog?: boolean }) {
  return (
    <nav className="k-row k-small legal-links" aria-label="Policies">
      {LEGAL_PAGES.map((p) => <Link key={p.path} className="muted" to={p.path}>{p.title}</Link>)}
      {blog && <a className="muted" href="/blog">Blog</a>}
      <a className="muted" href={INSTAGRAM} rel="me noopener">Instagram</a>
    </nav>
  );
}
