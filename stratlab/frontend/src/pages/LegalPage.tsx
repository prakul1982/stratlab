import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { CFG } from "../lib/config";
import { publicGet } from "../lib/http";
import { LEGAL_PAGES } from "../components/LegalLinks";
import { PublicFrame } from "../components/PublicFrame";
import { ChoiceControl } from "../components/Tracking";
import { DEFAULT_BUSINESS, inline, LEGAL_BLOCKS, LEGAL_UPDATED, type Business } from "../content/legal";

/** Who runs the site, from config.js, so the policies name the real business without a code change. */
const BUSINESS: Business = {
  name: CFG.BUSINESS_NAME || DEFAULT_BUSINESS.name,
  email: CFG.CONTACT_EMAIL || DEFAULT_BUSINESS.email,
  billing: CFG.BILLING_EMAIL || DEFAULT_BUSINESS.billing,
  privacy: CFG.PRIVACY_EMAIL || DEFAULT_BUSINESS.privacy,
  address: CFG.BUSINESS_ADDRESS || "",
  gstin: CFG.BUSINESS_GSTIN || "",
};

/** One string of the policy text (content/legal.ts, also written into each page's HTML at build time) as React nodes. */
const Inline = ({ text }: { text: string }) => (
  <>{inline(text, BUSINESS).map((t, i) => t.t === "b" ? <b key={i}>{t.s}</b> : t.t === "code" ? <code key={i}>{t.s}</code>
    : t.t === "mail" ? <a key={i} className="link" href={`mailto:${t.to}`}>{t.s}</a>
    : t.t === "link" ? <Link key={i} className="link" to={t.to}>{t.s}</Link> : <span key={i}>{t.s}</span>)}</>
);

function Policy({ path }: { path: string }) {
  return (
    <>
      {LEGAL_BLOCKS[path].map((b, i) => "h" in b ? <h2 key={i} className="h3">{b.h}</h2>
        : "p" in b ? <p key={i} className={b.small ? "small muted" : undefined}><Inline text={b.p} /></p>
        : <ul key={i}>{b.ul.filter((li) => typeof li === "string" || BUSINESS[li.when]).map((li, j) => <li key={j}><Inline text={typeof li === "string" ? li : li.text} /></li>)}</ul>)}
    </>
  );
}

/** The public policy pages. They open without signing in, as payment providers and app stores require. */
export function LegalPage() {
  const { pathname } = useLocation();
  // the seller's details set in Admin → Invoices (legal name, address, business email), when the owner has set them
  const [, seen] = useState(0);
  const [loaded, setLoaded] = useState(false);      // the seller's details are shown once fetched (or the fetch failed), not the fallback first
  useEffect(() => {
    let live = true;
    publicGet<{ legal_name?: string; address?: string; email?: string }>("/public/business").then((b) => {
      if (!live) return;
      setLoaded(true);
      if (!b) return;
      if (b.legal_name) BUSINESS.name = b.legal_name;
      if (b.address && !CFG.BUSINESS_ADDRESS) BUSINESS.address = b.address;
      if (b.email) BUSINESS.email = b.email;
      seen((n) => n + 1);
    }).catch(() => { if (live) setLoaded(true); });
    const slow = window.setTimeout(() => { if (live) setLoaded(true); }, 3000);   // a slow answer never keeps the page empty
    return () => { live = false; window.clearTimeout(slow); };
  }, []);
  const page = LEGAL_PAGES.find((p) => p.path === pathname) ?? LEGAL_PAGES[0];
  // the same frame as every other public page (header with the site's links and Sign in, the policies and the explore links at the
  // bottom), not a header of its own with four small links (PUB-1: the policies were the one public page with no way to the rest)
  return (
    <PublicFrame className="legal">
      <article className="legal-body stack">
        <nav className="legal-tabs" aria-label="Policies">
          {LEGAL_PAGES.map((p) => <Link key={p.path} className="k-pagenav-a" to={p.path}
            aria-current={p.path === page.path ? "page" : undefined}>{p.title}</Link>)}
        </nav>
        <h1 className="page-title">{page.title}</h1>
        <p className="small muted">Last updated {LEGAL_UPDATED[page.path]}</p>
        {loaded ? <Policy path={page.path} /> : <p className="small muted" role="status">Loading…</p>}
        {loaded && page.path === "/privacy" && <ChoiceControl />}{/* ADS-1: the answer about ads and analytics, and a way to change it */}
      </article>
    </PublicFrame>
  );
}
