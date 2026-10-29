import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BROAD_GROUP, breadthApi, cardDates, cardFigures, count, savedPick, share, withLive, type BreadthView } from "../lib/breadth";
import { homeRegion } from "../lib/homeMarket";
import { Panel } from "./Research";
import { AsOf, PanelSkel } from "./ui";
import { Stat, StatRow } from "./kit";
import { marketTz } from "../lib/format";
import { useMarketRefresh } from "../lib/marketLive";

/** Market breadth on the Invest home: the latest day's numbers for a market (every plan): the group last picked for it,
 * else the market's own group (the S&P 500 for the US), or its broad group while that one has no counts yet (R6O-007).
 * `region` is the market picked at the top of the page; without it, the reader's own market. */
export function BreadthCard({ region: picked }: { region?: "IN" | "US" }) {
  const [d, setD] = useState<BreadthView | null | "error">(null);
  const region = picked ?? homeRegion();
  useEffect(() => {
    // the reader's own market, whatever market a company page was last looked up in (R6O-007 residue, round 7)
    setD(null);
    const pick = savedPick(region);
    breadthApi.get(pick.group, "1y", true)
      .then((v) => (!v.today && !pick.picked && BROAD_GROUP[region] !== pick.group ? breadthApi.get(BROAD_GROUP[region], "1y", true) : v))
      .then(setD).catch(() => setD("error"));
  }, [region]);
  // India's counts are worked out every quarter hour while it trades (the server's live round): the card reads the newest each
  // minute, in place, keeping the shown counts when a read fails (LIVE-1). The US has daily counts only.
  useMarketRefresh(["IN"], () => {
    if (!d || d === "error") return;
    const group = d.group.id;
    breadthApi.live(group).then((x) => setD((cur) => withLive(cur, x, group))).catch(() => undefined);
  }, region === "IN" && d !== null && d !== "error");
  const f = d && d !== "error" ? cardFigures(d) : null;
  const dates = d && d !== "error" ? cardDates(d) : null;
  // the page opens on the group this card shows (or, before it has loaded, on this market), not the reader's own market
  const page = d && d !== "error" ? `/invest/breadth?group=${encodeURIComponent(d.group.id)}` : `/invest/breadth?region=${region}`;
  return (
    <Panel title={d && d !== "error" ? `Market breadth · ${d.group.name}` : "Market breadth"} right={<Link to={page} className="link">Charts →</Link>}>
      {d === null ? <PanelSkel figs label="Counting the market" />
        : d === "error" ? <p className="small muted">Breadth couldn't be opened just now. <Link className="link" to={page}>Try the page</Link>.</p>
        : !f ? <p className="small muted">The first counts for {d.group.name} come after the next close.</p>
        : (
          <div className="k-stack" data-testid="breadth-card" data-live={f.live ? "1" : "0"}>
            {/* VR5-002: "Live as of 15:30 IST" says it is live: no second "Live" pill beside it */}
            <span className="eyebrow">{d.group.name} · <span data-testid="breadth-card-when">{f.when}</span></span>
            <StatRow>
              <Stat label="Rose / fell" value={`${count(f.adv)} / ${count(f.dec)}`} note={dates?.counts} />
              <Stat label="Above 50-day average" value={share(f.pct50)} note={dates?.counts} />
              {/* the live count has no new highs and lows: those stay the last close's, said so */}
              {f.live
                ? (d.today ? <Stat label="52-week highs / lows" value={`${count(d.today.highs.value)} / ${count(d.today.lows.value)}`} note={dates?.highs} /> : null)
                : <Stat label="52-week highs / lows" value={`${count(f.highs)} / ${count(f.lows)}`} />}
            </StatRow>
            {!f.live && <AsOf parts={[["Prices", d.as_of]]} tz={marketTz(d.group.region)} />}
          </div>
        )}
    </Panel>
  );
}
