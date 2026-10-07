import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { FEATURES, GOAL_ORDER, GOALS, resolve, type Goal } from "../lib/features";
import { Search } from "./Icons";
import "../pages/trade/trade.css";

const OPEN_KEY = "stratlab.explore.open";

/** Everything StratLab can do, grouped by the goal it serves and ordered by what the user came for, so the deeper
 * tools aren't hidden and nobody faces a wall of equal choices. Only the first group shows until "Show everything"
 * is pressed (remembered), so the page under it stays short. `hide` leaves out tools the page above already links to,
 * so a space's home offers each one once. `order`: a space home lists its own space's goals first. */
export function Explore({ title = "What you can do here", skip = [], hide = [], order }: { title?: string; skip?: Goal[]; hide?: string[]; order?: "trade" | "invest" }) {
  const { notebooks, level, focus } = useApp();
  const nav = useNavigate();
  const loc = useLocation();
  const latest = notebooks?.[0] ? { id: notebooks[0].id } : null;
  const [all, setAll] = useState(() => { try { return localStorage.getItem(OPEN_KEY) === "1"; } catch { return false; } });
  const showAll = (on: boolean) => { setAll(on); try { localStorage.setItem(OPEN_KEY, on ? "1" : "0"); } catch { /* storage off */ } };
  const shown = FEATURES.filter((f) => f.home && f.goal && !hide.includes(f.id) && !(level === "new" && f.level === "advanced"));
  const goals = (GOAL_ORDER[order ?? focus ?? "both"] as Goal[]).filter((g) => !skip.includes(g) && shown.some((f) => f.goal === g));
  const open = (to: string) => {
    const dest = resolve(to, loc.pathname, latest);
    if (dest === loc.pathname + loc.search) { const box = document.getElementById("idea"); box?.scrollIntoView({ behavior: "smooth", block: "center" }); box?.focus(); }
    else nav(dest);
  };
  return (
    <section className="k-stack k-explore" aria-labelledby="explore-h">
      <div className="k-spread">
        <h2 id="explore-h" className="h2">{title}</h2>
        <button className="btn quiet sm" onClick={() => window.dispatchEvent(new Event("stratlab:search"))}><Search size={16} />Search everything</button>
      </div>
      {goals.slice(0, all ? goals.length : 1).map((g) => {
        const items = shown.filter((f) => f.goal === g);
        return (
          <div key={g} className="k-stack">
            <div className="k-stack k-tight">
              <b>{GOALS[g].title}</b>
              <span className="small muted">{GOALS[g].sub}</span>
            </div>
            <div className="explore-grid">
              {items.map((f) => (
                <button key={f.id} className="k-linkcard explore-card" onClick={() => open(f.to)}>
                  <b>{f.title}</b>
                  <span className="small muted">{f.what}</span>
                  {f.to.startsWith("@") && !latest && <span className="small muted">Starts with a notebook</span>}
                </button>
              ))}
            </div>
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
