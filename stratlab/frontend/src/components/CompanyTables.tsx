import type { Region } from "../lib/companyTables";
import { PeersCard } from "./CompanyPeers";
import { StatementsCard } from "./CompanyStatements";
import { ShareholdingCard } from "./ShareholdingHistory";

/* Lane c-f2: a company's Peers, Financial statements and Shareholding history, one under the other, on the company page and the deep
 * dive. Each card reads its own figures and says what a plan doesn't include. `ids` prefixes the cards' ids where a page has its own. */
export function CompanyTables({ region, symbol, delisted = false, ids = "co" }: { region: Region; symbol: string; delisted?: boolean; ids?: string }) {
  return (
    <>
      {!delisted && <PeersCard region={region} symbol={symbol} id={`${ids}-peers`} />}
      <StatementsCard region={region} symbol={symbol} id={`${ids}-statements`} />
      <ShareholdingCard region={region} symbol={symbol} id={`${ids}-holding-history`} />
    </>
  );
}
