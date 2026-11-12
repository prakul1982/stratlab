import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { grouped, pctPlain } from "../lib/format";
import { changeOver, HOLDER_NAME, stacks, type HolderKey, type HoldingQuarter, type Region, type Shareholding } from "../lib/companyTables";
import { Card, CardHead, DataTable, ErrorState, PlanNote, Signed, Skeleton, type Column } from "./kit";
import "./companyTables.css";

/* Shareholding by quarter (lane c-f2): promoters, FIIs, DIIs, government and public, and the number of shareholders, from the quarterly
 * shareholding pattern. Free: the latest quarter; Basic: the last 12 quarters and a small stacked chart. US companies file no such
 * pattern: a note says so and where the holders above 5% are. */

/** Each quarter as one bar of 100%, the groups stacked bottom up: drawn in SVG with the kit's series colours, its numbers in the table below. */
export function HoldingBars({ quarters, keys }: { quarters: HoldingQuarter[]; keys: HolderKey[] }) {
  const bars = stacks(quarters, keys);
  const W = 100 / Math.max(1, bars.length);
  const last = quarters[quarters.length - 1];
  const words = keys.map((k) => `${HOLDER_NAME[k]} ${last?.[k] == null ? "–" : pctPlain(last[k] as number, 2)}`).join(", ");
  return (
    <figure className="ct-bars">
      <svg viewBox="0 0 100 60" preserveAspectRatio="none" role="img" aria-label={`Who owns it, quarter by quarter, ${quarters[0]?.quarter} to ${last?.quarter}. In ${last?.quarter}: ${words}.`}>
        {bars.map((b, i) => b.parts.map((p) => (
          <rect key={`${b.quarter}-${p.key}`} x={i * W + W * 0.12} width={W * 0.76} y={60 - p.to * 0.6} height={Math.max(0, (p.to - p.from) * 0.6)} className={`ct-h-${p.key}`}>
            <title>{`${b.quarter}: ${HOLDER_NAME[p.key]} ${pctPlain(p.to - p.from, 2)}`}</title>
          </rect>
        )))}
      </svg>
      <div className="ct-bars-x" aria-hidden="true"><span>{quarters[0]?.quarter}</span><span>{last?.quarter}</span></div>
      <figcaption className="k-legend">{keys.map((k) => <span key={k}><i className={`ct-h-${k}`} />{HOLDER_NAME[k]}</span>)}</figcaption>
    </figure>
  );
}

export function ShareholdingCard({ region, symbol, id = "co-holding-history" }: { region: Region; symbol: string; id?: string }) {
  const [v, setV] = useState<Shareholding | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let live = true;
    setV(null); setError(null);
    api<Shareholding>(`/research/company/${region}/${encodeURIComponent(symbol)}/shareholding`)
      .then((x) => { if (live) setV(x); })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : "The shareholding couldn't be read."); });
    return () => { live = false; };
  }, [region, symbol, tries]);

  const head = <CardHead title="Shareholding history" info="Each group's share of all shares at the quarter's end, from the company's quarterly shareholding pattern, and the number of shareholders." />;
  if (error) return <Card id={id}>{head}<ErrorState title="The shareholding couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState></Card>;
  if (!v) return <Card id={id}>{head}<Skeleton label="Reading the shareholding" lines={3} /></Card>;
  if (!v.available) return <Card id={id}>{head}<p className="k-small k-muted" data-testid="holding-note">{v.note}</p></Card>;

  const keys = v.keys ?? [];
  const rows = [...v.quarters].reverse();         // the newest quarter first
  const share = (x: number | null | undefined) => (x == null ? "–" : pctPlain(x, 2));
  const columns: Column<HoldingQuarter>[] = [
    { key: "q", header: "Quarter", rowHeader: true, cell: (q) => q.quarter },
    ...keys.map((k): Column<HoldingQuarter> => ({ key: k, header: HOLDER_NAME[k], numeric: true, cell: (q) => share(q[k]) })),
    { key: "n", header: "Shareholders", numeric: true, cell: (q) => grouped(q.shareholders, 0, region) },
  ];
  const moves = v.quarters.length > 1 ? keys.map((k) => ({ k, d: changeOver(v.quarters, k) })).filter((x) => x.d != null) : [];
  return (
    <Card id={id}>
      {head}
      {v.chart && <HoldingBars quarters={v.quarters} keys={keys} />}
      {moves.length > 0 && (
        <p className="k-small">Since {v.quarters[0].quarter}: {moves.map((x, i) => <span key={x.k}>{i > 0 && " · "}{HOLDER_NAME[x.k]} <Signed value={x.d}>{`${x.d! > 0 ? "+" : x.d! < 0 ? "−" : ""}${Math.abs(x.d!).toFixed(2)} pts`}</Signed></span>)}</p>
      )}
      <DataTable label={`${symbol} shareholding by quarter`} rows={rows} rowKey={(q) => q.quarter} columns={columns} stack={false} />
      {v.pledge_note && <p className="k-note">{v.pledge_note}</p>}
      {v.locked && <PlanNote plan={v.locked.plan}>{v.locked.message}</PlanNote>}
    </Card>
  );
}
