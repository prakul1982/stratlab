import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { dateOnly, money } from "../../lib/format";
import { AsOf, Loading } from "../../components/ui";

/* Fixed-income rates and the yield after your tax: T-bill cut-offs, G-sec yields and the repo rate from the Reserve
 * Bank, this quarter's small savings rates with their tax treatment, the RBI floating rate bond, and your own deposits
 * from Net worth. Rates and arithmetic with their dates: never a ranking or a "best" deposit. */

type Tax = "eee" | "taxable" | "discount" | "reference";
type Row = { key: string; name: string; rate: number; tax: Tax; after_tax: number | null; how: string; as_of?: string | null; c80?: boolean; from?: string; to?: string };
type Deposit = { id: string; kind: "fd" | "rd"; name: string; rate: number; after_tax: number | null; maturity: string; matured: boolean; principal?: number;
  monthly?: number; interest: number; interest_after_tax: number; compounding?: string };
type Rates = {
  full: boolean; plan: string; tax_rate: number; basis: "slab" | "estimate"; slab: number | null; slabs: number[]; fy: number;
  mine: { rate: number; regime: string; income: number; age: string; fy: number } | null;
  market: Row[]; market_read_at: string | null; market_available: boolean;
  small_savings: { quarter: string; from: string; to: string; notified: string; source: string; rows: Row[] };
  bonds: Row[]; deposits: Deposit[]; tax_text: Record<Tax, string>; notes: string[]; disclaimer: string; as_of: string; rbi_source: string;
};

const pctText = (v: number | null | undefined, dp = 2) => (v == null ? "–" : `${v.toFixed(dp)}%`);
const inr = (v: number | null | undefined) => money(v, "INR", 0);
const fyLabel = (fy: number) => `FY ${fy}-${String(fy + 1).slice(2)}`;

