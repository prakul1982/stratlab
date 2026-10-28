import { useApp } from "../lib/app";
import { AdUnit } from "./AdUnit";

/** The one ad slot inside the app (ADS-1): under an AI answer, for Free accounts only. Basic and Pro see nothing here, and nothing
 * shows until the account's plan is known. The plan is the one the app already uses everywhere (`me.plan`: what the account
 * can do now, the owner's "View as" included), so a launch offer that gives everyone Pro's features gives them no ads too.
 * With ads off, or after "No thanks", a StratLab card holds the place. `seed` (a company's symbol) picks the card. */
export function AiAd({ seed }: { seed: string }) {
  const { me } = useApp();
  return <AdUnit slot="ai" plan={me?.plan ?? null} seed={seed} />;
}
