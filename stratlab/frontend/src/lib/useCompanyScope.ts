/* A page's companies (lib/companyScope): what its address says, else the account's choice. */
import { useSearchParams } from "react-router-dom";
import { useApp } from "./app";
import { companiesPref, type CompanyScope } from "./companyScope";

/** A page's companies: what its address says (`param`, "scope" unless named), else the account's choice. The setter keeps the page's own
 *  choice in the address, written out either way, so the account's default never overrides what the page shows. */
export function useCompanyScope(param = "scope"): [CompanyScope, (s: string, also?: (p: URLSearchParams) => void) => void] {
  const { me } = useApp();
  const [params, setParams] = useSearchParams();
  const here = params.get(param);
  const scope: CompanyScope = here === "all" || here === "mine" ? here : companiesPref(me);
  const set = (s: string, also?: (p: URLSearchParams) => void) => {
    const p = new URLSearchParams(params);
    p.set(param, s === "mine" ? "mine" : "all");
    also?.(p);
    setParams(p, { replace: true });
  };
  return [scope, set];
}
