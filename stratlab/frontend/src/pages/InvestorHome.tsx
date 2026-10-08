import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { inr, marketTz, money, pct } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { RegionSwitch } from "../components/Research";
import { RouteSeg, WATCH_VIEWS } from "../components/RouteSeg";
import { saveRegion, savedRegion, type Region } from "../lib/research";
import { Badge, Card, CardHead, Delta, EmptyState, ErrorState, PageHeader, PlanNote, Seg, Skeleton, Stat, StatRow } from "../components/kit";

type Row = {
  symbol: string; name: string; problem: string | null; price: number | null; chg: number | null; stage: number | null;
  st_up: boolean | null; signal: "fresh" | "st_s2" | "stage2" | null; sector: { symbol: string; name: string; quadrant: string | null } | null;
  red: number | null; amber: number | null; fund_raise: boolean; checks: { pass: number; watch: number; fail: number; na: number } | null;
  fails: string[]; card: { met: number; missed: number; score: number } | null; has_read: boolean;
};

const QUAD: Record<string, string> = { leading: "Leading", improving: "Improving", weakening: "Weakening", lagging: "Lagging" };   // one neutral style: a quadrant is a fact, not good or bad
const SIGNAL: Record<string, string> = { fresh: "Fresh Stage 2 + Supertrend", st_s2: "Stage 2 + Supertrend", stage2: "Stage 2" };
const attention = (r: Row) => (r.red ?? 0) * 3 + (r.checks?.fail ?? 0) + (r.fund_raise ? 1 : 0) + (r.card && r.card.score < 40 ? 1 : 0);

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="inv-cell"><span className="k-note">{label}</span><div className="k-small">{children}</div></div>;
}

export function InvestorHomePage() {
  const { me, fail } = useApp();
  const pro = !!me?.plan_info?.features?.investor_home;
  const [rows, setRows] = useState<Row[] | null>(null);
  const [at, setAt] = useState<string | null>(null);
  const [order, setOrder] = useState<"list" | "attention">("attention");
  const [region, setRegion] = useState<Region>(savedRegion);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const us = region === "US";
  const place = us ? "US" : "India";

  useEffect(() => {
    if (!pro) return;
    setRows(null); setError(null);
    api<{ rows: Row[]; as_of?: string | null }>(`/research/investor?region=${region}`).then((x) => { setRows(x.rows); setAt(x.as_of ?? null); })
      .catch((e) => { setError((e as Error).message); fail(e); });
  }, [pro, fail, region, tries]);
  const pick = (r: Region) => { saveRegion(r); setRegion(r); };

  const shown = useMemo(() => (rows && order === "attention" ? [...rows].sort((a, b) => attention(b) - attention(a)) : rows), [rows, order]);
  const s2 = rows?.filter((r) => r.stage === 2).length ?? 0;
  const flagged = rows?.filter((r) => (r.red ?? 0) > 0).length ?? 0;
  const leading = rows?.filter((r) => r.sector?.quadrant === "leading").length ?? 0;

  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/watchlist")} title="Your watchlist, all in one place" asOf={rows ? at : undefined} asOfLabel="Checked" asOfTz={marketTz(region)}
        lede={`For each ${place} watchlist company: the price trend, where its sector sits in the rotation, ${us ? "" : "red-flag filings, "}the investor checklist and how well management delivered on past targets. Facts to read, not advice.`} />
      <div className="k-toolbar"><RegionSwitch region={region} setRegion={pick} /><RouteSeg label="Watchlist view" views={WATCH_VIEWS} /></div>
      {!pro && <PlanNote>Watchlist at a glance is on the Basic plan.</PlanNote>}
      {pro && error && <ErrorState title="The watchlist couldn't be checked" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>}
      {pro && !rows && !error && <Card><Skeleton label="Checking each watchlist company" lines={4} /></Card>}
      {rows && rows.length === 0 && (
        <Card>
          <EmptyState title={`Your watchlist has no ${place} stocks yet`} action={{ label: "Find a company", to: `/research?region=${region}` }}>
            Open a company and press Watch: it shows up here with its trend, sector and checklist.
          </EmptyState>
        </Card>
      )}
      {rows && rows.length > 0 && (
        <>
          <Card>
            <StatRow label="Your watchlist in numbers">
              <Stat item label="Companies" value={String(rows.length)} />
              <Stat item label="In Stage 2" value={String(s2)} />
              <Stat item label="Sector leading the market" value={String(leading)} />
              {!us && <Stat item label="With red-flag filings" value={String(flagged)} />}
            </StatRow>
          </Card>
          <div className="k-toolbar">
            <Seg label="Order" value={order} onChange={(v) => setOrder(v as "list" | "attention")} options={[{ value: "attention", label: "Most flags first" }, { value: "list", label: "Watchlist order" }]} />
          </div>
          {shown!.map((r) => (
            <Card key={r.symbol}>
              <CardHead level={3} title={<Link className="link" to={`/research/${region}/${encodeURIComponent(r.symbol)}/deep`}>{r.name}</Link>}
                actions={r.price != null ? <><span className="k-small">{us ? money(r.price, "USD", 2) : inr(r.price, 2)}</span>{r.chg != null && <Delta value={r.chg} tone="neutral">{pct(r.chg)}</Delta>}</> : undefined} />
              <span className="k-note">{r.symbol}</span>
              {r.problem && <p className="k-note">Company numbers unavailable: {r.problem}</p>}
              <div className="inv-stat-cells">
                <Cell label="Trend">{r.stage == null ? "–" : <>Stage {r.stage} · Supertrend {r.st_up ? "up" : "down"}{r.signal && <> · <Badge tone="plain" dot={false}>{SIGNAL[r.signal]}</Badge></>}</>}</Cell>
                <Cell label="Sector">{r.sector ? <>{r.sector.name}{r.sector.quadrant && <> · <Badge tone="plain" dot={false}>{QUAD[r.sector.quadrant]}</Badge></>}</> : "–"}</Cell>
                {!us && <Cell label="Filings, last 3 months">{r.red == null ? "–" : r.red ? <span>{r.red} red flag{r.red === 1 ? "" : "s"}</span> : "No red flags"}{r.fund_raise ? " · fund raise filed" : ""}</Cell>}
                <Cell label="Checklist">{r.checks ? <><b>{r.checks.pass} pass</b> · {r.checks.watch} watch · {r.checks.fail} fail</> : "–"}</Cell>
                <Cell label="Management report card">{r.card ? `${r.card.met} of ${r.card.met + r.card.missed} targets met` : <Link className="link" to={`/research/${region}/${encodeURIComponent(r.symbol)}/deep`}>Not checked yet</Link>}</Cell>
              </div>
              {r.fails.length > 0 && <p className="k-note">Failed checks: {r.fails.join(" · ")}</p>}
            </Card>
          ))}
          <p className="k-note inv-text">Checks use fixed rules shown on each company's deep dive. The report card appears once someone has checked that company's past calls. Nothing here is investment advice.</p>
        </>
      )}
    </div>
  );
}
