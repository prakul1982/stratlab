import { Link } from "react-router-dom";
import { money, signClass } from "../lib/format";

/** A year's US share sales in the tax report (worked out in Money · US stocks; their lines are already in the sales
 * and buckets above on plans with the US tax workings). */
export type UsYear = { count: number; st: number; lt: number; unpriced: number; fallback: boolean; allowed: boolean; plan?: string } | null | undefined;

const inr = (v: number) => money(v, "INR", 0);

export function UsTaxCard({ us, label, trades }: { us: UsYear; label: string; trades?: number }) {
  if (!us && !trades) return null;
  return (
    <section className="card stack" style={{ gap: 10 }} aria-label="US stocks">
      <h2 className="h2">US stocks, in Indian tax</h2>
      {!us ? <p className="small" style={{ margin: 0 }}>No US share sales in {label}.</p> : (
        <>
          <p className="small" style={{ margin: 0 }}>
            {us.count} sale{us.count === 1 ? "" : "s"} in {label}: short-term <b className={signClass(us.st)}>{inr(us.st)}</b> (held 24 months or less, at your slab
            rate) and long-term <b className={signClass(us.lt)}>{inr(us.lt)}</b> (12.5% under section 112, no ₹1.25 lakh exemption), in rupees at SBI's TT buying rate
            on the last day of the month before each purchase and sale (Rule 115).
          </p>
          {us.allowed ? <p className="tiny muted" style={{ margin: 0 }}>They are in the sales and the set-off above, under "foreign shares".</p>
            : <p className="small" style={{ margin: 0 }}>They aren't in the estimate above: the US tax workings are on the {us.plan ?? "Pro"} plan. <Link className="link" to="/plans">See plans</Link></p>}
          {us.unpriced > 0 && <p className="tiny muted" style={{ margin: 0 }}>{us.unpriced} sale{us.unpriced === 1 ? " has" : "s have"} no rupee rate yet and {us.unpriced === 1 ? "isn't" : "aren't"} counted.</p>}
        </>
      )}
      <p className="tiny muted" style={{ margin: 0 }}>US dividends, the foreign tax credit (Form 67, due by the end of the assessment year) and Schedule FA (the calendar year's foreign assets, filed with the return) are in <Link className="link" to="/money/us-tax">US stocks</Link>; every schedule for the return is in the <Link className="link" to="/money/itr">ITR-ready export</Link>.</p>
    </section>
  );
}
