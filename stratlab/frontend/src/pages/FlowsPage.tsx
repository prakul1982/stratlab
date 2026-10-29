import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { crore, dayName, spanLine, statusLine, type CashPoint, type Summary } from "../lib/positioning";
import { cutPoints } from "../lib/range";
import { LineChart } from "../components/Charts";
import { Card, CardHead, DataTable, EmptyState, ErrorState, PageHeader, RangeChips, Signed, Skeleton, useRange, type Column } from "../components/kit";

/* /invest/flows (IA-1: Market today's Flows tab): what foreign portfolio investors (FII/FPI) and domestic institutions (DII)
 * bought and sold in India's cash market, from the exchange's provisional evening figures. The latest day for everyone;
 * every recorded day (a table and a chart) on the plan that has Positioning's history, as on Positioning. The same reads as
 * Positioning's cash card, so the two pages never disagree. Facts only. */

/** A crore figure with its sign and ▲/▼, in the kit's colours. */
function Net({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="k-muted">–</span>;
  return <Signed value={v}>{`${v > 0 ? "▲ " : v < 0 ? "▼ " : ""}${crore(v, true)}`}</Signed>;
}

type DayRow = CashPoint & { both: number | null };

export function FlowsPage() {
  const [s, setS] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [again, setAgain] = useState(0);
  const [hist, setHist] = useState<CashPoint[] | null | "error">(null);
  useEffect(() => {
    setError(null);
    api<Summary>("/trade/positioning?pcr=false").then(setS).catch((e) => setError(e instanceof ApiError ? e.message : "The flows couldn't be read."));
  }, [again]);
  const full = !!s?.full;
  useEffect(() => {
    if (!full) return;
    let live = true;
    api<{ points: CashPoint[] }>("/trade/positioning/history?kind=cash&range=all").then((r) => live && setHist(r.points)).catch(() => live && setHist("error"));
    return () => { live = false; };
  }, [full]);
  const all = useMemo(() => (Array.isArray(hist) ? hist.filter((p) => p.fii != null || p.dii != null) : []), [hist]);
  const times = useMemo(() => all.map((p) => p.day.slice(0, 10)), [all]);
  const rng = useRange("flows", times, "3m");
  const shown = useMemo(() => cutPoints(all, rng.value), [all, rng.value]);
  const rows: DayRow[] = useMemo(() => [...shown].reverse().map((p) => ({ ...p, both: p.fii == null || p.dii == null ? null : p.fii + p.dii })), [shown]);
  const total = (k: "fii" | "dii" | "both") => rows.reduce((n, r) => n + (r[k] ?? 0), 0);
  const c = s?.cash;
  const cols: Column<DayRow>[] = [
    { key: "d", header: "Day", rowHeader: true, cell: (r) => dayName(r.day) },
    { key: "f", header: "FII/FPI net", numeric: true, cell: (r) => <Net v={r.fii} /> },
    { key: "i", header: "DII net", numeric: true, cell: (r) => <Net v={r.dii} /> },
    { key: "b", header: "Both, net", numeric: true, cell: (r) => <Net v={r.both} /> },
  ];
  return (
    <div className="k-page">
      <PageHeader eyebrow="Invest · Market today" title="Flows"
        lede="What foreign and domestic institutions bought and sold in India's cash market, in ₹ crore: the exchange's provisional figures, published each trading evening. Facts, not advice." />
      {error ? <ErrorState title="The flows couldn't be read" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>{error}</ErrorState>
        : !s || !c ? <Card><Skeleton label="Reading the newest flows" /></Card>
        : (
          <>
            <Card label="The latest day" testId="flows-latest">
              <CardHead title={c.as_of ? `The latest day: ${dayName(c.as_of)}` : "The latest day"} infoLabel="About these figures"
                info="The exchange's provisional numbers for the day: what foreign portfolio investors (FII/FPI) and domestic institutions (DII) bought and sold in the cash market. Final numbers can differ a little." />
              {c.fii && c.dii ? (
                <DataTable label="FII and DII cash market, the latest day" rows={[{ id: "fii", k: "FII/FPI", n: c.fii }, { id: "dii", k: "DII", n: c.dii }]} rowKey={(r) => r.id} columns={[
                  { key: "k", header: "Who", rowHeader: true, cell: (r) => r.k },
                  { key: "buy", header: "Bought", numeric: true, cell: (r) => crore(r.n.buy) },
                  { key: "sell", header: "Sold", numeric: true, cell: (r) => crore(r.n.sell) },
                  { key: "net", header: "Net", numeric: true, cell: (r) => <Net v={r.n.net} /> },
                ]} />
              ) : <p className="k-small k-muted">{statusLine(c, "cash numbers")}</p>}
            </Card>
            {!full ? (
              <Card label="Every recorded day" testId="flows-locked">
                <CardHead title="Every recorded day" />
                <p className="k-small k-muted">Each recorded day's FII and DII net buying, as a table and a chart, is on the {s.plan_needed} plan, as on Positioning. The latest day above is on every plan.</p>
                <Link to="/plans" className="btn sm k-btn-end">See the {s.plan_needed} plan</Link>
              </Card>
            ) : (
              <Card label="Every recorded day" testId="flows-days">
                <CardHead title="Every recorded day" infoLabel="About the days"
                  info={`The exchange shows only its latest day, so the days start when StratLab began reading them${s.coverage?.cash ? `: ${spanLine(s.coverage.cash)}` : ""}.`}
                  actions={<RangeChips chart="flows" times={times} options={rng.options} value={rng.value} onChange={rng.pick} label="Time range" />} />
                {hist === null ? <Skeleton label="Reading the recorded days" />
                  : hist === "error" ? <ErrorState title="The recorded days couldn't be read">Try again in a minute.</ErrorState>
                  : !rows.length ? <EmptyState title="No days recorded yet">The first day appears after the exchange's next evening figures.</EmptyState>
                  : (
                    <>
                      {shown.length >= 2 && (
                        <LineChart lines={[{ values: shown.map((p) => p.fii), color: "var(--pos-call)", width: 2, label: "FII/FPI" },
                          { values: shown.map((p) => p.dii), color: "var(--pos-put)", width: 2, label: "DII" }]}
                          labels={shown.map((p) => dayName(p.day))} times={shown.map((p) => p.day.slice(0, 10))} ranges={false} legend format={(v) => crore(v, true)} signedTip
                          axisFormat={(v) => crore(v)} baseline={0} height={220} ariaLabel="FII and DII net cash market flows by day" />
                      )}
                      <DataTable label="FII and DII net buying by day" columns={cols} rows={rows} rowKey={(r) => r.day} phonePage={30}
                        foot={{ d: `${rows.length} day${rows.length === 1 ? "" : "s"}, total`, f: <Net v={total("fii")} />, i: <Net v={total("dii")} />, b: <Net v={total("both")} /> }} />
                    </>
                  )}
              </Card>
            )}
            <p className="k-note">FII futures and options positions, PCR and India VIX are on <Link className="link" to="/trade/positioning">Positioning</Link> (Trade › F&amp;O desk).</p>
          </>
        )}
    </div>
  );
}
