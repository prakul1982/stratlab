import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { Card, CardHead, FigureTable, Skeleton } from "../../components/kit";
import { MARKET, rebuildLine, type PagesRebuild } from "./rebuild";

/** Admin → Data: how far the company pages are rebuilt to the facts a page shows now (owner, 13 Nov), per market, from what the
 * stored pages say (counted when the screens gather them; no read of its own). */
export function PagesRebuildPanel() {
  const [r, setR] = useState<PagesRebuild | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => { api<PagesRebuild>("/admin/stock-pages/rebuild").then(setR, () => setFailed(true)); }, []);
  return (
    <Card label="Company pages rebuild">
      <CardHead title="Company pages rebuild" info="When the facts a company page shows change, every stored page is rebuilt to them a few at a time, the largest companies first. A page not rebuilt yet still shows, and is rebuilt when someone opens it." />
      {failed ? <p className="k-small k-down" role="alert">The rebuild count couldn't be read. Reload the page.</p> : !r ? <Skeleton label="Loading the rebuild count" lines={2} /> : (
        <FigureTable label={`Company pages at facts version ${r.version}`} header="Market" valueHeader="Pages at this version" noteHeader="What it counts"
          rows={r.markets.map((m) => ({ key: m.region, label: MARKET[m.region] ?? m.region, ...rebuildLine(m, r.version) }))} />
      )}
    </Card>
  );
}
