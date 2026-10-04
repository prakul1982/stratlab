import { asOf } from "../lib/format";
import type { Region } from "../lib/research";
import { survLabel, survList, useSurveillance } from "../lib/surveillance";
import { Info } from "./ui";

/** A stock's exchange surveillance flags as small factual badges ("LT-ASM 2", "T2T", "F&O ban"), with an (i) that
 * says what each of the exchange's measures is and the date of the list it comes from. Nothing for a stock on no
 * list, or for a US stock. `codes` are the row's own flags when the page already has them (screens). `plain` leaves
 * the (i) out, for badges inside a button (a search result), where the badge's title carries the list's name. */
export function SurvBadges({ region, symbol, codes, plain }: { region: Region | string | undefined; symbol: string; codes?: string[]; plain?: boolean }) {
  const v = useSurveillance(region === "IN");
  if (region !== "IN" || !v) return null;
  const mine = (codes ?? v.flags[symbol] ?? []).map((c) => [c, survLabel(v, symbol, c)] as const).filter(([, l]) => l);
  if (!mine.length) return null;
  return (
    <span className="surv" data-surveillance={symbol}>
      {mine.map(([c, l]) => <span key={c} className="surv-badge" title={`${l!.label} (exchange surveillance list)`}>{l!.short}</span>)}
      {!plain && <Info label={`What ${symbol}'s exchange surveillance flags mean`}>
        {mine.map(([c, l]) => {
          const list = survList(v, c);
          const when = asOf(list?.as_of);
          return (
            <span key={c} className="surv-line"><b>{l!.label}.</b> {l!.text}
              {when && <> List as of {when}{list?.failed ? "; it couldn't be refreshed since, so this is the last copy read" : ""}.</>}</span>
          );
        })}
        <span className="surv-line">{v.note}</span>
      </Info>}
    </span>
  );
}

/** "IN" for an Indian stock (the region the lists cover), from a picked instrument. */
export function survRegion(i: { market?: string; exchange?: string } | null | undefined): string | undefined {
  return i && (i.market === "IN" || (!i.market && (i.exchange === "NSE" || i.exchange === "BSE"))) ? "IN" : undefined;
}
