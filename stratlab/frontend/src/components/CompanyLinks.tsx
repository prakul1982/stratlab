import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { fmtDate, safeHref } from "../lib/format";
import { CSV_HEAD, GROUPS, csvRows, factsLine, inGroup, lockedText, type CompanyLink, type CompanyLinks } from "../lib/companyLinks";
import { Card, CardHead, ErrorState, PlanNote, Skeleton } from "./kit";
import "./companylinks.css";

/* The customer and supplier map on a company page (lane b2): the customers and suppliers this company's filings name, and
 * the companies whose filings name it, each with the sentence word for word, its date and the filing. Free sees the latest
 * few; Basic every link; Pro the CSV too. Hidden when no filing names anyone. */

function Row({ i }: { i: CompanyLink }) {
  const name = i.symbol ? <Link className="link" to={`/research/${i.region}/${encodeURIComponent(i.symbol)}`}><b>{i.name}</b></Link> : <b>{i.name}</b>;
  return (
    <li data-link={i.name}>
      <div className="co-links-head">{name}{i.as_filed && <span className="k-note">as filed, not linked</span>}</div>
      <span className="k-sub-line">{factsLine(i)}{i.said_on ? ` · said on ${fmtDate(i.said_on)}` : ""}</span>
      <blockquote className="co-links-quote k-small">“{i.quote}”</blockquote>
      <a className="link k-small" href={safeHref(i.doc_url)} target="_blank" rel="noopener noreferrer">{i.doc_title || "The filing"} ↗</a>
    </li>
  );
}

export function CompanyLinksCard({ region, symbol }: { region: "IN" | "US"; symbol: string }) {
  const [v, setV] = useState<CompanyLinks | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setV(null); setError(null);
    api<CompanyLinks>(`/research/links/${region}/${encodeURIComponent(symbol)}`)
      .then((x) => live && setV(x))
      .catch((e) => live && setError(e instanceof Error ? e.message : "The links couldn't be loaded."));
    return () => { live = false; };
  }, [region, symbol]);

  if (v && v.total === 0) return null;                      // no filing names anyone: the card is left out
  const csv = v?.csv && v.items.length > 0 ? (
    <button className="btn quiet sm" onClick={() => import("../lib/csvDownload").then((m) => m.downloadCsv(`${symbol.toLowerCase()}-customers-suppliers.csv`, CSV_HEAD, csvRows(v.items)))}>CSV</button>
  ) : null;
  const groups = v ? GROUPS.map((g) => ({ ...g, rows: inGroup(v.items, g.id) })).filter((g) => g.rows.length) : [];
  return (
    <Card id="customers-suppliers" label="Customers and suppliers">
      <CardHead title="Customers and suppliers" actions={csv}
        info="Customers and suppliers named in filings: this company's own (order wins, a share of sales, a sole supplier) and other companies' that name it. Each with the sentence word for word and the filing." />
      {error ? <ErrorState title="The links couldn't be loaded">{error}</ErrorState> : !v ? <Skeleton label="Loading customers and suppliers" lines={3} /> : (
        <div className="k-stack">
          <div className={`co-links-groups${groups.length > 1 ? " two" : ""}`}>
            {groups.map((g) => (
              <section key={g.id} className="co-links-group" aria-label={g.title}>
                <h3>{g.title}</h3>
                <ul className="co-links-list">{g.rows.map((i) => <Row key={i.id} i={i} />)}</ul>
              </section>
            ))}
          </div>
          {v.locked > 0 && <PlanNote plan="basic">{lockedText(v.locked, v.plan_for_all)}</PlanNote>}
          {v.full && !v.csv && v.items.length > 0 && <p className="k-note">The links as a CSV, and the links among a theme's companies, are on the {v.plan_for_csv} plan.</p>}
          <p className="k-note">{v.note}</p>
        </div>
      )}
    </Card>
  );
}
