import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { eyebrowOf } from "../lib/eyebrow";
import { asOf, fmtDate, marketTz, pct, price, safeHref } from "../lib/format";
import { useLiveRefresh } from "../lib/liveRefresh";
import { ipoApi, type DocLink, type Facts, type IpoDetail, type Statement, type Summary } from "../lib/ipo";
import { badgeOf, bandText, clockText, croreText, expectedText, minText, partsText, sharesText, sizeText, spanText, timesText } from "../lib/ipoText";
import { Badge, Card, CardHead, DataTable, Disclosure, EmptyState, ErrorState, PageHeader, PlanNote, Signed, Skeleton, Stat, StatRow, type Column } from "../components/kit";
import { LockedPreview } from "../components/LockedPreview";
import { Info } from "../components/ui";
import "./ipo.css";

/* /invest/ipos/:id: one issue. Its dates, price band, lot and minimum, size (fresh issue and offer for sale), the bids by category
 * (refreshed while it is open), how it has traded since listing against the issue price, the facts read from its offer document
 * (promoters, selling shareholders, the objects, the last three years' revenue and profit), and the document's links: free for
 * everyone. The summary of the offer document (each statement with the words of the document it rests on) is on Basic. Facts
 * only, in the document's and the exchanges' own figures. */

function Dates({ d }: { d: IpoDetail }) {
  const r = d.ipo;
  if (r.market === "US") {
    return (
      <ul className="ipo-dates" data-testid="ipo-dates">
        {r.expected && <li><span className="k-note">Expected to price</span><b>{fmtDate(r.expected)}</b></li>}
        {r.priced && <li><span className="k-note">{r.stage === "listed" ? "First trading day" : "Priced; trading starts next session"}</span><b>{fmtDate(r.priced)}</b></li>}
        {r.filed && <li><span className="k-note">Filed with the SEC</span><b>{fmtDate(r.filed)}</b></li>}
      </ul>
    );
  }
  return (
    <>
      <ul className="ipo-dates" data-testid="ipo-dates">
        <li><span className="k-note">Bidding opens</span><b>{fmtDate(r.open)}</b></li>
        <li><span className="k-note">Bidding closes</span><b>{fmtDate(r.close)}</b>{r.close_time && <span className="k-note" data-testid="ipo-close-time">{clockText(r.close_time)} IST</span>}</li>
        <li><span className="k-note">Allotment</span><b>{expectedText(r.allotment, r.allotment_expected)}</b></li>
        <li><span className="k-note">Listing</span><b>{expectedText(r.listing, r.listing_expected)}</b></li>
      </ul>
      {r.hours && <p className="k-note" data-testid="ipo-hours">Bidding hours as the exchange states them: {r.hours.replace(/\.+$/, "")}.</p>}
      {(r.allotment_expected || r.listing_expected) && (
        <p className="k-note">"Expected" is the day SEBI's timetable gives: allotment the working day after bidding closes, listing three working days after. The exchange publishes the actual day.</p>
      )}
    </>
  );
}

function Terms({ d }: { d: IpoDetail }) {
  const r = d.ipo;
  const us = r.market === "US";
  return (
    <Card label="The issue" testId="ipo-terms" className="ipo-terms">
      <CardHead level={2} title="The issue" />
      <StatRow label="Terms of the issue">
        <Stat label={us ? "Price" : "Price band"} value={bandText(r)} note={us && r.stage === "upcoming" ? "range not final" : undefined} />
        {!us && <Stat label="Lot" value={r.lot ? `${sharesText(r.lot)} shares` : "–"} note={r.lot ? `minimum ${minText(r)}` : undefined} />}
        <Stat label="Issue size" value={sizeText(r)} note={r.size != null && r.size_parts ? `${partsText(r.size_parts)}, ${r.size_basis}` : r.size_basis && r.size_basis !== "stated" ? r.size_basis : undefined} />
        {us && r.shares != null && <Stat label="Shares offered" value={sharesText(r.shares, "US")} />}
      </StatRow>
      <dl className="ipo-facts">
        {!us && (r.fresh != null || r.fresh_cr != null) && <div><dt>Fresh issue</dt><dd>{r.fresh != null ? `${sharesText(r.fresh)} shares` : croreText(r.fresh_cr)}</dd></div>}
        {!us && (r.ofs != null || r.ofs_cr != null) && <div><dt>Offer for sale<Info label="About the offer for sale">The shares existing holders offer, as against new shares the company issues.</Info></dt><dd>{r.ofs != null ? `${sharesText(r.ofs)} shares` : croreText(r.ofs_cr)}</dd></div>}
        {!us && r.face_value != null && <div><dt>Face value</dt><dd>{price(r.face_value, "INR", 2)}</dd></div>}
        {!us && r.retail_max != null && <div><dt>Most a retail bid can be</dt><dd>{price(r.retail_max, "INR", 0)}</dd></div>}
        {r.issue_type && <div><dt>Issue type</dt><dd>{r.issue_type}</dd></div>}
        {r.exchanges && r.exchanges.length > 0 && <div><dt>Lists on</dt><dd>{r.exchanges.join(" and ")}{r.segment === "sme" ? " (SME platform)" : ""}</dd></div>}
        {us && r.exchange && <div><dt>Lists on</dt><dd>{r.exchange}</dd></div>}
        {r.industry && <div><dt>Industry</dt><dd>{r.industry}</dd></div>}
        {r.isin && <div><dt>ISIN</dt><dd>{r.isin}</dd></div>}
        {r.lead_managers && r.lead_managers.length > 0 && <div className="wide"><dt>Lead managers</dt><dd>{r.lead_managers.join(", ")}</dd></div>}
        {r.registrar && <div><dt>Registrar</dt><dd>{r.registrar}</dd></div>}
      </dl>
      <h3 className="k-sub">Dates</h3>
      <Dates d={d} />
    </Card>
  );
}

