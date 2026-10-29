import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { eyebrowOf } from "../lib/eyebrow";
import { asOf, fmtDate, marketTz, pct, price, safeHref } from "../lib/format";
import { useLiveRefresh } from "../lib/liveRefresh";
import { ipoApi, type DocLink, type Facts, type IpoDetail, type Summary } from "../lib/ipo";
import {
  KPI_LABELS, badgeOf, bandText, clockText, croreText, expectedText, figure, firstAndRest, freshCrore, growthPct, kpiText, minText, objectRows, partsText, periodText,
  priceToEarnings, sharesText, sizeText, spanText, timesText, yearKey,
} from "../lib/ipoText";
import { Badge, Card, CardHead, DataTable, Disclosure, EmptyState, ErrorState, PageHeader, PlanNote, Signed, Skeleton, type Column } from "../components/kit";
import { LockedPreview } from "../components/LockedPreview";
import "./ipo.css";

/* /invest/ipos/:id: one issue, a table for every block (O7). The issue's terms and dates, the bids by category (refreshed while it
 * is open), how it has traded since listing against the issue price, and what the offer document says, read by fixed rules and each
 * with its page: the money's use with amounts, the risks the document puts first, the last years' revenue and profit with their
 * change, its key indicators beside its listed peers', who holds the shares before the offer, and the price to earnings against the
 * peers' at the top of the band. All free for everyone. The AI summary (Basic) is the business and how its revenue splits, each
 * statement with the document's words behind one fold. Facts only, in the document's and the exchanges' own figures. */

type Line = { id: string; k: ReactNode; v: ReactNode; n?: ReactNode };

/** A block of "item, figure, note" rows: the issue's terms, its dates, a US offering's facts. */
function LineTable({ label, rows, noteHead = "Note" }: { label: string; rows: Line[]; noteHead?: string }) {
  const notes = rows.some((r) => r.n);
  const cols: Column<Line>[] = [
    { key: "k", header: "Item", rowHeader: true, wrap: true, cell: (r) => r.k },
    { key: "v", header: "Figure", wrap: true, cell: (r) => r.v },
    ...(notes ? [{ key: "n", header: noteHead, wrap: true, cell: (r: Line) => (r.n ? <span className="k-note">{r.n}</span> : "") } as Column<Line>] : []),
  ];
  return <DataTable label={label} rows={rows} rowKey={(r) => r.id} columns={cols} />;
}

function Terms({ d }: { d: IpoDetail }) {
  const r = d.ipo;
  const us = r.market === "US";
  const rows: (Line | null)[] = [
    { id: "band", k: us ? "Price" : r.stage === "listed" && r.price != null ? "Issue price" : "Price band", v: bandText(r), n: us && r.stage === "upcoming" ? "The range is not final." : undefined },
    !us ? { id: "lot", k: "Lot", v: r.lot ? `${sharesText(r.lot)} shares` : "–", n: r.lot ? `Minimum bid ${minText(r)}` : undefined } : null,
    {
      id: "size", k: "Issue size", v: sizeText(r),
      n: [r.size != null && r.size_parts ? `${partsText(r.size_parts)}, ${r.size_basis}` : r.size_basis && r.size_basis !== "stated" ? r.size_basis : null,
        r.size_in_bids != null ? `The exchange's bid table covers ${croreText(r.size_in_bids)}; the rest is the anchor portion${r.anchor_shares ? ` (${sharesText(r.anchor_shares)} shares)` : ""}.` : null,
      ].filter(Boolean).join(". ") || undefined,
    },
    us && r.shares != null ? { id: "shares", k: "Shares offered", v: sharesText(r.shares, "US") } : null,
    !us && (r.fresh != null || r.fresh_cr != null) ? { id: "fresh", k: "Fresh issue", v: r.fresh != null ? `${sharesText(r.fresh)} shares` : croreText(r.fresh_cr), n: "New shares the company issues." } : null,
    !us && (r.ofs != null || r.ofs_cr != null) ? { id: "ofs", k: "Offer for sale", v: r.ofs != null ? `${sharesText(r.ofs)} shares` : croreText(r.ofs_cr), n: "Shares existing holders offer, as against new shares the company issues." } : null,
    !us && r.face_value != null ? { id: "face", k: "Face value", v: price(r.face_value, "INR", 2) } : null,
    !us && r.retail_max != null ? { id: "retail", k: "Most a retail bid can be", v: price(r.retail_max, "INR", 0) } : null,
    r.issue_type ? { id: "type", k: "Issue type", v: r.issue_type } : null,
    r.exchanges && r.exchanges.length > 0 ? { id: "lists", k: "Lists on", v: `${r.exchanges.join(" and ")}${r.segment === "sme" ? " (SME platform)" : ""}` } : null,
    us && r.exchange ? { id: "xch", k: "Lists on", v: r.exchange } : null,
    r.industry ? { id: "ind", k: "Industry", v: r.industry } : null,
    r.isin ? { id: "isin", k: "ISIN", v: r.isin } : null,
    r.lead_managers && r.lead_managers.length > 0 ? { id: "lm", k: "Lead managers", v: r.lead_managers.join(", ") } : null,
    r.registrar ? { id: "reg", k: "Registrar", v: r.registrar } : null,
  ];
  return (
    <Card label="The issue" testId="ipo-terms" className="ipo-terms">
      <CardHead level={2} title="The issue" />
      <LineTable label="The terms of the issue" rows={rows.filter((x): x is Line => !!x)} />
      <h3 className="k-sub">Dates</h3>
      <Dates d={d} />
    </Card>
  );
}

