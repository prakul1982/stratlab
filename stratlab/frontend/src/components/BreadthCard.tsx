import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BROAD_GROUP, breadthApi, count, savedPick, share, type BreadthView } from "../lib/breadth";
import { homeRegion } from "../lib/homeMarket";
import { Panel } from "./Research";
import { AsOf, PanelSkel } from "./ui";
import { Stat } from "./kit";
import { marketTz } from "../lib/format";

/** Market breadth on the Invest home: the latest day's numbers for the reader's market (every plan): the group last
 * picked for it, else the market's own group, or its broad group while that one has no counts yet (R6O-007). */
export function BreadthCard() {
  const [d, setD] = useState<BreadthView | null | "error">(null);
  useEffect(() => {
    // the reader's own market, whatever market a company page was last looked up in (R6O-007 residue, round 7)
    const region = homeRegion();
    const pick = savedPick(region);
    breadthApi.get(pick.group, "1y", true)
      .then((v) => (!v.today && !pick.picked && BROAD_GROUP[region] !== pick.group ? breadthApi.get(BROAD_GROUP[region], "1y", true) : v))
      .then(setD).catch(() => setD("error"));
  }, []);
  return (
    <Panel title="Market breadth" right={<Link to="/invest/breadth" className="link">Charts →</Link>}>
      {d === null ? <PanelSkel figs label="Counting the market" />
        : d === "error" ? <p className="small muted">Breadth couldn't be opened just now. <Link className="link" to="/invest/breadth">Try the page</Link>.</p>
        : !d.today ? <p className="small muted">The first counts for {d.group.name} come after the next close.</p>
        : (
          <div className="k-stack" data-testid="breadth-card">
            <span className="eyebrow">{d.group.name}</span>
            <div className="k-stats">
              <Stat label="Rose / fell" value={`${count(d.today.adv.value)} / ${count(d.today.dec.value)}`} />
              <Stat label="Above 50-day average" value={share(d.today.pct50.value)} />
              <Stat label="52-week highs / lows" value={`${count(d.today.highs.value)} / ${count(d.today.lows.value)}`} />
            </div>
            <AsOf parts={[["Prices", d.as_of]]} tz={marketTz(d.group.region)} />
          </div>
        )}
    </Panel>
  );
}
