import { useState } from "react";
import { dateOnly, inr, qty as qtyText, signTone } from "../lib/format";
import { Card, CardHead, DataTable, type Column } from "./kit";

/** Gold, silver, international and debt ETFs and gold bonds in one year: each sale under the head the law puts it,
 * from the server's instrument_kinds.other_year. Equity ETFs, REITs and InvITs are taxed like shares and sit with them. */
export type UnitSale = { key: string; kind: string; label: string; bought: string; sold: string; qty: number; cost: number; sale: number; gain: number;
  head: "slab" | "lt" | "exempt" | "old"; why: string };
export type Units = {
  rows: UnitSale[]; count: number; slab: { gains: number; losses: number; taxable: number };
  lt: { gains: number; losses: number; taxable: number; rate: number; tax: number }; exempt: number; old: number | null;
  carry_forward: { st: number; lt: number };
};

const HEADS: Record<UnitSale["head"], string> = { slab: "Short term, slab rate", lt: "Long term, 12.5%", exempt: "Exempt", old: "Old rules" };
const tone = (v: number) => { const t = signTone(v); return t ? `k-${t}` : undefined; };

export function UnitsCard({ units, notes, name, label }: { units: Units | null | undefined; notes: string[]; name: (k: string) => string; label: string }) {
  const [all, setAll] = useState(false);
  if (!units) return null;
  const rows = (all ? units.rows : units.rows.slice(0, 20)).map((r, i) => ({ ...r, i }));
  const cols: Column<UnitSale & { i: number }>[] = [
    { key: "unit", header: "Unit", rowHeader: true, cell: (r) => <><b>{name(r.key)}</b> <span className={`badge kind-${r.kind.split("-")[0]}`}>{r.label}</span></> },
    { key: "bought", header: "Bought", numeric: true, cell: (r) => dateOnly(r.bought) },
    { key: "sold", header: "Sold", numeric: true, cell: (r) => dateOnly(r.sold) },
    { key: "qty", header: "Qty", numeric: true, cell: (r) => qtyText(r.qty) },
    { key: "cost", header: "Cost", numeric: true, cell: (r) => inr(r.cost) },
    { key: "sale", header: "Sale", numeric: true, cell: (r) => inr(r.sale) },
    { key: "gain", header: "Gain or loss", numeric: true, cell: (r) => <span className={tone(r.gain)}>{inr(r.gain)}</span> },
    { key: "head", header: "Head", wrap: true, cell: (r) => <span title={r.why}>{HEADS[r.head]}<span className="k-sub-line">{r.why}</span></span> },
  ];
  return (
    <Card label="ETFs and gold bonds">
      <CardHead title="ETFs and gold bonds under other rules" actions={<span className="k-note">{units.count} sale{units.count === 1 ? "" : "s"} in {label}</span>} />
      <p className="k-small">
        Gold, silver, international and debt ETFs and Sovereign Gold Bonds aren't taxed like shares. Short-term gains taxed at your slab
        rate: <b>{inr(units.slab.taxable)}</b>{units.slab.losses > 0 && <> (after {inr(units.slab.losses)} of losses)</>}. Long-term gains at 12.5% (section
        112, no exemption): <b>{inr(units.lt.taxable)}</b>, tax {inr(units.lt.tax)} before cess. Both are in the total tax estimate.
        {units.exempt ? <> Exempt (gold bonds redeemed at maturity): {inr(units.exempt)}.</> : null}
        {units.old != null && <> Sold before 23 Jul 2024 under the old long-term rules (indexation), not worked out here: {inr(units.old)}.</>}
        {(units.carry_forward.st > 0 || units.carry_forward.lt > 0) && <> Left to carry forward: {inr(units.carry_forward.st)} short-term and {inr(units.carry_forward.lt)} long-term loss.</>}
      </p>
      <DataTable label="ETF and gold bond sales" columns={cols} rows={rows} rowKey={(r) => String(r.i)} />
      {units.rows.length > 20 && !all && <button type="button" className="btn quiet sm k-btn-end" onClick={() => setAll(true)}>Show all {units.rows.length}</button>}
      {notes.length > 0 && <ul className="k-list muted">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
    </Card>
  );
}
