import { ImportStrategy } from "../components/ImportStrategy";
import { Card, CardHead, PageHeader } from "../components/kit";
import { useCreateNotebook } from "./Home";
import "./trade/trade.css";

/* /import: bring a strategy in from a file or text. Built from the kit (components/kit). */

const ROUTES: [string, string][] = [
  ["Rules on one stock, index, coin or pair", "A notebook you can backtest, check for luck, then paper trade."],
  ["Rules that scan a list of stocks", "A notebook set up on that group (NIFTY 50, F&O stocks, your own list), sharing one pot of capital, and paper-traded as a group."],
  ["An option structure", "Straddles, strangles, condors or any legs open in the Options tab for live paper trading."],
];

export function ImportPage() {
  const create = useCreateNotebook(null);
  return (
    <div className="k-page k-narrow">
      <PageHeader eyebrow="Trade · Build and test" title="Import a strategy"
        lede="Drop in a strategy you already run: a config file, Pine Script, Python, MetaTrader, AmiBroker, a StratLab export, or plain words. StratLab works out what it is and sets it up in the right place." />
      <Card label="Where an import goes">
        <CardHead title="Where it ends up" info="StratLab reads what you bring and puts it in the place that fits. Anything that can't be carried over, such as order types, spread filters or broker logins, is listed on the notebook so nothing is silently dropped." />
        <ul className="k-routes">
          {ROUTES.map(([a, b]) => <li key={a}><b>{a}</b><span className="k-small k-muted">{b}</span></li>)}
        </ul>
      </Card>
      <Card label="Import">
        <CardHead title="Bring it in" />
        <ImportStrategy onBuilt={create} />
      </Card>
    </div>
  );
}
