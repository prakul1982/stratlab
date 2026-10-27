import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { FEATURES, GOAL_ORDER, GOALS, resolve, type Goal } from "../lib/features";
import { PLAN_NAME, planOf } from "../lib/plans";
import { TileGrid } from "./TileGrid";
import "../pages/trade/trade.css";

const OPEN_KEY = "stratlab.explore.open";

/** Everything StratLab can do, grouped by the goal it serves and ordered by what the user came for, so the deeper
 * tools aren't hidden and nobody faces a wall of equal choices. Only the first group shows until "Show everything"
 * is pressed (remembered), so the page under it stays short. `hide` leaves out tools the page above already links to,
 * so a space's home offers each one once. `order`: a space home lists its own space's goals first. */
export function Explore({ title = "More you can do", skip = [], hide = [], order }: { title?: string; skip?: Goal[]; hide?: string[]; order?: "trade" | "invest" }) {
  const { notebooks, level, focus, me } = useApp();
  // a tool the plan doesn't include says which plan has it, on the tile, before the click (DP1-020)
  const lockedOn = (flag?: string) => (flag && me?.plan_info.features?.[flag] === false ? PLAN_NAME[planOf(flag)] : null);
  const nav = useNavigate();
  const loc = useLocation();
  const latest = notebooks?.[0] ? { id: notebooks[0].id } : null;
  const [all, setAll] = useState(() => { try { return localStorage.getItem(OPEN_KEY) === "1"; } catch { return false; } });
  const showAll = (on: boolean) => { setAll(on); try { localStorage.setItem(OPEN_KEY, on ? "1" : "0"); } catch { /* storage off */ } };
  // a card never points at the page it is on
  const here = loc.pathname + loc.search;
  const shown = FEATURES.filter((f) => f.home && f.goal && !hide.includes(f.id) && !(level === "new" && f.level === "advanced") && resolve(f.to, loc.pathname, latest) !== here);
  const goals = (GOAL_ORDER[order ?? focus ?? "both"] as Goal[]).filter((g) => !skip.includes(g) && shown.some((f) => f.goal === g));
  const open = (to: string) => {
    const dest = resolve(to, loc.pathname, latest);
    if (dest === loc.pathname + loc.search) { const box = document.getElementById("idea"); box?.scrollIntoView({ behavior: "smooth", block: "center" }); box?.focus(); }
    else nav(dest);
  };
  return (
    <section className="k-stack k-explore" aria-labelledby="explore-h">
      {/* no "Search everything" here: the menu's search box is on every page, and a second one read as another search (DD-002) */}
      <h2 id="explore-h" className="h2">{title}</h2>
      {goals.slice(0, all ? goals.length : 1).map((g) => {
        const items = shown.filter((f) => f.goal === g);
        return (
          <div key={g} className="k-stack">
            <div className="k-stack k-tight">
              <b>{GOALS[g].title}</b>
              <span className="small muted">{GOALS[g].sub}</span>
            </div>
            <TileGrid className="explore-grid">
              {items.map((f) => (
                <button key={f.id} className="k-linkcard explore-card" onClick={() => open(f.to)}>
                  <b>{f.title}</b>
                  <span className="small muted">{f.what}</span>
                  <span className="small explore-go">{lockedOn(f.flag) ? `On the ${lockedOn(f.flag)} plan →` : f.to.startsWith("@") && !latest ? "Starts with a notebook →" : "Open →"}</span>
                </button>
              ))}
            </TileGrid>
          </div>
        );
      })}
      {goals.length > 1 && (
        <button className="btn quiet sm k-btn-end" aria-expanded={all} onClick={() => showAll(!all)}>
          {all ? "Show less" : `Show ${shown.filter((f) => goals.slice(1).includes(f.goal!)).length} more tools`}
        </button>
      )}
    </section>
  );
}
