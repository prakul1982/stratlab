import { Seg } from "./kit/Seg";
import { AUTO_USD_LINE, type PriceCur } from "../lib/priceCurrency";

/** The plans' "Prices in" switch, rupees or US dollars (owner, 16 Nov), always in view beside the prices; while dollars were picked by
 * the region rather than by the visitor, one line says so (never a silent guess). */
export function CurrencySwitch({ cur, auto, onChange }: { cur: PriceCur; auto: boolean; onChange: (c: PriceCur) => void }) {
  return (
    <div className="cur-switch" data-testid="cur-switch">
      <Seg label="Prices in" value={cur} onChange={(v) => onChange(v === "USD" ? "USD" : "INR")}
        options={[{ value: "INR", label: "₹ INR" }, { value: "USD", label: "$ USD" }]} />
      {auto && cur === "USD" && <span className="small muted" data-testid="cur-auto">{AUTO_USD_LINE}</span>}
    </div>
  );
}
