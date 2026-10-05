import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { signClass } from "../lib/format";
import { crore, dayName, missingWhy, ratio, sides, signed, type Summary } from "../lib/positioning";
import { vixChange, vixNum } from "../lib/vix";
import { Fig, PanelSkel } from "./ui";
import { useVix } from "./VixPanel";

/** The newest positioning numbers in a few lines (FII index futures, the FII and DII cash flows, NIFTY's PCR, India
 * VIX), for the Trade home and the Options page. */
export function PositioningCard() {
  const [s, setS] = useState<Summary | null | "error">(null);
  const vix = useVix();
  const vq = vix && vix !== "error" ? vix : null;
  useEffect(() => { api<Summary>("/trade/positioning?brief=1").then(setS).catch(() => setS("error")); }, []);
  const fii = s && s !== "error" ? s.participants.oi.find((r) => r.id === "fii") : undefined;
  const nifty = s && s !== "error" ? s.pcr?.find((r) => r.name === "NIFTY") : undefined;
  return (
    <section className="card stack pos-card" style={{ gap: 10 }} aria-labelledby="pos-card-h" data-testid="positioning-card">
      <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
        <h2 id="pos-card-h" className="h3">Positioning</h2>
        <Link to="/trade/positioning" className="link">Participants, flows and PCR →</Link>
      </div>
      {s === null ? <PanelSkel figs label="Reading the newest numbers" />
        : s === "error" ? <p className="small muted">The positioning numbers couldn't be read just now. <Link className="link" to="/trade/positioning">Open the page</Link>.</p>
        : (
          <div className="space-figs">
            <Fig label="FII index futures, net" value={fii?.fut_idx_net != null ? signed(fii.fut_idx_net as number) : null} missing={missingWhy(s.participants)} noteTone=""
              note={(fii?.fut_idx_net_chg != null || fii?.fut_idx_long_pct != null) && <>
                {fii?.fut_idx_net_chg != null && <span className={signClass(fii.fut_idx_net_chg as number)}>{signed(fii.fut_idx_net_chg as number)} from the day before</span>}
                {fii?.fut_idx_net_chg != null && fii?.fut_idx_long_pct != null && <br />}
                {fii?.fut_idx_long_pct != null && <span className="muted" data-testid="pos-card-sides">{sides(fii.fut_idx_long_pct as number, fii.fut_idx_short_pct as number)}</span>}
              </>} />
            <Fig label="FII/FPI cash, net" value={s.cash.fii?.net != null ? crore(s.cash.fii.net, true) : null} missing={missingWhy(s.cash)} missingId="pos-card-cash-reason"
              note={s.cash.dii?.net != null && `DII ${crore(s.cash.dii.net, true)}`} />
            <Fig label="NIFTY PCR (open interest)" value={nifty?.pcr_oi != null ? ratio(nifty.pcr_oi) : null} missing="Not recorded yet"
              note={nifty?.expiry && `Expiry ${dayName(nifty.expiry)}`} />
            <Fig label="India VIX" value={vq?.value != null ? <span data-testid="pos-card-vix">{vixNum(vq.value)}</span> : null}
              missing={vix === null ? "Reading…" : "Not available"}
              note={vq && (vixChange(vq.quote) ?? (vq.percentile.percentile != null ? `Higher than ${Math.round(vq.percentile.percentile)}% of the past year` : null))} />
          </div>
        )}
      {s && s !== "error" && (
        <p className="tiny muted">
          {s.participants.as_of ? `Participants as of ${dayName(s.participants.as_of)}` : "Participant numbers not published yet"}
          {s.cash.as_of ? ` · cash flows as of ${dayName(s.cash.as_of)}` : ""}. Exchange data; facts, not advice.
        </p>
      )}
    </section>
  );
}