function Dates({ d }: { d: IpoDetail }) {
  const r = d.ipo;
  const tt = "SEBI's timetable";
  let rows: Line[];
  if (r.market === "US") {
    const us: (Line | null)[] = [
      r.filed ? { id: "filed", k: "Filed with the SEC", v: fmtDate(r.filed) } : null,
      r.expected ? { id: "exp", k: "Expected to price", v: fmtDate(r.expected) } : null,
      r.priced ? { id: "priced", k: r.stage === "listed" ? "First trading day" : "Priced", v: fmtDate(r.priced), n: r.stage === "listed" ? undefined : "Trading starts next session." } : null,
    ];
    rows = us.filter((x): x is Line => !!x);
  } else {
    const inr: (Line | null)[] = [
      { id: "open", k: "Bidding opens", v: fmtDate(r.open) },
      { id: "close", k: "Bidding closes", v: <span data-testid="ipo-close-time-row">{fmtDate(r.close)}</span>, n: r.close_time ? <span data-testid="ipo-close-time">{clockText(r.close_time)} IST</span> : undefined },
      { id: "allot", k: "Allotment", v: expectedText(r.allotment, r.allotment_expected), n: r.allotment_expected ? `${tt}: the working day after bidding closes. The exchange publishes the actual day.` : undefined },
      r.credit ? { id: "credit", k: "Money unblocked or refunded, shares credited", v: `${fmtDate(r.credit)} (expected)`, n: `${tt}: two working days after bidding closes.` } : null,
      { id: "list", k: "Listing", v: expectedText(r.listing, r.listing_expected), n: r.listing_expected ? `${tt}: three working days after bidding closes. The exchange publishes the actual day.` : undefined },
    ];
    rows = inr.filter((x): x is Line => !!x);
  }
  return (
    <>
      <div data-testid="ipo-dates"><LineTable label="The dates of the issue" rows={rows} noteHead="Rule" /></div>
      {r.hours && <p className="k-note" data-testid="ipo-hours">Bidding hours as the exchange states them: {r.hours.replace(/\.+$/, "")}.</p>}
    </>
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
  const rows = s.rows.some((r) => r.sr === "total") ? s.rows : [...s.rows, { label: "Whole issue", sr: "total", offered: null, bid: null, times: s.times }];
  const cols: Column<(typeof s.rows)[number]>[] = [
    { key: "c", header: "Category", rowHeader: true, wrap: true, cell: (r) => (r.sr === "total" ? <b>{r.label}</b> : r.label) },
    { key: "o", header: "Shares on offer", numeric: true, cell: (r) => sharesText(r.offered) },
    { key: "b", header: "Shares bid for", numeric: true, cell: (r) => sharesText(r.bid) },
    { key: "t", header: "Times", numeric: true, info: "Shares bid for divided by shares on offer in the category.", cell: (r) => (r.times != null ? timesText(r.times).replace(" times", "×") : "–") },
  ];
  const at = s.as_of ? asOf(s.as_of.replace(" ", "T") + ":00+05:30", { tz: marketTz("IN") }) : null;
  return (
    <Card label="Bids received" testId="ipo-bids">
      <CardHead level={2} title="Bids received" info="By category, over both exchanges, as the exchange publishes them. While the issue is open the figures move through the day; the final ones are published after the close."
        infoLabel="About the bids" actions={d.subscription?.live ? <Badge tone="live">Live</Badge> : undefined} />
      <DataTable stack label="Bids received by category" rows={rows} rowKey={(r) => r.sr} columns={cols} />
      <p className="k-note" data-testid="ipo-bids-asof">Whole issue {timesText(s.times)}{at ? `, as of ${at}` : ""}.</p>
      {d.ipo.segment === "sme" && <p className="k-note">An SME issue's exchange page gives the bids per category without the shares reserved for each, so only the whole issue has a count of times.</p>}
    </Card>
  );
}

function Listing({ d }: { d: IpoDetail }) {
  const p = d.perf;
  const r = d.ipo;
  if (r.stage !== "listed" || !p) return null;
  const chg = (v: number | null | undefined) => (v == null ? "–" : <Signed value={v} fmt={(x) => pct(x, 1)} />);
  type Row = { id: string; k: string; v: number | null | undefined; c: number | null | undefined };
  const rows: Row[] = [
    { id: "issue", k: "Issue price", v: p.issue_price, c: undefined },
    ...(p.listing_price != null ? [{ id: "list", k: "Listing price", v: p.listing_price, c: p.listing_change_pct }] : []),
    { id: "day", k: "First day's close", v: p.day_close, c: p.day_change_pct },
    { id: "now", k: p.latest_date ? `Close on ${fmtDate(p.latest_date, { year: false })}` : "Latest", v: p.latest, c: p.change_pct },
  ];
  return (
    <Card label="After listing" testId="ipo-listing">
      <CardHead level={2} title="After listing" info={p.basis === "exchange"
        ? "From the exchange's own table of how its listed issues have traded: the first day's close and the latest price against the issue price."
        : "The listing price is the first session's opening price; the latest is the latest daily close. Each against the issue price."} infoLabel="About these prices" />
      <DataTable label="Trading against the issue price" rows={rows} rowKey={(x) => x.id} columns={[
        { key: "k", header: "Item", rowHeader: true, cell: (x) => x.k },
        { key: "v", header: "Price", numeric: true, cell: (x) => price(x.v, r.currency, 2) },
        { key: "c", header: "Against the issue price", numeric: true, cell: (x) => (x.id === "issue" ? "–" : chg(x.c)) },
      ]} />
      <p className="k-small">{r.company_link ? <Link className="link" to={r.company_link}>Open {r.name}'s company page</Link> : null}
        {r.company_link ? ": its day one, charts, results and filings." : null}</p>
    </Card>
  );
}

const pageOf = (page?: number) => (page ? `Page ${page} of the PDF.` : "");

/** What the money is for: each object with its amount in ₹ crore and its share of the fresh issue, as the document gives them. */
function Objects({ f, d }: { f: Facts; d: IpoDetail }) {
  const u = f.utilisation;
  if (!u && !f.objects) return null;
  const fresh = freshCrore(d.ipo);
  const rows = u ? objectRows(u.rows, fresh) : [];
  return (
    <Card label="What the money is for" testId="ipo-objects">
      <CardHead level={2} title="What the money is for" info="The objects of the fresh issue as the offer document lists them, with the amount it gives each. A share is the amount over the fresh issue's size." infoLabel="About the objects" />
      {u ? (
        <>
          <DataTable stack label="Objects of the issue" rows={rows} rowKey={(x) => String(x.n)} columns={[
            { key: "n", header: "#", numeric: true, cell: (x) => x.n },
            { key: "l", header: "Object", rowHeader: true, wrap: true, cell: (x) => x.label },
            { key: "a", header: "Amount (₹ crore)", numeric: true, cell: (x) => (x.amount == null ? <span className="k-muted">Not given</span> : figure(x.amount)) },
            { key: "s", header: "Share of the fresh issue", numeric: true, cell: (x) => (x.share == null ? "–" : `${figure(x.share, 1)}%`) },
          ]} foot={rows.some((x) => x.amount != null) ? { n: "", l: "Amounts given", a: figure(rows.reduce((t, x) => t + (x.amount ?? 0), 0)), s: fresh ? `${figure((rows.reduce((t, x) => t + (x.amount ?? 0), 0) / fresh) * 100, 1)}%` : "–" } : undefined} />
          <p className="k-note">{fresh ? `Fresh issue ${croreText(fresh)}. ` : ""}An object with no amount is one the document gives none for at this stage (usually general corporate purposes, which it sizes after the price is set). {pageOf(u.page)}</p>
        </>
      ) : f.objects && (
        <div data-testid="ipo-objects-text">
          <p className="k-small">{f.objects.text}</p>
          {f.objects.table && (
            <DataTable label="Objects of the issue" rows={f.objects.table.rows} rowKey={(_x, i) => String(i)} columns={[
              { key: "l", header: "Object", rowHeader: true, wrap: true, cell: (x) => x.label },
              { key: "a", header: f.objects?.table?.unit ? `Amount (${f.objects.table.unit})` : "Amount", numeric: true, cell: (x) => x.figures ?? "–" },
            ]} />
          )}
          <p className="k-note">The document's words. {pageOf(f.objects.page)}</p>
        </div>
      )}
    </Card>
  );
}

/** Promoters and the selling shareholders: one table, with who offers shares in this issue. */
function Owners({ f }: { f: Facts }) {
  const promoters = f.promoters ?? [];
  const selling = f.selling ?? [];
  const sells = new Set(selling.map((s) => s.name.toLowerCase()));
  type Row = { id: string; name: string; role: string; sells: boolean };
  const rows: Row[] = [
    ...promoters.map((n, i) => ({ id: `p${i}`, name: n, role: "Promoter", sells: sells.has(n.toLowerCase()) })),
    ...selling.filter((s) => !promoters.some((n) => n.toLowerCase() === s.name.toLowerCase())).map((s, i) => ({ id: `s${i}`, name: s.name, role: s.kind, sells: true })),
  ];
  if (!rows.length) return null;
  return (
    <Card label="Promoters and selling shareholders" testId="ipo-promoters">
      <CardHead level={2} title="Promoters and selling shareholders" info="The promoters are read from the offer document's cover; the selling shareholders from its table of the offer for sale. A holder who sells puts existing shares up in this issue." infoLabel="About these names" />
      <DataTable stack label="Promoters and selling shareholders" rows={rows} rowKey={(x) => x.id} columns={[
        { key: "n", header: "Name", rowHeader: true, wrap: true, cell: (x) => x.name },
        { key: "r", header: "Role", cell: (x) => x.role },
        { key: "s", header: "Sells shares in this issue", cell: (x) => (x.sells ? "Yes" : selling.length ? "No" : "–") },
      ]} />
      {selling.length === 0 && <p className="k-note" data-testid="ipo-selling">No shareholder sells in this issue: it is a fresh issue only, as far as the document's table shows.</p>}
    </Card>
  );
}

function Holding({ f }: { f: Facts }) {
  const h = f.holding;
  if (!h?.rows.length) return null;
  const post = h.rows.some((x) => x.post_pct != null);
  return (
    <Card label="Who holds the shares before the offer" testId="ipo-holding">
      <CardHead level={2} title="Who holds the shares before the offer" info="The document's table of the shareholding of the promoters, the promoter group and other holders before the issue." infoLabel="About this table" />
      <DataTable stack label="Shareholding before the offer" rows={h.rows} rowKey={(_x, i) => `${i}`} columns={[
        { key: "n", header: "Holder", rowHeader: true, wrap: true, cell: (x) => (x.total ? <b>{x.name}</b> : <>{x.name}<span className="k-sub-line">{x.group}</span></>) },
        { key: "s", header: "Shares", numeric: true, cell: (x) => sharesText(x.shares) },
        { key: "p", header: "Share of the company", numeric: true, cell: (x) => (x.pct == null ? "–" : `${figure(x.pct)}%`) },
        ...(post ? [{ key: "q", header: "After the offer", numeric: true, cell: (x: (typeof h.rows)[number]) => (x.post_pct == null ? "–" : `${figure(x.post_pct)}%`) } as Column<(typeof h.rows)[number]>] : []),
      ]} />
      <p className="k-note">As at the date the document gives. {pageOf(h.page)}</p>
    </Card>
  );
}

function Financials({ f, kind }: { f: Facts; kind: string }) {
  const fin = f.financials;
  if (!fin) return null;
  const eps = new Map((f.eps?.rows ?? []).map((x) => [yearKey(x.period), x.basic] as const));
  const epsRow = fin.years.some((y) => eps.get(yearKey(y)) != null) ? { key: "eps", label: "Earnings per share, basic (₹)", values: fin.years.map((y) => eps.get(yearKey(y)) ?? null) } : null;
  const rows = [...fin.rows, ...(epsRow ? [epsRow] : [])];
  return (
    <Card label="Revenue and profit" testId="ipo-financials">
      <CardHead level={2} title="Revenue and profit" info={`From the restated summary financial information of the ${kind}. The change is the latest year against the one before; none is given where the year before was a loss.`} infoLabel="About these figures" />
      <DataTable stack label="Revenue and profit from the offer document" rows={rows} rowKey={(x) => x.key} columns={[
        { key: "l", header: fin.unit, rowHeader: true, wrap: true, cell: (x) => x.label },
        ...fin.years.map((y, i): Column<(typeof rows)[number]> => ({ key: y, header: y, numeric: true, cell: (x) => (x.values[i] == null ? "–" : x.key === "profit" ? <Signed value={x.values[i]} fmt={croreText} /> : x.key === "eps" ? <Signed value={x.values[i]} fmt={(v) => figure(v)} /> : croreText(x.values[i])) })),
        { key: "g", header: "Latest year's change", numeric: true, cell: (x) => { const g = growthPct(x.values[0], x.values[1]); return g == null ? "–" : <Signed value={g} fmt={(v) => pct(v, 1)} />; } },
      ]} />
      <p className="k-note">Year ends as the document gives them. {pageOf(fin.page)}</p>
    </Card>
  );
}

function Indicators({ f }: { f: Facts }) {
  const k = f.kpis;
  if (!k) return null;
  const rows = KPI_LABELS.filter((l) => k.periods.some((p) => p.values[l.key] != null));
  const fiscal = k.periods.find((p) => /^fiscal|^(fy|financial year)/i.test(p.label) && KPI_LABELS.some((l) => p.peers[l.key]?.some((v) => v != null)));
  const peerRows = fiscal ? KPI_LABELS.filter((l) => fiscal.values[l.key] != null && fiscal.peers[l.key]?.some((v) => v != null)) : [];
  return (
    <>
      <Card label="Key indicators" testId="ipo-kpis">
        <CardHead level={2} title="Key indicators" info="The document's table of the key performance indicators, as it gives them for each period. Amounts in ₹ crore; margins and returns in percent." infoLabel="About the indicators" />
        <DataTable grid label="Key indicators by period" rows={rows} rowKey={(x) => x.key} columns={[
          { key: "l", header: "Indicator", rowHeader: true, wrap: true, cell: (x) => x.label },
          ...k.periods.map((p, i): Column<(typeof rows)[number]> => ({ key: `p${i}`, header: periodText(p.label), numeric: true, cell: (x) => kpiText(p.values[x.key], x.unit) })),
        ]} />
        <p className="k-note">{pageOf(k.page)}</p>
      </Card>
      {fiscal && peerRows.length > 0 && (
        <Card label="Key indicators beside listed peers" testId="ipo-peer-kpis">
          <CardHead level={2} title={`Beside its listed peers, ${periodText(fiscal.label)}`} info="The same indicators for the listed companies the document names as its peers, for the same period. A blank is one the document does not give." infoLabel="About the peers" />
          <DataTable stack label="Key indicators beside listed peers" rows={peerRows} rowKey={(x) => x.key} columns={[
            { key: "l", header: "Indicator", rowHeader: true, wrap: true, cell: (x) => x.label },
            { key: "c", header: "This company", numeric: true, cell: (x) => kpiText(fiscal.values[x.key], x.unit) },
            ...k.peers.map((n, i): Column<(typeof peerRows)[number]> => ({ key: `n${i}`, header: n, numeric: true, cell: (x) => kpiText(fiscal.peers[x.key]?.[i], x.unit) })),
          ]} />
        </Card>
      )}
    </>
  );
}

function Valuation({ f, d }: { f: Facts; d: IpoDetail }) {
  const t = f.peers;
  if (!t?.peers.length) return null;
  const r = d.ipo;
  const top = r.price ?? r.high ?? null;
  const eps = t.company.eps ?? f.eps?.rows[0]?.basic ?? null;
  const pe = priceToEarnings(top, eps);
  type Row = { name: string; price: number | null; revenue: number | null | undefined; eps: number | null | undefined; nav: number | null | undefined; pe: number | null; ronw: number | null | undefined; own?: boolean };
  const rows: Row[] = [
    { name: r.name, price: top, revenue: t.company.revenue, eps, nav: t.company.nav, pe, ronw: t.company.ronw, own: true },
    ...t.peers.map((p) => ({ ...p })),
  ];
  return (
    <Card label="Price against listed peers" testId="ipo-peers">
      <CardHead level={2} title="Price against listed peers" info="The document's table of the listed companies it compares this one with. The peers' prices are as at the date the document gives. This company's row is the top of its price band over its earnings per share for the last year the document gives." infoLabel="About this comparison" />
      <DataTable stack label="Price to earnings against listed peers" rows={rows} rowKey={(x) => x.name} columns={[
        { key: "n", header: "Company", rowHeader: true, wrap: true, cell: (x) => (x.own ? <><b>{x.name}</b><span className="k-sub-line">at the {r.price != null ? "issue price" : "top of the price band"}</span></> : x.name) },
        { key: "p", header: "Price (₹)", numeric: true, cell: (x) => figure(x.price) },
        { key: "r", header: "Revenue (₹ crore)", numeric: true, cell: (x) => figure(x.revenue) },
        { key: "e", header: "Earnings per share (₹)", numeric: true, cell: (x) => figure(x.eps) },
        { key: "v", header: "Book value per share (₹)", numeric: true, cell: (x) => figure(x.nav) },
        { key: "pe", header: "Price to earnings", numeric: true, cell: (x) => (x.pe == null ? "–" : `${figure(x.pe, 1)}×`) },
        { key: "ro", header: "Return on net worth", numeric: true, cell: (x) => (x.ronw == null ? "–" : `${figure(x.ronw)}%`) },
      ]} />
      <p className="k-note">{t.price_on ? `Peers' prices as on ${t.price_on}. ` : ""}{pageOf(t.page)}</p>
    </Card>
  );
}

/** The risks the offer document puts first, each with its page: the first few, then one fold for the rest. */
function Risks({ f }: { f: Facts }) {
  const risks = f.risks ?? [];
  if (!risks.length) return null;
  const [head, rest] = firstAndRest(risks, 5);
  const table = (rows: typeof risks, label: string) => (
    <DataTable stack label={label} rows={rows} rowKey={(x) => String(x.n)} columns={[
      { key: "n", header: "#", numeric: true, cell: (x) => x.n },
      { key: "t", header: "Risk, as the document words it", rowHeader: true, wrap: true, cell: (x) => x.text },
      { key: "p", header: "Page", numeric: true, cell: (x) => x.page },
    ]} />
  );
  return (
    <Card label="Risks the document puts first" testId="ipo-risks">
      <CardHead level={2} title="Risks the document puts first" info="The headings of the first risk factors in the offer document that are about this company, in its order and its words, with the page of the PDF each is on. The document lists many more." infoLabel="About these risks" />
      {table(head, "Risks the document puts first")}
      {rest.length > 0 && <Disclosure summary={`Show the other ${rest.length} risks`} testId="ipo-risks-more">{table(rest, "More risks the document puts first")}</Disclosure>}
    </Card>
  );
}

function UsFacts({ f }: { f: Facts }) {
  const u = f.us;
  const rows = ([
    u?.company_shares != null ? { id: "cs", k: "Shares offered by the company", v: sharesText(u.company_shares, "US") } : null,
    u?.selling_shares != null ? { id: "ss", k: "Shares offered by selling stockholders", v: sharesText(u.selling_shares, "US") } : null,
    u?.price != null ? { id: "pr", k: "Offer price", v: price(u.price, "USD", 2) } : null,
    u?.range ? { id: "rg", k: "Price range on the cover", v: `${price(u.range[0], "USD", 2)} to ${price(u.range[1], "USD", 2)}` } : null,
    u?.listing ? { id: "li", k: "Listing", v: `${u.listing}${u.symbol ? `, symbol ${u.symbol}` : ""}` } : null,
    u?.proceeds ? { id: "up", k: "Use of proceeds", v: <span data-testid="ipo-proceeds">{u.proceeds}</span>, n: "The document's words." } : null,
  ] as (Line | null)[]).filter((x): x is Line => !!x);
  return rows.length ? <LineTable label="From the prospectus" rows={rows} /> : null;
}

function FromTheDocument({ f, d }: { f: Facts; d: IpoDetail }) {
  const r = d.ipo;
  const kind = f.kind ?? "offer document";
  if (f.state === "none") {
    return <Card compact label="From the offer document" testId="ipo-facts"><p className="k-small k-muted">No offer document has been found for this issue yet. {r.market === "IN" ? "The draft and red herring prospectuses filed with SEBI are listed under Documents once they are." : "The registration statement and prospectus filed with the SEC are listed under Documents once they are."}</p></Card>;
  }
  if (f.state === "pending") {
    return <Card compact label="From the offer document" testId="ipo-facts"><p className="k-small k-muted">The {kind} is read automatically a few at a time. What it says about the promoters, the objects and the figures shows here once it has been. Open it under Documents meanwhile.</p></Card>;
  }
  if (r.market === "US") {
    return (
      <Card label="From the prospectus" testId="ipo-facts">
        <CardHead level={2} title="From the prospectus" info={`Read by fixed rules from the places the ${kind} always puts these. A fact the rules can't find is left out, not guessed. Open the document for everything else.`} infoLabel="About these facts" />
        <UsFacts f={f} />
      </Card>
    );
  }
  const any = f.promoters?.length || f.selling?.length || f.objects || f.utilisation || f.financials || f.kpis || f.holding || f.peers || f.risks?.length;
  return (
    <div className="ipo-doc" data-testid="ipo-facts">
      {!any && <Card compact label="From the offer document"><p className="k-small k-muted">The rules couldn't read the cover or the summary tables of this document. Open it under Documents.</p></Card>}
      <Objects f={f} d={d} />
      <Owners f={f} />
      <Holding f={f} />
      <Financials f={f} kind={kind} />
      <Indicators f={f} />
      <Valuation f={f} d={d} />
      <Risks f={f} />
      {any && <p className="k-note">Read by fixed rules from the places the {kind} puts these, each with the page of the PDF it is on. A fact the rules can't find is left out, not guessed. Open the document for everything else.</p>}
    </div>
  );
}

function SummaryCard({ d, sum, onWrite, busy, error }: { d: IpoDetail; sum: Summary; onWrite: () => void; busy: boolean; error: string | null }) {
  const kind = sum.kind ?? "offer document";
  if (sum.state === "locked") {
    return (
      <Card label="Summary of the offer document" testId="ipo-summary">
        <CardHead level={2} title="Summary of the offer document" />
        <PlanNote plan="basic">The summary of the offer document is on the {sum.plan} plan. The tables above and the document itself stay free.</PlanNote>
        <LockedPreview title="the summary" actions={false} points={[
          "What the company does and where its money comes from.",
          "How its revenue splits by business segment, product or place, as the document gives it.",
          "Every statement comes with the words of the document it rests on.",
        ]} />
      </Card>
    );
  }
  const items = sum.items;
  const quotes = items ? [items.business && { id: "b", what: "The business", quote: items.business.quote }, ...(items.segments ?? []).map((s, i) => ({ id: `s${i}`, what: `Segment ${i + 1}`, quote: s.quote }))].filter(Boolean) as { id: string; what: string; quote: string }[] : [];
  return (
    <Card label="Summary of the offer document" testId="ipo-summary">
      <CardHead level={2} title="Business and segments" info={`Written once from the passages of the ${kind} and kept for everyone. A statement stays only when the words it quotes are really in the document and every figure in it is in those words. It is not advice: open the document for the whole.`} infoLabel="About this summary" />
      {sum.state === "ready" && items ? (
        <>
          {items.business && <p className="k-small" data-testid="ipo-sum-business">{items.business.text}</p>}
          {items.segments.length > 0 && (
            <div data-testid="ipo-sum-segments">
              <DataTable stack label="How the revenue splits" rows={items.segments} rowKey={(x) => x.text} columns={[{ key: "t", header: "How the revenue splits, as the document gives it", rowHeader: true, wrap: true, cell: (x) => x.text }]} />
            </div>
          )}
          {quotes.length > 0 && (
            <Disclosure summary="Show the document's words" testId="ipo-sum-words">
              <DataTable stack label="The document's words behind each statement" rows={quotes} rowKey={(x) => x.id} columns={[
                { key: "w", header: "Statement", rowHeader: true, cell: (x) => x.what },
                { key: "q", header: "The document's words", wrap: true, cell: (x) => <q className="ipo-quote">{x.quote}</q> },
              ]} />
            </Disclosure>
          )}
          <p className="k-note">Written {sum.at ? asOf(sum.at) : ""} from the {kind}. Facts the document states, not a view on the issue. Figures are in the document's own units (₹ million or ₹ crore, as it writes them).</p>
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
      {d.ipo.market === "IN" && sum.state === "pending" && <p className="k-note">The tables above are already read; this adds the business and its segments in words.</p>}
    </Card>
  );
}

function Documents({ docs, d }: { docs: DocLink[]; d: IpoDetail }) {
  return (
    <Card label="Documents" testId="ipo-docs">
      <CardHead level={2} title="Documents" info={d.ipo.market === "IN" ? "The draft and red herring prospectuses filed with SEBI, and the exchange's copy of the red herring prospectus (a ZIP)." : "The registration statement, its amendments and the final prospectus filed with the SEC."} infoLabel="About these documents" />
      {docs.length ? (
        <DataTable stack label="Offer documents" rows={docs} rowKey={(x) => x.url} columns={[
          { key: "d", header: "Document", rowHeader: true, wrap: true, cell: (x) => <a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer">{x.label} ↗</a> },
          { key: "s", header: "From", cell: (x) => x.source },
          { key: "t", header: "Dated", cell: (x) => (x.date ? fmtDate(x.date) : "–") },
        ]} />
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
  const [gone, setGone] = useState(false);            // the address names no issue: nothing to try again (RC5-004)
  const [busy, setBusy] = useState(false);
  const [writeError, setWriteError] = useState<string | null>(null);
  const load = useCallback((quiet = false) => {
    if (!quiet) { setD(null); setError(null); setGone(false); }
    ipoApi.one(id).then(setD).catch((e) => {
      if (quiet) return;
      setGone(e instanceof ApiError && e.status === 404);
      setError(e instanceof ApiError ? e.message : "This IPO couldn't be read just now.");
    });
  }, [id]);
  useEffect(() => { load(); }, [load]);
  useLiveRefresh(d?.ipo.stage === "open", () => load(true));       // each minute while bidding is open (LIVE-1; was every two)
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
  const lede = r ? [r.market === "IN" ? `${r.segment === "sme" ? "SME" : "Main board"} issue` : "US offering", r.symbol,
    r.open && r.close ? `bidding ${spanText(r.open, r.close)}` : r.priced ? `${r.stage === "listed" ? "trading from" : "priced for"} ${fmtDate(r.priced)}` : r.expected ? `expected to price ${fmtDate(r.expected)}` : null].filter(Boolean).join(" · ") : undefined;
  return (
    <div className="k-page ipo-page">
      <PageHeader eyebrow={eyebrowOf("/invest/ipos")} title={r?.name ?? "IPO"} lede={lede} actions={badge ? <Badge tone={badge.tone}>{badge.word}</Badge> : undefined} />
      <p className="k-small"><Link className="link" to={`/invest/ipos?m=${r?.market ?? "IN"}`}>← All IPOs</Link></p>
      {error ? (gone ? <ErrorState title="That IPO isn't on the list">The address may be old, or the issue was taken off the list. Every issue the exchanges list is on the IPOs page.</ErrorState>
        : <ErrorState title="This IPO couldn't be read" action={{ label: "Try again", onClick: () => load() }}>{error}</ErrorState>)
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
