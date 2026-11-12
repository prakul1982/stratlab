import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

/* A company page's link to its business group (pages/BusinessGroupsPage.tsx), when the shareholding filings put it in one. Its own
 * small file, so the company page doesn't load the groups' pages. */
/** "Part of the X group (8 listed companies)" on a company page, when the filings put it in one. */
export function GroupLink({ symbol }: { symbol: string }) {
  const [g, setG] = useState<{ slug: string; name: string; companies: number } | null>(null);
  useEffect(() => {
    let live = true;
    setG(null);
    api<{ group: { slug: string; name: string; companies: number } | null }>(`/invest/groups/of/${encodeURIComponent(symbol)}`)
      .then((x) => live && setG(x.group)).catch(() => undefined);
    return () => { live = false; };
  }, [symbol]);
  if (!g) return null;
  return <span className="k-small" data-testid="group-link">Part of the <Link className="link" to={`/invest/groups/${g.slug}`}>{g.name} group</Link> ({g.companies} listed companies)</span>;
}
