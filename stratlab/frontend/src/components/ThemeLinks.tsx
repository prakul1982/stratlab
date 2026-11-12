import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { fmtDate, safeHref } from "../lib/format";
import type { ThemeLinks } from "../lib/companyLinks";
import { Card, CardHead, DataTable, PlanNote, Skeleton } from "./kit";
import "./companylinks.css";

/* Who sells to whom among a theme's companies (lane b2, Pro): the customer and supplier links named in filings between the
 * theme's members, counted from one value-chain layer to another, then each link with its sentence, and the companies outside
 * the theme its members name most often. Other plans see how many links there are. Left out when no member has a link. */
export function ThemeLinksCard({ region, theme }: { region: "IN" | "US"; theme: string }) {
  const [v, setV] = useState<ThemeLinks | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    setV(null); setFailed(false);
    api<ThemeLinks>(`/research/links/theme?region=${region}&q=${encodeURIComponent(theme)}`).then((x) => live && setV(x), () => live && setFailed(true));
    return () => { live = false; };
  }, [region, theme]);
  if (failed || (v && (!v.available || (v.allowed ? !(v.edges?.length || v.outside?.length) : !v.links)))) return null;
  const co = (s: string) => <Link className="link" to={`/research/${region}/${encodeURIComponent(s)}`}>{s}</Link>;
  return (
    <Card id="theme-links" label="Who sells to whom">
      <CardHead title="Who sells to whom in this theme" info="Customer and supplier links named in the members' filings, by value-chain layer: from the supplier's layer to the customer's. Counts of links, not a score." />
      {!v ? <Skeleton label="Loading the theme's links" lines={3} /> : !v.allowed ? (
        <PlanNote plan="pro">{v.links} link{v.links === 1 ? "" : "s"} between this theme's companies, by layer, are on the {v.plan} plan.</PlanNote>
      ) : (
        <div className="k-stack">
          {!!v.layers?.length && <DataTable label="Links from layer to layer" rows={v.layers} rowKey={(r) => `${r.from}>${r.to}`} stack={false}
            columns={[{ key: "f", header: "Supplier's layer", rowHeader: true, wrap: true, cell: (r) => r.from },
              { key: "t", header: "Customer's layer", wrap: true, cell: (r) => r.to }, { key: "n", header: "Links", numeric: true, cell: (r) => r.links }]} />}
          {!!v.edges?.length && <DataTable label="Links between the theme's companies" rows={v.edges} rowKey={(e) => `${e.supplier}>${e.customer}>${e.doc_url}`} stack
            csv="theme customer and supplier links"
            columns={[{ key: "s", header: "Supplier", rowHeader: true, cell: (e) => <>{co(e.supplier)}<span className="k-sub-line">{e.supplier_layer}</span></>, csv: (e) => e.supplier },
              { key: "c", header: "Customer", cell: (e) => <>{co(e.customer)}<span className="k-sub-line">{e.customer_layer}</span></>, csv: (e) => e.customer },
              { key: "q", header: "Filing says", wrap: true, cell: (e) => <><span className="k-small">“{e.quote}”</span>{" "}
                <a className="link k-small" href={safeHref(e.doc_url)} target="_blank" rel="noopener noreferrer">{e.stated_by}'s filing{e.said_on ? `, ${fmtDate(e.said_on)}` : ""} ↗</a></>, csv: (e) => e.quote }]} />}
          {!!v.outside?.length && <DataTable label="Named most often outside the theme" rows={v.outside} rowKey={(o) => o.name} stack={false}
            columns={[{ key: "n", header: "Named outside the theme", rowHeader: true, wrap: true, cell: (o) => (o.symbol ? co(o.symbol) : o.name) },
              { key: "l", header: "Links", numeric: true, cell: (o) => o.links }, { key: "m", header: "By members", wrap: true, cell: (o) => o.members.join(", ") }]} />}
          <p className="k-note">From the companies' own filings, each link with its sentence. Facts, not advice.</p>
        </div>
      )}
    </Card>
  );
}
