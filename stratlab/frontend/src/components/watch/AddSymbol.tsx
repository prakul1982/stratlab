/* Adding to a list (MW-1): the market, then the instrument search every other page uses (with its own popular picks for that market). */
import { useState } from "react";
import { InstrumentSearch } from "../InstrumentSearch";
import { Select } from "../kit/Form";
import { useApp } from "../../lib/app";
import { homeRegion } from "../../lib/homeMarket";
import type { Instrument } from "../../lib/types";
import { acceptable, itemOf, MARKET_NAME, type WatchItem } from "../../lib/watch";

/** The markets a list can hold, in the order the app lists them (your own CSV can't be charted live, so it isn't one). */
const MARKET_IDS = ["IN", "US", "CRYPTO", "FX", "CMDTY", "MCX", "CDS", "UK", "EU", "JP"];

export function AddSymbol({ onAdd }: { onAdd: (it: WatchItem) => void }) {
  const { markets } = useApp();
  const [market, setMarket] = useState<string>(homeRegion());              // the reader's own market first
  const m = markets.find((x) => x.id === market);
  const offered = MARKET_IDS.filter((id) => markets.some((x) => x.id === id));
  const pick = (i: Instrument) => { const it = itemOf(i); if (it) onAdd(it); };
  return (
    <div className="mw-add k-stack snug" aria-label="Add to this list">
      <div className="mw-add-row">
        <Select small label="Market" value={market} onChange={setMarket} options={(offered.length ? offered : MARKET_IDS).map((id) => ({ value: id, label: markets.find((x) => x.id === id)?.name ?? MARKET_NAME[id] ?? id }))} />
      </div>
      {m && <InstrumentSearch market={m} onPick={pick} compact noNote accept={acceptable} label={`Search ${m.name} to add`}
        placeholder={market === "IN" ? "A stock, ETF or index: RELIANCE, NIFTY 50" : undefined} />}
    </div>
  );
}
