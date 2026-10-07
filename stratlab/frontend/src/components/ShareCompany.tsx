import { useState } from "react";
import { api, dataUrl } from "../lib/api";
import { useApp } from "../lib/app";
import { download, shareLink, siteUrl } from "../lib/share";
import { renderCompanyCard, type CompanyCard } from "./companyCard";
import { Share } from "./Icons";
import { track } from "../lib/analytics";

/** Share a company: draws its fact card, makes a public link that previews as the card (and opens the company's
 *  public page), then the phone's share sheet or, on a computer, the link copied with the image a click away. */
export function ShareCompanyButton({ region, symbol }: { region: "IN" | "US"; symbol: string }) {
  const { run, busy } = useShareCompany(region, symbol);
  return (
    <button className="btn quiet sm" onClick={run} disabled={busy} title="A card with this company's facts, and a link that previews as it">
      <Share size={16} /> {busy ? "Making the card…" : "Share"}
    </button>
  );
}

/** Make the company's fact card and share its link: a button runs it, or a page's own menu (a company page's More). */
export function useShareCompany(region: "IN" | "US", symbol: string) {
  const { notify, fail } = useApp();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const path = `/cards/company/${region}/${encodeURIComponent(symbol)}`;
      const card = await api<CompanyCard>(path);
      const blob = await renderCompanyCard(card, "light");
      const out = await api<{ token: string }>(path, { method: "POST", body: { image: await dataUrl(blob) } });
      const url = `${siteUrl()}/c/${out.token}`;
      const file = new File([blob], `stratlab-${card.symbol.toLowerCase()}-facts.png`, { type: "image/png" });
      const save = { label: "Save the image", run: () => download(blob, file.name) };
      const r = await shareLink({ url, title: `${card.name} on StratLab`, text: `${card.name} (${card.symbol}): price, 1-year range and key facts.`, file });
      if (r !== "cancelled") track("card shared", { kind: "company", region, channel: r });
      if (r === "copied") notify("Link copied. It shows as this company's fact card on WhatsApp, X and LinkedIn.", save);
      else if (r === "shown") notify(`Your link: ${url}`, save);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return { run, busy };
}
