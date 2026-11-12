import { Link } from "react-router-dom";
import { companySearch, type DocRegion } from "../lib/docSearch";

/** The company page's way into the filings search, scoped to this company's documents (pages/DocSearchPage.tsx). */
export function DocSearchLink({ region, symbol }: { region: DocRegion; symbol: string }) {
  return <Link className="btn quiet sm" to={companySearch(region, symbol)} data-testid="doc-search-link">Search its documents</Link>;
}
