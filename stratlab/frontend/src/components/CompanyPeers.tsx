import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { download as saveFile } from "../lib/share";
import { pct, pctPlain } from "../lib/format";
import { capText, downloadPath, peText, sortPeers, type PeerKey, type PeerRow, type Peers, type Region } from "../lib/companyTables";
import { Card, CardHead, DataTable, EmptyState, ErrorState, PlanNote, Select, Signed, Skeleton, usePhone, type Column } from "./kit";
import "./companyTables.css";

/* Peers (lane c-f2): the companies of the same industry nearest in market value, with the company's own row in bold and the median of the
 * peers shown under them. Free: the three nearest; Basic: up to ten, sortable; Pro: CSV. The server trims what a plan doesn't include. */

export function PeersCard({ region, symbol, id = "co-peers" }: { region: Region; symbol: string; id?: string }) {
  const { fail } = useApp();
  const [v, setV] = useState<Peers | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [sort, setSort] = useState<{ key: PeerKey; desc: boolean } | null>(null);
  const [getting, setGetting] = useState(false);
  const phone = usePhone();

  useEffect(() => {
    let live = true;
    setV(null); setError(null);
    api<Peers>(`/research/company/${region}/${encodeURIComponent(symbol)}/peers`)
      .then((x) => { if (live) setV(x); })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : "The peers couldn't be read."); });
    return () => { live = false; };
  }, [region, symbol, tries]);

  const csv = async () => {
    setGetting(true);
    try {
      const r = await api<Response>(downloadPath(region, symbol, "peers.csv"), { raw: true });
      saveFile(await r.blob(), `stratlab-${symbol}-peers.csv`);
    } catch (e) { fail(e); } finally { setGetting(false); }
  };

  const head = (actions?: React.ReactNode) => <CardHead title="Peers" actions={actions}
    info="Listed companies of the same industry (its sector when the industry has too few), nearest in market value. Sales growth is compounded over 3 years; EBITDA margin, net margin and the return are of the latest reported year; P/E at the last close. A lender is compared on return on equity." />;

  if (error) return <Card id={id}>{head()}<ErrorState title="The peers couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState></Card>;
  if (!v) return <Card id={id}>{head()}<Skeleton label="Reading the peers" lines={4} /></Card>;
  if (!v.total) return <Card id={id}>{head()}<EmptyState title="No peers to compare yet">{`${v.basis_words[0].toUpperCase()}${v.basis_words.slice(1)}.`}</EmptyState></Card>;

  const peers = sort ? sortPeers(v.rows, sort.key, sort.desc) : v.rows;
  const rows: PeerRow[] = v.own ? [v.own, ...peers] : peers;
  const pctCell = (x: number | null) => pctPlain(x, 1).replace("-", "−");
  const cols: Column<PeerRow>[] = [
    { key: "name", header: "Company", rowHeader: true, wrap: true, cell: (r) => (r.own
      ? <b>{r.name}<span className="sr-only"> (this company)</span></b>
      : <Link className="link" to={`/research/${region}/${encodeURIComponent(r.symbol)}`}>{r.name}</Link>) },
    { key: "market_cap", header: "Market value", numeric: true, sortable: true, cell: (r) => capText(r.market_cap, region) },
    // the header says the span: the 3-year compounded rate, not the latest year's (LIVE8B-017)
    { key: "sales_growth", header: "Sales growth, 3 yrs", info: "Compounded a year over the last 3 years.", numeric: true, sortable: true,
      cell: (r) => (r.sales_growth == null ? "–" : <Signed value={r.sales_growth}>{pct(r.sales_growth, 1)}</Signed>) },
    ...(v.lender ? [] : [{ key: "ebitda", header: "EBITDA margin", numeric: true, sortable: true, cell: (r: PeerRow) => pctCell(r.ebitda) } as Column<PeerRow>]),
    { key: "net", header: "Net margin", numeric: true, sortable: true, cell: (r) => pctCell(r.net) },
    { key: "ret", header: v.return_label, info: v.lender ? "Return on equity: net profit over shareholders' equity." : "Return on capital employed: operating profit over equity and debt.",
      numeric: true, sortable: true, cell: (r) => pctCell(r.ret) },
    { key: "pe", header: "P/E", numeric: true, sortable: true, cell: (r) => peText(r.pe) },
  ];
  const m = v.median;
  const foot = m ? { name: `Median of ${v.rows.length} peer${v.rows.length === 1 ? "" : "s"}`, market_cap: capText(m.market_cap, region),
    sales_growth: m.sales_growth == null ? "–" : pct(m.sales_growth, 1), ebitda: pctCell(m.ebitda), net: pctCell(m.net), ret: pctCell(m.ret), pe: peText(m.pe) } : undefined;
  const onSort = (k: string) => setSort((s) => ({ key: k as PeerKey, desc: s?.key === k ? !s.desc : true }));
  // on a phone the rows are cards with no header to press: the sort is picked here instead (Basic)
  const phoneSort = phone && v.can_sort ? <>
    <Select label="Sort by" small value={sort?.key ?? ""} onChange={(k) => setSort(k ? { key: k as PeerKey, desc: true } : null)}
      options={[{ value: "", label: "Nearest in value" }, ...cols.filter((c) => c.sortable).map((c) => ({ value: c.key, label: typeof c.header === "string" ? c.header : c.key }))]} />
    {sort && <button type="button" className="btn quiet sm" onClick={() => setSort((x) => (x ? { ...x, desc: !x.desc } : x))}>{sort.desc ? "High to low" : "Low to high"}</button>}
  </> : null;
  const download = v.can_export ? <button type="button" className="btn quiet sm" disabled={getting} onClick={() => void csv()}>{getting ? "Preparing…" : "Download CSV"}</button> : null;
  return (
    <Card id={id}>
      {head(phoneSort || download ? <>{phoneSort}{download}</> : undefined)}
      <p className="k-small k-muted">{v.basis_words[0].toUpperCase() + v.basis_words.slice(1)}{v.return_label === "ROE" ? "; compared on return on equity, as a lender" : ""}. Market value in {region === "IN" ? "rupees" : "dollars"}.</p>
      <div className="ct-peers">
        {/* on a phone the company and its five nearest, then "Show more" (LIVE8B-012: eleven stacked cards ran 2,400 px) */}
        <DataTable label={`${symbol} and its peers`} rows={rows} rowKey={(r) => r.symbol} columns={cols} foot={foot} phonePage={6}
          rowAttrs={(r): Record<string, string> => (r.own ? { className: "ct-own", "data-own": "" } : { "data-peer": r.symbol })}
          sort={v.can_sort ? { key: sort?.key ?? "", desc: sort?.desc ?? true, onSort } : undefined} />
      </div>
      {v.locked && <PlanNote plan={v.locked.plan}>{v.locked.message}</PlanNote>}
      {v.export_locked && <p className="k-note">{v.export_locked.message}</p>}
    </Card>
  );
}
