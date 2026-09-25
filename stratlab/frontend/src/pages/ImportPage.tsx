import { ImportStrategy } from "../components/ImportStrategy";
import { useCreateNotebook } from "./Home";

const ROUTES: [string, string][] = [
  ["Rules on one stock, index, coin or pair", "A notebook you can backtest, check for luck, then paper trade."],
  ["Rules that scan a list of stocks", "A notebook set up on that group (NIFTY 50, F&O stocks, your own list), sharing one pot of capital, and paper-traded as a group."],
  ["An option structure", "Straddles, strangles, condors or any legs open in the Options tab for live paper trading."],
];

export function ImportPage() {
  const create = useCreateNotebook(null);
  return (
    <div className="stack" style={{ gap: 22, maxWidth: 820 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Any market · any format</span>
        <h1 className="serif" style={{ fontSize: "clamp(30px, 4vw, 42px)", fontWeight: 400, letterSpacing: "-0.02em" }}>Import a strategy</h1>
        <p className="muted" style={{ maxWidth: "64ch" }}>
          Drop in a strategy you already run: a config file, Pine Script, Python, MetaTrader, AmiBroker, a StratLab export, or plain words.
          StratLab works out what it is and sets it up in the right place.
        </p>
      </div>
      <ul className="route-list">
        {ROUTES.map(([a, b]) => <li key={a}><b>{a}</b><span className="small muted">{b}</span></li>)}
      </ul>
      <section className="card stack" style={{ gap: 14 }}>
        <ImportStrategy onBuilt={create} />
      </section>
      <p className="small muted">Anything that can't be carried over, such as order types, spread filters or broker logins, is listed on the notebook so nothing is silently dropped.</p>
    </div>
  );
}
