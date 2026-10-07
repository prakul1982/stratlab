import { AssistantCards, AssistantNotice } from "../components/AssistantCard";
import { PageHeader } from "../components/kit";

/** /assistant: keys for Claude or ChatGPT, how to set them up, and every tool call they made. A feature of the Mine space. */
export function AssistantPage() {
  return (
    <div className="k-page">
      <PageHeader eyebrow="Mine · Connect an AI assistant" title="Connect an AI assistant"
        lede="Make a key so Claude or ChatGPT can use your StratLab: your watchlist, holdings, a company's facts, the watchlist scan, alerts, and paper sessions with their P&L." />
      <AssistantNotice />
      <AssistantCards />
    </div>
  );
}
