import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BROAD_GROUP, breadthApi, cardFigures, cardTable, savedPick, withLive, type BreadthView, type CardRow } from "../lib/breadth";
import { homeRegion } from "../lib/homeMarket";
import { Panel } from "./Research";
import { AsOf, PanelSkel } from "./ui";
import { DataTable, type Column } from "./kit";
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
  const table = d && d !== "error" ? cardTable(d) : null;
  const columns: Column<CardRow>[] = table ? [
    { key: "k", header: "Measure", rowHeader: true, cell: (r) => r.k },
    { key: "now", header: table.nowHead, numeric: true, brief: true, cell: (r) => r.now ?? <span className="k-muted">At the close</span> },
    ...(table.beforeHead ? [{ key: "before", header: table.beforeHead, numeric: true, cell: (r: CardRow) => r.before ?? "–" }] : []),
  ] : [];
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
            {/* TABLE-SWEEP (owner, 29 Oct: "stat tiles with 'vs yesterday' lines" are a table): the three counts as rows; LIVE4-008: the newest
                count and the close before it each in a column headed with its day, so no figure sits under another day's header */}
            {/* on a phone two short lines a measure (the newest count at the right, the close before under it), not a card each */}
            {table && <DataTable stack compact label={`Market breadth, ${d.group.name}`} columns={columns} rows={table.rows} rowKey={(r) => r.id} />}
            {!f.live && <AsOf parts={[["Prices", d.as_of]]} tz={marketTz(d.group.region)} />}
          </div>
        )}
    </Panel>
  );
}
