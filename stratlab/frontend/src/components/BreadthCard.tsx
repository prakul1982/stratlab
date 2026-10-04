import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { breadthApi, count, savedPick, share, type BreadthView } from "../lib/breadth";
import { Panel } from "./Research";
import { AsOf, PanelSkel } from "./ui";

/** Market breadth on the Invest home: the latest day's numbers for the group last picked (every plan). */
export function BreadthCard() {
  const [d, setD] = useState<BreadthView | null | "error">(null);
  useEffect(() => { breadthApi.get(savedPick().group, "1y", true).then(setD).catch(() => setD("error")); }, []);
  return (
    <Panel title="Market breadth" right={<Link to="/invest/breadth" className="link">Charts →</Link>}>
      {d === null ? <PanelSkel figs label="Counting the market" />
        : d === "error" ? <p className="small muted">Breadth couldn't be opened just now. <Link className="link" to="/invest/breadth">Try the page</Link>.</p>
        : !d.today ? <p className="small muted">The first counts for {d.group.name} come after the next close.</p>
        : (
          <div className="stack" style={{ gap: 10 }} data-testid="breadth-card">
            <span className="eyebrow">{d.group.name}</span>
            <div className="space-figs">
              <div className="space-fig"><span className="tiny muted">Rose / fell</span><b className="num">{count(d.today.adv.value)} / {count(d.today.dec.value)}</b></div>
              <div className="space-fig"><span className="tiny muted">Above 50-day average</span><b className="num">{share(d.today.pct50.value)}</b></div>
              <div className="space-fig"><span className="tiny muted">52-week highs / lows</span><b className="num">{count(d.today.highs.value)} / {count(d.today.lows.value)}</b></div>
            </div>
            <AsOf parts={[["Prices", d.as_of]]} />
          </div>
        )}
    </Panel>
  );
}
