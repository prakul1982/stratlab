import { Link } from "react-router-dom";
import { inr, signTone } from "../lib/format";
import { Card, CardHead, PlanNote } from "./kit";

/** A year's US share sales in the tax report (worked out in Money · US stocks; their lines are already in the sales
 * and buckets above on plans with the US tax workings). */
export type UsYear = { count: number; st: number; lt: number; unpriced: number; fallback: boolean; allowed: boolean; plan?: string } | null | undefined;

const tone = (v: number) => { const t = signTone(v); return t ? `k-${t}` : undefined; };

export function UsTaxCard({ us, label, trades }: { us: UsYear; label: string; trades?: number }) {
  if (!us && !trades) return null;
  return (
    <Card label="US stocks">
      <CardHead title="US stocks, in Indian tax" />
      {!us ? <p className="k-small">No US share sales in {label}.</p> : (
        <>
          <p className="k-small">
            {us.count} sale{us.count === 1 ? "" : "s"} in {label}: short-term <b className={tone(us.st)}>{inr(us.st)}</b> (held 24 months or less, at your slab
            rate) and long-term <b className={tone(us.lt)}>{inr(us.lt)}</b> (12.5% under section 112, no ₹1.25 lakh exemption), in rupees at SBI's TT buying rate
            on the last day of the month before each purchase and sale (Rule 115).
          </p>
          {us.allowed ? <p className="k-note">They are in the sales and the set-off above, under "foreign shares".</p>
            : <PlanNote>They aren't in the estimate above: the US tax workings are on the {us.plan ?? "Pro"} plan.</PlanNote>}
          {us.unpriced > 0 && <p className="k-note">{us.unpriced} sale{us.unpriced === 1 ? " has" : "s have"} no rupee rate yet and {us.unpriced === 1 ? "isn't" : "aren't"} counted.</p>}
        </>
      )}
      <p className="k-note">US dividends, the foreign tax credit (Form 67, due by the end of the assessment year) and Schedule FA (the calendar year's foreign assets, filed with the return) are in <Link className="link" to="/money/us-tax">US stocks</Link>; every schedule for the return is in the <Link className="link" to="/money/itr">ITR-ready export</Link>.</p>
    </Card>
  );
}