function Bids({ d }: { d: IpoDetail }) {
  const s = d.subscription;
  if (!s) {
    return d.ipo.market === "IN" && d.ipo.stage !== "listed" && d.ipo.stage !== "withdrawn" && d.ipo.stage !== "social" ? (
      <Card compact label="Bids received" testId="ipo-bids">
        {/* an issue only BSE lists has no NSE page here: said as that, not as "no bids" (RC2A-005: the one open SME issue read as having none) */}
        <p className="k-small k-muted" data-testid="ipo-no-bids">{d.ipo.stage === "upcoming" ? "Bidding has not opened. The bids received by category show here, refreshed through the day, once it does."
          : !d.ipo.symbol && d.ipo.exchanges?.length === 1 && d.ipo.exchanges[0] === "BSE" ? "This issue is listed on BSE only. Its bids are on BSE's own page for the issue; they are not read here yet, so none are shown."
          : "The exchange has no bids to show for this issue."}</p>
      </Card>
    ) : null;
  }
  const cols: Column<(typeof s.rows)[number]>[] = [
    { key: "c", header: "Category", rowHeader: true, wrap: true, cell: (r) => (r.sr === "total" ? <b>{r.label}</b> : r.label) },
    { key: "o", header: "Shares on offer", numeric: true, cell: (r) => sharesText(r.offered) },
    { key: "b", header: "Shares bid for", numeric: true, cell: (r) => sharesText(r.bid) },
    { key: "t", header: "Times", numeric: true, info: "Shares bid for divided by shares on offer in the category.", cell: (r) => (r.times != null ? timesText(r.times).replace(" times", "×") : "–") },
  ];
  return (
    <Card label="Bids received" testId="ipo-bids">
      <CardHead level={2} title="Bids received" info="By category, over both exchanges, as the exchange publishes them. While the issue is open the figures move through the day; the final ones are published after the close."
        infoLabel="About the bids" actions={d.subscription?.live ? <Badge tone="live">Live</Badge> : undefined} />
      <StatRow label="Bids received in total"><Stat label="Whole issue" value={timesText(s.times)} note={s.as_of ? `as of ${asOf(s.as_of.replace(" ", "T") + ":00+05:30", { tz: marketTz("IN") })}` : undefined} /></StatRow>
      <DataTable stack label="Bids received by category" rows={s.rows} rowKey={(r) => r.sr} columns={cols} />
      {d.ipo.segment === "sme" && <p className="k-note">An SME issue's exchange page gives the bids per category without the shares reserved for each, so only the whole issue has a count of times.</p>}
    </Card>
  );
}

function Listing({ d }: { d: IpoDetail }) {
  const p = d.perf;
  const r = d.ipo;
  if (r.stage !== "listed" || !p) return null;
  const chg = (v: number | null | undefined) => (v == null ? "–" : <Signed value={v} fmt={(x) => pct(x, 1)} />);
  return (
    <Card label="Since listing" testId="ipo-listing">
      <CardHead level={2} title="Since listing" info={p.basis === "exchange"
        ? "From the exchange's own table of how its listed issues have traded: the first day's close and the latest price against the issue price."
        : "The listing price is the first session's opening price; the latest is the latest daily close. Each against the issue price."} infoLabel="About these prices" />
      <StatRow label="Trading against the issue price">
        <Stat label="Issue price" value={price(p.issue_price, r.currency, 2)} />
        {p.listing_price != null && <Stat label="Listing price" value={price(p.listing_price, r.currency, 2)} note={chg(p.listing_change_pct)} />}
        <Stat label="First day's close" value={price(p.day_close, r.currency, 2)} note={chg(p.day_change_pct)} />
        <Stat label={p.latest_date ? `Close on ${fmtDate(p.latest_date, { year: false })}` : "Latest"} value={price(p.latest, r.currency, 2)} note={chg(p.change_pct)} />
      </StatRow>
      <p className="k-small">{r.company_link ? <Link className="link" to={r.company_link}>Open {r.name}'s company page</Link> : null}
        {r.company_link ? ": its day one, charts, results and filings." : null}</p>
    </Card>
  );
}

function FromTheDocument({ f, d }: { f: Facts; d: IpoDetail }) {
  const r = d.ipo;
  const kind = f.kind ?? "offer document";
  const there = (page?: number) => (page ? ` Page ${page} of the PDF.` : "");
  if (f.state === "none") {
    return <Card compact label="From the offer document" testId="ipo-facts"><p className="k-small k-muted">No offer document has been found for this issue yet. {r.market === "IN" ? "The draft and red herring prospectuses filed with SEBI are listed under Documents once they are." : "The registration statement and prospectus filed with the SEC are listed under Documents once they are."}</p></Card>;
  }
  if (f.state === "pending") {
    return <Card compact label="From the offer document" testId="ipo-facts"><p className="k-small k-muted">The {kind} is read automatically a few at a time. What it says about the promoters, the objects and the figures shows here once it has been. Open it under Documents meanwhile.</p></Card>;
  }
  const fin = f.financials;
  // what the summary below already says, with the words it rests on, is not said twice (RC2A-007)
  const said = d.summary.state === "ready" ? d.summary.items : undefined;
  const hide = { promoters: !!said?.promoters?.length, objects: !!said?.objects?.length };
  return (
    <Card label="From the offer document" testId="ipo-facts">
      <CardHead level={2} title="From the offer document" info={`Read by fixed rules from the places the ${kind} always puts these, each with the page it is on. A fact the rules can't find is left out, not guessed. Open the document for everything else.`} infoLabel="About these facts" />
      {r.market === "IN" ? (
        <dl className="ipo-facts">
          {f.promoters && f.promoters.length > 0 && !hide.promoters && <div className="wide"><dt>Promoters</dt><dd data-testid="ipo-promoters">{f.promoters.join(", ")}</dd></div>}
          {f.selling && f.selling.length > 0 && <div className="wide"><dt>Selling shareholders (offer for sale)</dt><dd data-testid="ipo-selling">{f.selling.map((s) => `${s.name} (${s.kind.toLowerCase()})`).join(", ")}</dd></div>}
          {f.objects && !hide.objects && (
            <div className="wide"><dt>What the money is for</dt>
              <dd data-testid="ipo-objects">{f.objects.text}
                {f.objects.table && (
                  <ol className="ipo-money" data-testid="ipo-money-table">
                    {f.objects.table.rows.map((x, i) => <li key={i}>{x.label}{x.figures ? <span className="k-note"> {x.figures}{f.objects?.table?.unit ? ` (${f.objects.table.unit})` : ""}</span> : null}</li>)}
                  </ol>
                )}
                <span className="k-note"> The document's words.{there(f.objects.page)}</span></dd>
            </div>
          )}
        </dl>
      ) : (
        <dl className="ipo-facts">
          {f.us?.company_shares != null && <div><dt>Shares offered by the company</dt><dd>{sharesText(f.us.company_shares, "US")}</dd></div>}
          {f.us?.selling_shares != null && <div><dt>Shares offered by selling stockholders</dt><dd>{sharesText(f.us.selling_shares, "US")}</dd></div>}
          {f.us?.price != null && <div><dt>Offer price</dt><dd>{price(f.us.price, "USD", 2)}</dd></div>}
          {f.us?.range && <div><dt>Price range on the cover</dt><dd>{price(f.us.range[0], "USD", 2)} to {price(f.us.range[1], "USD", 2)}</dd></div>}
          {f.us?.listing && <div><dt>Listing</dt><dd>{f.us.listing}{f.us.symbol ? `, symbol ${f.us.symbol}` : ""}</dd></div>}
          {f.us?.proceeds && <div className="wide"><dt>Use of proceeds</dt><dd data-testid="ipo-proceeds">{f.us.proceeds}<span className="k-note"> The document's words.</span></dd></div>}
        </dl>
      )}
      {r.market === "IN" && !f.promoters?.length && !f.objects && !fin && <p className="k-small k-muted">The rules couldn't read the cover or the summary tables of this document. Open it under Documents.</p>}
      {fin && (
        <>
          <h3 className="k-sub">Revenue and profit, last three years</h3>
          <DataTable stack label="Revenue and profit from the offer document" rows={fin.rows} rowKey={(x) => x.key} columns={[
            { key: "l", header: `${fin.unit}`, rowHeader: true, cell: (x) => x.label },
            ...fin.years.map((y, i): Column<(typeof fin.rows)[number]> => ({ key: y, header: y, numeric: true, cell: (x) => (x.values[i] == null ? "–" : x.key === "profit" ? <Signed value={x.values[i]} fmt={croreText} /> : croreText(x.values[i])) })),
          ]} />
          <p className="k-note">From the restated summary financial information of the {kind}.{there(fin.page)} Year ends as the document gives them.</p>
        </>
      )}
    </Card>
  );
}

function Statements({ title, rows, id }: { title: string; rows: Statement[]; id: string }) {
  if (!rows.length) return null;
  return (
    <div data-testid={`ipo-sum-${id}`}>
      <h3 className="k-sub">{title}</h3>
      {rows.map((s, i) => (
        <div key={i} className="ipo-statement">
          <p className="k-small">{s.text}</p>
          <Disclosure summary="The document's words"><blockquote className="ipo-quote">“{s.quote}”</blockquote></Disclosure>
        </div>
      ))}
    </div>
  );
}

function SummaryCard({ d, sum, onWrite, busy, error }: { d: IpoDetail; sum: Summary; onWrite: () => void; busy: boolean; error: string | null }) {
  const kind = sum.kind ?? "offer document";
  if (sum.state === "locked") {
    return (
      <Card label="Summary of the offer document" testId="ipo-summary">
        <CardHead level={2} title="Summary of the offer document" />
        <PlanNote plan="basic">The summary of the offer document is on the {sum.plan} plan. The facts above and the document itself stay free.</PlanNote>
        <LockedPreview title="the summary" actions={false} points={[
          "What the company does and where its money comes from.",
          "Its revenue and profit for the periods the document gives, as written there.",
          "What the money raised is for, and who gets the money from shares existing holders offer.",
          "The risk factors the document puts first, one sentence each.",
          "Who the promoters are. Every statement comes with the words of the document it rests on.",
        ]} />
      </Card>
    );
  }
  const items = sum.items;
  return (
    <Card label="Summary of the offer document" testId="ipo-summary">
      <CardHead level={2} title="Summary of the offer document" info={`Written once from the passages of the ${kind} and kept for everyone. A statement stays only when the words it quotes are really in the document and every figure in it is in those words. It is not advice: open the document for the whole.`} infoLabel="About this summary" />
      {sum.state === "ready" && items ? (
        <>
          {items.business && <div data-testid="ipo-sum-business"><h3 className="k-sub">The business</h3>
            <div className="ipo-statement"><p className="k-small">{items.business.text}</p><Disclosure summary="The document's words"><blockquote className="ipo-quote">“{items.business.quote}”</blockquote></Disclosure></div></div>}
          <Statements id="financials" title="Figures" rows={items.financials} />
          <Statements id="objects" title="What the money is for" rows={items.objects} />
          <Statements id="risks" title="Risk factors the document puts first" rows={items.risks} />
          <Statements id="promoters" title="Promoters" rows={items.promoters} />
          <p className="k-note">Written {sum.at ? asOf(sum.at) : ""} from the {kind}. Facts the document states, not a view on the issue.</p>
        </>
      ) : sum.state === "none" ? (
        <p className="k-small k-muted">No offer document has been found for this issue yet, so there is nothing to summarise.</p>
      ) : sum.state === "problem" ? (
        <p className="k-small k-muted">{sum.message ?? "The document couldn't be summarised."}</p>
      ) : (
        <EmptyState title="The summary isn't written yet" action={{ label: busy ? "Reading the document…" : "Write it now", onClick: onWrite }}>
          It is written automatically, a few documents at a time. Reading a long offer document takes a minute or two.
        </EmptyState>
      )}
      {error && <p className="k-small k-down" role="alert">{error}</p>}
      {d.ipo.market === "IN" && sum.state === "ready" && <p className="k-note">Figures are the document's own units (₹ million or ₹ crore, as it writes them).</p>}
    </Card>
  );
}

function Documents({ docs, d }: { docs: DocLink[]; d: IpoDetail }) {
  return (
    <Card label="Documents" testId="ipo-docs">
      <CardHead level={2} title="Documents" info={d.ipo.market === "IN" ? "The draft and red herring prospectuses filed with SEBI, and the exchange's copy of the red herring prospectus (a ZIP)." : "The registration statement, its amendments and the final prospectus filed with the SEC."} infoLabel="About these documents" />
      {docs.length ? (
        <ul className="k-list plain ipo-docs">
          {docs.map((x) => (
            <li key={x.url}><a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">{x.label} ↗</a>
              <span className="k-note"> {[x.source, x.date ? fmtDate(x.date) : null].filter(Boolean).join(" · ")}</span></li>
          ))}
        </ul>
      ) : <p className="k-small k-muted">No offer document found yet.</p>}
      <p className="k-note">{d.note}</p>
    </Card>
  );
}

export function IpoPage() {
  const { id = "" } = useParams();
  const { fail } = useApp();
  const [d, setD] = useState<IpoDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [writeError, setWriteError] = useState<string | null>(null);
  const load = useCallback((quiet = false) => {
    if (!quiet) { setD(null); setError(null); }
    ipoApi.one(id).then(setD).catch((e) => !quiet && setError(e instanceof ApiError ? e.message : "This IPO couldn't be read just now."));
  }, [id]);
  useEffect(() => { load(); }, [load]);
  useLiveRefresh(d?.ipo.stage === "open", () => load(true), 120_000);
  const write = async () => {
    setBusy(true); setWriteError(null);
    try {
      const got = await ipoApi.summary(id);
      setD((cur) => (cur ? { ...cur, facts: got.facts, summary: got.summary } : cur));
    } catch (e) {
      if (e instanceof ApiError && (e.status === 429 || e.status === 503)) setWriteError(e.message);
      else fail(e);
    } finally { setBusy(false); }
  };

  const r = d?.ipo;
  const badge = r ? badgeOf(r) : null;
  return (
    <div className="k-page ipo-page">
      <PageHeader eyebrow={eyebrowOf("/invest/ipos")} title={r?.name ?? "IPO"}
        lede={r ? <>{r.market === "IN" ? `${r.segment === "sme" ? "SME" : "Main board"} issue` : "US offering"}{r.symbol ? ` · ${r.symbol}` : ""}{r.open && r.close ? ` · bidding ${spanText(r.open, r.close)}` : r.priced ? ` · ${r.stage === "listed" ? "trading from" : "priced for"} ${fmtDate(r.priced)}` : r.expected ? ` · expected to price ${fmtDate(r.expected)}` : ""}</> : undefined}
        actions={badge ? <Badge tone={badge.tone}>{badge.word}</Badge> : undefined} />
      <p className="k-small"><Link className="link" to={`/invest/ipos?m=${r?.market ?? "IN"}`}>← All IPOs</Link></p>
      {error ? <ErrorState title="This IPO couldn't be read" action={{ label: "Try again", onClick: () => load() }}>{error}</ErrorState>
        : !d ? <Card><Skeleton label="Reading the issue" lines={5} /></Card> : (
        <>
          {d.ipo.stage === "withdrawn" && <p className="k-callout k-small" role="status" data-testid="ipo-not-gone-ahead">The exchange lists this issue as {(d.ipo.issue_status ?? "withdrawn")}. The dates and price band below are the ones announced before; no bidding, allotment or listing follows from them.</p>}
          {d.ipo.stage === "social" && <p className="k-callout k-small" role="status" data-testid="ipo-social-note">This is a fund raise on the Social Stock Exchange, not an IPO of shares. It is listed here only because the exchange lists it beside the IPOs.</p>}
          <Terms d={d} />
          <Bids d={d} />
          <Listing d={d} />
          <FromTheDocument f={d.facts} d={d} />
          <SummaryCard d={d} sum={d.summary} onWrite={write} busy={busy} error={writeError} />
          <Documents docs={d.documents} d={d} />
          <p className="k-small">Alerts for when an issue opens, closes, is allotted or lists are set on the <Link className="link" to={`/invest/ipos?m=${d.ipo.market}`}>IPOs page</Link>.</p>
        </>
      )}
    </div>
  );
}

export default IpoPage;
