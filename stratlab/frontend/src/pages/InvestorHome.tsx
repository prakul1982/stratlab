import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { pct, signClass } from "../lib/format";
import { ResearchNav } from "../components/Research";
import { REGION_NAME, saveRegion, savedRegion, type Region } from "../lib/research";
import { AsOf, Loading } from "../components/ui";

type Row = {
  symbol: string; name: string; problem: string | null; price: number | null; chg: number | null; stage: number | null;
  st_up: boolean | null; signal: "fresh" | "st_s2" | "stage2" | null; sector: { symbol: string; name: string; quadrant: string | null } | null;
  red: number | null; amber: number | null; fund_raise: boolean; checks: { pass: number; watch: number; fail: number; na: number } | null;
  fails: string[]; card: { met: number; missed: number; score: number } | null; has_read: boolean;
};

const QUAD: Record<string, [string, string]> = { leading: ["Leading", "pass"], improving: ["Improving", "next"], weakening: ["Weakening", "warn"], lagging: ["Lagging", "fail"] };
const SIGNAL: Record<string, string> = { fresh: "Fresh ST S2", st_s2: "ST S2", stage2: "Stage 2" };
const attention = (r: Row) => (r.red ?? 0) * 3 + (r.checks?.fail ?? 0) + (r.fund_raise ? 1 : 0) + (r.card && r.card.score < 40 ? 1 : 0);

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="inv-cell"><span className="tiny muted">{label}</span><div className="small">{children}</div></div>;
}

export function InvestorHomePage() {
  const { me, fail } = useApp();
  const pro = !!me?.plan_info?.features?.investor_home;
  const [rows, setRows] = useState<Row[] | null>(null);
  const [at, setAt] = useState<string | null>(null);
  const [order, setOrder] = useState<"list" | "attention">("attention");
  const [region, setRegion] = useState<Region>(savedRegion);
  const us = region === "US";
  const place = us ? "US" : "India";

  useEffect(() => {
    if (!pro) return;
    setRows(null);
    api<{ rows: Row[]; as_of?: string | null }>(`/research/investor?region=${region}`).then((x) => { setRows(x.rows); setAt(x.as_of ?? null); }).catch(fail);
  }, [pro, fail, region]);
  const pick = (r: Region) => { saveRegion(r); setRegion(r); };

  const shown = useMemo(() => (rows && order === "attention" ? [...rows].sort((a, b) => attention(b) - attention(a)) : rows), [rows, order]);
  const s2 = rows?.filter((r) => r.stage === 2).length ?? 0;
  const flagged = rows?.filter((r) => (r.red ?? 0) > 0).length ?? 0;
  const leading = rows?.filter((r) => r.sector?.quadrant === "leading").length ?? 0;

  return (
    <div className="stack" style={{ gap: 24 }}>
      <ResearchNav region={region} setRegion={pick} />
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Investor home · {REGION_NAME[region]}</span>
        <h1 className="page-title">Your watchlist, all in one place</h1>
        <p className="page-sub">For each {place} watchlist company: the price trend, where its sector sits in the rotation, {us ? "" : "red-flag filings, "}the investor checklist and how well management delivered on past targets. A place to see what needs a closer look, not advice.</p>
        {rows && <AsOf parts={[["Checked", at]]} />}
      </div>
      {!pro && <div className="banner"><span>Watchlist at a glance is on the Basic plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>}
      {pro && !rows && <Loading label="Checking each watchlist company" />}
      {rows && rows.length === 0 && (
        <div className="card dashed stack" style={{ gap: 10, alignItems: "flex-start" }}>
          <p className="muted">Your watchlist has no {place} stocks yet. Open a company and press <b>Watch</b>: it shows up here with its trend, sector and checklist.</p>
          <Link to={`/research?region=${region}`} className="btn sm">Find a company</Link>
        </div>
      )}
      {rows && rows.length > 0 && (
        <>
          <div className="stat-row">
            <div className="stat"><span className="tiny muted">Companies</span><b className="num">{rows.length}</b></div>
            <div className="stat"><span className="tiny muted">In Stage 2</span><b className="num">{s2}</b></div>
            <div className="stat"><span className="tiny muted">Sector leading the market</span><b className="num">{leading}</b></div>
            {!us && <div className="stat"><span className="tiny muted">With red-flag filings</span><b className="num">{flagged}</b></div>}
          </div>
          <div className="seg" role="radiogroup" aria-label="Order" style={{ alignSelf: "flex-start" }}>
            <button role="radio" aria-checked={order === "attention"} aria-pressed={order === "attention"} onClick={() => setOrder("attention")}>Needs a look first</button>
            <button role="radio" aria-checked={order === "list"} aria-pressed={order === "list"} onClick={() => setOrder("list")}>Watchlist order</button>
          </div>
          <div className="stack" style={{ gap: 14 }}>
            {shown!.map((r) => (
              <section key={r.symbol} className="card stack" style={{ gap: 12 }}>
                <div className="spread" style={{ gap: 10, flexWrap: "wrap", alignItems: "baseline" }}>
                  <div className="stack" style={{ gap: 2, minWidth: 0 }}>
                    <Link className="link" to={`/research/${region}/${encodeURIComponent(r.symbol)}/deep`}><b>{r.name}</b></Link>
                    <span className="tiny muted mono">{r.symbol}</span>
                  </div>
                  {r.price != null && <span className="mono small">{us ? "$" : "₹"}{r.price.toLocaleString(us ? "en-US" : "en-IN", { maximumFractionDigits: 2 })} <span className={signClass(r.chg)}>{r.chg == null ? "" : pct(r.chg)}</span></span>}
                </div>
                {r.problem && <p className="tiny muted" style={{ margin: 0 }}>Company numbers unavailable: {r.problem}</p>}
                <div className="inv-grid">
                  <Cell label="Trend">{r.stage == null ? "–" : <>Stage {r.stage} · Supertrend {r.st_up ? "up" : "down"}{r.signal && <> · <span className={`badge ${r.signal === "fresh" ? "pass" : "next"}`}>{SIGNAL[r.signal]}</span></>}</>}</Cell>
                  <Cell label="Sector">{r.sector ? <>{r.sector.name}{r.sector.quadrant && <> · <span className={`badge ${QUAD[r.sector.quadrant][1]}`}>{QUAD[r.sector.quadrant][0]}</span></>}</> : "–"}</Cell>
                  {!us && <Cell label="Filings, last 3 months">{r.red == null ? "–" : r.red ? <span className="neg">{r.red} red flag{r.red === 1 ? "" : "s"}</span> : "No red flags"}{r.fund_raise ? " · fund raise filed" : ""}</Cell>}
                  <Cell label="Checklist">{r.checks ? <><b>{r.checks.pass} pass</b> · {r.checks.watch} watch · {r.checks.fail} fail</> : "–"}</Cell>
                  <Cell label="Management report card">{r.card ? `${r.card.met} of ${r.card.met + r.card.missed} targets met` : <Link className="link" to={`/research/${region}/${encodeURIComponent(r.symbol)}/deep`}>Not checked yet</Link>}</Cell>
                </div>
                {r.fails.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>Failed checks: {r.fails.join(" · ")}</p>}
              </section>
            ))}
          </div>
          <p className="small muted" style={{ maxWidth: "80ch" }}>Checks use fixed rules shown on each company's deep dive. The report card appears once someone has checked that company's past calls. Nothing here is investment advice.</p>
        </>
      )}
    </div>
  );
}
