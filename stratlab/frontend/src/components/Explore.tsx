import { useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { FEATURES, resolve } from "../lib/features";
import { Search } from "./Icons";

/** Everything StratLab can do, one tap each, so the deeper tools aren't hidden behind a notebook. */
export function Explore({ title = "What you can do here" }: { title?: string }) {
  const { notebooks, level } = useApp();
  const nav = useNavigate();
  const loc = useLocation();
  const latest = notebooks?.[0] ? { id: notebooks[0].id } : null;
  return (
    <section className="stack" style={{ gap: 12 }} aria-labelledby="explore-h">
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 id="explore-h" className="h2">{title}</h2>
        <button className="btn quiet sm" onClick={() => window.dispatchEvent(new Event("stratlab:search"))}><Search size={16} />Search everything</button>
      </div>
      <div className="explore-grid">
        {FEATURES.filter((f) => f.home && !(level === "new" && f.level === "advanced")).map((f) => (
          <button key={f.id} className="card explore-card" onClick={() => {
            const to = resolve(f.to, loc.pathname, latest);
            if (to === loc.pathname + loc.search) { const box = document.getElementById("idea"); box?.scrollIntoView({ behavior: "smooth", block: "center" }); box?.focus(); }
            else nav(to);
          }}>
            <b>{f.title}</b>
            <span className="small muted">{f.what}</span>
            {f.to.startsWith("@") && !latest && <span className="small muted">Starts with a notebook</span>}
          </button>
        ))}
      </div>
    </section>
  );
}
