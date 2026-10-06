import { AssistantCards, AssistantNotice } from "../components/AssistantCard";
import { PageHeader } from "../components/kit";

/** /assistant: keys for Claude or ChatGPT, how to set them up, and every tool call they made. A feature of the Mine space. */
export function AssistantPage() {
  return (
    <div className="k-page">
      <PageHeader eyebrow="AI assistant" title="AI assistant"
        lede="Use StratLab in Claude or ChatGPT: your watchlist, holdings, a company's facts, the watchlist scan, alerts, and paper sessions with their P&L." />
      <AssistantNotice />
      <AssistantCards />
    </div>
  );
}
