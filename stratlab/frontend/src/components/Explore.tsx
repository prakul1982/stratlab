import { useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { FEATURES, GOAL_ORDER, GOALS, resolve, type Goal } from "../lib/features";
import { Search } from "./Icons";

/** Everything StratLab can do, grouped by the goal it serves and ordered by what the user came for, so the deeper
 * tools aren't hidden and nobody faces a wall of equal choices. */
export function Explore({ title = "What you can do here", skip = [] }: { title?: string; skip?: Goal[] }) {
  const { notebooks, level, focus } = useApp();
  const nav = useNavigate();
  const loc = useLocation();
  const latest = notebooks?.[0] ? { id: notebooks[0].id } : null;
  const shown = FEATURES.filter((f) => f.home && f.goal && !(level === "new" && f.level === "advanced"));
  const open = (to: string) => {
    const dest = resolve(to, loc.pathname, latest);
    if (dest === loc.pathname + loc.search) { const box = document.getElementById("idea"); box?.scrollIntoView({ behavior: "smooth", block: "center" }); box?.focus(); }
    else nav(dest);
  };
  return (
    <section className="stack" style={{ gap: 18 }} aria-labelledby="explore-h">
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 id="explore-h" className="h2">{title}</h2>
        <button className="btn quiet sm" onClick={() => window.dispatchEvent(new Event("stratlab:search"))}><Search size={16} />Search everything</button>
      </div>
      {(GOAL_ORDER[focus ?? "both"] as Goal[]).filter((g) => !skip.includes(g)).map((g) => {
        const items = shown.filter((f) => f.goal === g);
        if (!items.length) return null;
        return (
          <div key={g} className="stack" style={{ gap: 10 }}>
            <div className="stack" style={{ gap: 2 }}>
              <b>{GOALS[g].title}</b>
              <span className="small muted">{GOALS[g].sub}</span>
            </div>
            <div className="explore-grid">
              {items.map((f) => (
                <button key={f.id} className="card explore-card" onClick={() => open(f.to)}>
                  <b>{f.title}</b>
                  <span className="small muted">{f.what}</span>
                  {f.to.startsWith("@") && !latest && <span className="small muted">Starts with a notebook</span>}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}
