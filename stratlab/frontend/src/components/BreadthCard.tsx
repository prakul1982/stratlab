import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BROAD_GROUP, breadthApi, cardFigures, count, savedPick, share, shortDay, type BreadthView } from "../lib/breadth";
import { homeRegion } from "../lib/homeMarket";
import { Panel } from "./Research";
import { AsOf, PanelSkel } from "./ui";
import { Badge, Stat } from "./kit";
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
  const f = d && d !== "error" ? cardFigures(d) : null;
  return (
    <Panel title="Market breadth" right={<Link to="/invest/breadth" className="link">Charts →</Link>}>
      {d === null ? <PanelSkel figs label="Counting the market" />
        : d === "error" ? <p className="small muted">Breadth couldn't be opened just now. <Link className="link" to="/invest/breadth">Try the page</Link>.</p>
        : !f ? <p className="small muted">The first counts for {d.group.name} come after the next close.</p>
        : (
          <div className="k-stack" data-testid="breadth-card" data-live={f.live ? "1" : "0"}>
            <span className="eyebrow">{d.group.name} · <span data-testid="breadth-card-when">{f.when}</span> {f.live && <Badge tone="live">Live</Badge>}</span>
            <div className="k-stats">
              <Stat label="Rose / fell" value={`${count(f.adv)} / ${count(f.dec)}`} />
              <Stat label="Above 50-day average" value={share(f.pct50)} />
              {/* the live count has no new highs and lows: those stay the last close's, said so */}
              {f.live
                ? (d.today ? <Stat label="52-week highs / lows" value={`${count(d.today.highs.value)} / ${count(d.today.lows.value)}`} note={`Last close, ${shortDay(d.today.day)}`} /> : null)
                : <Stat label="52-week highs / lows" value={`${count(f.highs)} / ${count(f.lows)}`} />}
            </div>
            {!f.live && <AsOf parts={[["Prices", d.as_of]]} tz={marketTz(d.group.region)} />}
          </div>
        )}
    </Panel>
  );
}