export function RatesPage() {
  const { fail } = useApp();
  const [pick, setPick] = useState<number | "mine">("mine");
  const [d, setD] = useState<Rates | null>(null);

  useEffect(() => {
    let live = true;
    api<Rates>(pick === "mine" ? "/money/rates" : `/money/rates?slab=${pick}`).then((r) => { if (live) setD(r); }).catch(fail);
    return () => { live = false; };
  }, [pick, fail]);

  const table = (rows: Row[], label: string, extra?: (r: Row) => ReactNode) => (
    <div className="table-wrap">
      <table aria-label={label}>
        <thead><tr><th style={{ textAlign: "left" }}>What</th><th>Rate</th><th>After tax</th><th style={{ textAlign: "left" }}>Interest</th><th style={{ textAlign: "left" }}>Tax</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.key}>
            <td style={{ textAlign: "left", minWidth: 200, whiteSpace: "normal" }}><b>{r.name}</b>{extra?.(r)}</td>
            <td className="num">{pctText(r.rate)}</td>
            <td className="num">{r.after_tax == null ? "–" : pctText(r.after_tax)}</td>
            <td style={{ textAlign: "left", minWidth: 150, whiteSpace: "normal" }} className="small">{r.how}</td>
            <td style={{ textAlign: "left", minWidth: 170, whiteSpace: "normal" }} className="small">{d!.tax_text[r.tax]}{r.c80 && r.tax !== "eee" ? "; the deposit counts under 80C" : ""}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );

  return (
    <div className="stack rates-page" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Money · fixed income</span>
        <h1 className="page-title">Rates and your yield after tax</h1>
        <p className="page-sub">Treasury bills, government bonds, the repo rate, this quarter's small savings rates and your own deposits, each beside what it
          comes to after tax at your rate. Published rates with their dates, and arithmetic: not a ranking of where to put money.</p>
      </div>

      {!d ? <Loading label="Reading the rates" /> : <>
        <section className="card stack" style={{ gap: 10 }} aria-label="Your tax rate">
          <h2 className="h2">Your tax rate</h2>
          <div className="seg wrap" role="group" aria-label="Tax rate">
            {d.full && <button type="button" aria-pressed={pick === "mine"} onClick={() => setPick("mine")}>My estimate</button>}
            {d.slabs.map((s) => <button key={s} type="button" aria-pressed={pick === s || (!d.full && pick === "mine" && s === 30)} onClick={() => setPick(s)}>{s}%</button>)}
          </div>
          <p className="small" style={{ margin: 0 }} role="status">
            {d.basis === "estimate" && d.mine
              ? <>After-tax figures use <b>{d.tax_rate}%</b>: the tax on the next ₹10,000 of interest at your {fyLabel(d.mine.fy)} tax inputs ({d.mine.regime} regime, other income {inr(d.mine.income)}), with any rebate, surcharge and cess.</>
              : <>After-tax figures use <b>{d.tax_rate}%</b>: the {d.slab ?? 30}% slab with 4% cess.{d.full && pick === "mine" ? <> Save your income in the <Link className="link" to="/tax-report">tax report</Link> to use your own estimate.</> : null}</>}
          </p>
          {!d.full && <div className="banner"><span>After-tax yields at the rate from your own tax estimate (rebate, surcharge and cess included) are on the {d.plan} plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>}
        </section>

        <section className="card stack" style={{ gap: 10 }} aria-label="Market rates">
          <h2 className="h2">Treasury bills, government bonds and the repo rate</h2>
          {d.market_available ? table(d.market, "Market rates") : <p className="small muted" style={{ margin: 0 }}>The Reserve Bank's rates couldn't be read just now. They are read again every few hours.</p>}
          <AsOf parts={[["Read from the Reserve Bank", d.market_read_at]]} />
        </section>

        <section className="card stack" style={{ gap: 10 }} aria-label="Small savings">
          <h2 className="h2">Small savings, {d.small_savings.quarter}</h2>
          {table(d.small_savings.rows, "Small savings rates", (r) => r.c80 ? <div className="tiny muted">80C on the deposit (old regime)</div> : null)}
          <p className="tiny muted" style={{ margin: 0 }}>Rates for {dateOnly(d.small_savings.from)} to {dateOnly(d.small_savings.to)}, notified on {dateOnly(d.small_savings.notified)}. Source: {d.small_savings.source}. Reset every quarter.</p>
        </section>

        <section className="card stack" style={{ gap: 10 }} aria-label="Bonds">
          <h2 className="h2">RBI floating rate bond</h2>
          {table(d.bonds, "Floating rate bond", (r) => r.from ? <div className="tiny muted">{dateOnly(r.from)} to {dateOnly(r.to)}</div> : null)}
        </section>

        <section className="card stack" style={{ gap: 10 }} aria-label="Your deposits">
          <h2 className="h2">Your deposits</h2>
          {d.deposits.length === 0
            ? <p className="small muted" style={{ margin: 0 }}>Fixed and recurring deposits you add in <Link className="link" to="/money/net-worth">Net worth</Link> show here with their rate and interest after tax.</p>
            : (
              <div className="table-wrap">
                <table aria-label="Your deposits">
                  <thead><tr><th style={{ textAlign: "left" }}>Deposit</th><th>Rate</th><th>After tax</th><th>Interest to maturity</th><th>After tax</th></tr></thead>
                  <tbody>{d.deposits.map((x) => (
                    <tr key={x.id}>
                      <td style={{ textAlign: "left", minWidth: 180, whiteSpace: "normal" }}><b>{x.name}</b>
                        <div className="tiny muted">{x.kind === "fd" ? `${inr(x.principal)}, ${x.compounding === "simple" ? "simple interest" : `compounded ${x.compounding}`}` : `${inr(x.monthly)} a month`} · {x.matured ? "matured" : "matures"} {dateOnly(x.maturity)}</div></td>
                      <td className="num">{pctText(x.rate)}</td>
                      <td className="num">{pctText(x.after_tax)}</td>
                      <td className="num">{inr(x.interest)}</td>
                      <td className="num">{inr(x.interest_after_tax)}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
        </section>

        <details className="small card">
          <summary className="tiny" style={{ minHeight: 32, display: "flex", alignItems: "center", cursor: "pointer" }}>How the after-tax figures are worked out, and TDS</summary>
          <ul className="tiny muted" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
          <p className="tiny muted" style={{ margin: "6px 0 0" }}>{d.disclaimer} Market rates: {d.rbi_source}.</p>
        </details>
      </>}
    </div>
  );
}
