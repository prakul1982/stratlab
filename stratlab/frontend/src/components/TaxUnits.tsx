import { useState } from "react";
import { dateOnly, money, qty as qtyText, signClass } from "../lib/format";

/** Gold, silver, international and debt ETFs and gold bonds in one year: each sale under the head the law puts it,
 * from the server's instrument_kinds.other_year. Equity ETFs, REITs and InvITs are taxed like shares and sit with them. */
export type UnitSale = { key: string; kind: string; label: string; bought: string; sold: string; qty: number; cost: number; sale: number; gain: number;
  head: "slab" | "lt" | "exempt" | "old"; why: string };
export type Units = {
  rows: UnitSale[]; count: number; slab: { gains: number; losses: number; taxable: number };
  lt: { gains: number; losses: number; taxable: number; rate: number; tax: number }; exempt: number; old: number | null;
  carry_forward: { st: number; lt: number };
};

const inr = (v: number | null | undefined) => money(v, "INR", 0);
const HEADS: Record<UnitSale["head"], string> = { slab: "Short term, slab rate", lt: "Long term, 12.5%", exempt: "Exempt", old: "Old rules" };

export function UnitsCard({ units, notes, name, label }: { units: Units | null | undefined; notes: string[]; name: (k: string) => string; label: string }) {
  const [all, setAll] = useState(false);
  if (!units) return null;
  return (
    <section className="card stack" style={{ gap: 12 }} aria-label="ETFs and gold bonds">
      <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
        <h2 className="h2">ETFs and gold bonds under other rules</h2>
        <span className="tiny muted">{units.count} sale{units.count === 1 ? "" : "s"} in {label}</span>
      </div>
      <p className="small" style={{ margin: 0 }}>
        Gold, silver, international and debt ETFs and Sovereign Gold Bonds aren't taxed like shares. Short-term gains taxed at your slab
        rate: <b>{inr(units.slab.taxable)}</b>{units.slab.losses > 0 && <> (after {inr(units.slab.losses)} of losses)</>}. Long-term gains at 12.5% (section
        112, no exemption): <b>{inr(units.lt.taxable)}</b>, tax {inr(units.lt.tax)} before cess. Both are in the total tax estimate.
        {units.exempt ? <> Exempt (gold bonds redeemed at maturity): {inr(units.exempt)}.</> : null}
        {units.old != null && <> Sold before 23 Jul 2024 under the old long-term rules (indexation), not worked out here: {inr(units.old)}.</>}
        {(units.carry_forward.st > 0 || units.carry_forward.lt > 0) && <> Left to carry forward: {inr(units.carry_forward.st)} short-term and {inr(units.carry_forward.lt)} long-term loss.</>}
      </p>
      <div className="table-wrap">
        <table aria-label="ETF and gold bond sales">
          <thead><tr><th style={{ textAlign: "left" }}>Unit</th><th>Bought</th><th>Sold</th><th>Qty</th><th>Cost</th><th>Sale</th><th>Gain or loss</th><th style={{ textAlign: "left" }}>Head</th></tr></thead>
          <tbody>{(all ? units.rows : units.rows.slice(0, 20)).map((r, i) => (
            <tr key={i}>
              <td style={{ textAlign: "left" }}><b>{name(r.key)}</b> <span className={`badge kind-${r.kind.split("-")[0]}`}>{r.label}</span></td>
              <td className="num">{dateOnly(r.bought)}</td><td className="num">{dateOnly(r.sold)}</td><td className="num">{qtyText(r.qty)}</td>
              <td className="num">{inr(r.cost)}</td><td className="num">{inr(r.sale)}</td><td className={`num ${signClass(r.gain)}`}>{inr(r.gain)}</td>
              <td style={{ textAlign: "left", whiteSpace: "normal", minWidth: 160 }} className="small" title={r.why}>{HEADS[r.head]}<div className="tiny muted">{r.why}</div></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {units.rows.length > 20 && !all && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setAll(true)}>Show all {units.rows.length}</button>}
      {notes.length > 0 && <ul className="tiny muted" style={{ margin: 0, paddingLeft: 20 }}>{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
    </section>
  );
}
