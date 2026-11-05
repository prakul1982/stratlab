/* Which companies a calendar or Invest home opens on: every company, or only the person's own stocks (watchlist, holdings, notebooks
 * and paper sessions). Owner, 5 Nov: "in calendar show all companies first not my stocks, and do this everywhere ... give a global option".
 * The account keeps the choice (Settings → Experience, and the welcome question asks it once); every company is the default. A page's
 * own switch changes only that page, kept in its address (?scope=all|mine), so a link still opens what it showed (useCompanyScope).
 * The pure part, here, is what the unit tests import. */
import type { Me } from "./types";

export type CompanyScope = "all" | "mine";

/** The two choices, every company first (the default), in the words every page's switch uses. */
export const SCOPE_OPTIONS: { value: CompanyScope; label: string }[] = [{ value: "all", label: "All companies" }, { value: "mine", label: "My stocks" }];

/** What each choice does, in a line under the switch (Settings, the welcome question). */
export const COMPANIES_HINT: Record<CompanyScope, string> = {
  all: "The results, corporate actions, all-dates and filings pages and Invest home open on every company, yours marked.",
  mine: "Those pages open on your own stocks: your watchlist, holdings, notebooks and paper sessions.",
};

/** The account's choice: only its own stocks when it said so, else every company. */
export const companiesPref = (me: Pick<Me, "prefs"> | null | undefined): CompanyScope => (me?.prefs?.companies === "mine" ? "mine" : "all");
