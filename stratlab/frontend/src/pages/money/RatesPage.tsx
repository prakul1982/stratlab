import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { asOf as asOfText, dateOnly, inr, pctPlain } from "../../lib/format";
import { Card, CardHead, ChipBar, DataTable, Disclosure, EmptyState, PageHeader, PlanNote, Skeleton, type Column } from "../../components/kit";

/* /money/rates: fixed-income rates and the yield after your tax: T-bill cut-offs, G-sec yields and the repo rate from the
 * Reserve Bank, this quarter's small savings rates with their tax treatment, the RBI floating rate bond, and your own
 * deposits from Net worth. Rates and arithmetic with their dates: never a ranking or a "best" deposit.
 * Built from the kit (components/kit), amounts from lib/format. */

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

const pctText = (v: number | null | undefined) => pctPlain(v, 2);
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

  const table = (rows: Row[], label: string, extra?: (r: Row) => ReactNode) => {
    const cols: Column<Row>[] = [
      { key: "what", header: "What", rowHeader: true, wrap: true, cell: (r) => <><b>{r.name}</b>{extra?.(r)}</> },
      { key: "rate", header: "Rate", numeric: true, cell: (r) => pctText(r.rate) },
      { key: "after", header: "After tax", numeric: true, cell: (r) => (r.after_tax == null ? "–" : pctText(r.after_tax)) },
      { key: "how", header: "Interest", wrap: true, cell: (r) => r.how },
      { key: "tax", header: "Tax", wrap: true, cell: (r) => `${d!.tax_text[r.tax]}${r.c80 && r.tax !== "eee" ? "; the deposit counts under 80C" : ""}` },
    ];
    return <DataTable label={label} columns={cols} rows={rows} rowKey={(r) => r.key} />;
  };
  const sub = (text: ReactNode) => <span className="k-sub-line">{text}</span>;

  const pickValue = pick === "mine" ? (d && !d.full ? "30" : "mine") : String(pick);
  const rateOptions = d ? [...(d.full ? [{ value: "mine", label: "My estimate" }] : []), ...d.slabs.map((s) => ({ value: String(s), label: `${s}%` }))] : [];

  const depCols: Column<Deposit>[] = [
    { key: "dep", header: "Deposit", rowHeader: true, wrap: true, cell: (x) => (
      <><b>{x.name}</b>{sub(<>{x.kind === "fd" ? `${inr(x.principal)}, ${x.compounding === "simple" ? "simple interest" : `compounded ${x.compounding}`}` : `${inr(x.monthly)} a month`} · {x.matured ? "matured" : "matures"} {dateOnly(x.maturity)}</>)}</>) },
    { key: "rate", header: "Rate", numeric: true, cell: (x) => pctText(x.rate) },
    { key: "after", header: "After tax", numeric: true, cell: (x) => pctText(x.after_tax) },
    { key: "int", header: "Interest to maturity", numeric: true, cell: (x) => inr(x.interest) },
    { key: "intat", header: "After tax", numeric: true, cell: (x) => inr(x.interest_after_tax) },
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow="Money · Plan" title="Rates and your yield after tax"
        lede="Treasury bills, government bonds, the repo rate, small savings and your own deposits, each beside what it comes to after your tax."
        asOf={d?.as_of} info={d ? <>Published rates with their dates, and arithmetic: not a ranking of where to put money. Market rates: {d.rbi_source}.</> : undefined} infoLabel="Where the rates come from" />

      {!d ? <Card><Skeleton label="Reading the rates" /></Card> : <>
        <Card label="Your tax rate">
          <CardHead title="Your tax rate" info="The tax rate that turns each rate into what you keep. Pick your own estimate from the tax report, or a slab." />
          <ChipBar label="Tax rate" options={rateOptions} value={pickValue} onChange={(v) => setPick(v === "mine" ? "mine" : Number(v))} />
          <p className="k-small" role="status">
            {d.basis === "estimate" && d.mine
              ? <>After-tax figures use <b>{d.tax_rate}%</b>: the tax on the next ₹10,000 of interest at your {fyLabel(d.mine.fy)} tax inputs ({d.mine.regime} regime, other income {inr(d.mine.income)}), with any rebate, surcharge and cess.</>
              : <>After-tax figures use <b>{d.tax_rate}%</b>: the {d.slab ?? 30}% slab with 4% cess.{d.full && pick === "mine" ? <> Save your income in the <Link className="link" to="/tax-report">tax report</Link> to use your own estimate.</> : null}</>}
          </p>
          {!d.full && <PlanNote>After-tax yields at the rate from your own tax estimate (rebate, surcharge and cess included) are on the {d.plan} plan.</PlanNote>}
        </Card>

        <Card label="Market rates">
          <CardHead title="Treasury bills, government bonds and the repo rate" info={d.market_read_at ? `Read from the Reserve Bank on ${asOfText(d.market_read_at)}.` : undefined} />
          {d.market_available ? table(d.market, "Market rates")
            : <EmptyState title="The Reserve Bank's rates couldn't be read just now">They are read again every few hours. Come back later.</EmptyState>}
        </Card>

        <Card label="Small savings">
          <CardHead title={`Small savings, ${d.small_savings.quarter}`} info={`Rates for ${dateOnly(d.small_savings.from)} to ${dateOnly(d.small_savings.to)}, notified on ${dateOnly(d.small_savings.notified)}. Source: ${d.small_savings.source}. Reset every quarter.`} />
          {table(d.small_savings.rows, "Small savings rates", (r) => (r.c80 ? sub("80C on the deposit (old regime)") : null))}
        </Card>

        <Card label="Bonds">
          <CardHead title="RBI floating rate bond" />
          {table(d.bonds, "Floating rate bond", (r) => (r.from ? sub(`${dateOnly(r.from)} to ${dateOnly(r.to)}`) : null))}
        </Card>

        <Card label="Your deposits">
          <CardHead title="Your deposits" />
          {d.deposits.length === 0
            ? <EmptyState title="No deposits yet" action={{ label: "Add one in Net worth", to: "/money/net-worth" }}>Fixed and recurring deposits you add in Net worth show here with their rate and interest after tax.</EmptyState>
            : <DataTable label="Your deposits" columns={depCols} rows={d.deposits} rowKey={(x) => x.id} />}
        </Card>

        <Card>
          <Disclosure summary="How the after-tax figures are worked out, and TDS">
            <ul className="k-list muted">{d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
            <p className="k-note">{d.disclaimer}</p>
          </Disclosure>
        </Card>
      </>}
    </div>
  );
}
