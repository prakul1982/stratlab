/* The customer and supplier map (lane b2): the company card's answer (/research/links/{region}/{symbol}), the theme view's
 * (/research/links/theme) and the Admin queue's (/admin/supply-links), with the small pure helpers the components and the unit
 * tests share. Facts as filed: each link is a sentence a filing said on its date. */

export type LinkGroup = "names_customers" | "named_supplier_by" | "names_suppliers" | "named_customer_by";
export interface CompanyLink {
  id: string; group: LinkGroup; relation: string; name: string; symbol: string | null; region: "IN" | "US";
  basis: string; amount: string | null; quote: string; said_on: string | null; doc_url: string; doc_title: string | null;
  method: string | null; as_filed: boolean;
}
export interface CompanyLinks {
  region: "IN" | "US"; symbol: string; items: CompanyLink[]; total: number; locked: number; full: boolean; csv: boolean;
  plan_for_all: string; plan_for_csv: string; note: string;
}
export interface ThemeLinks {
  available: boolean; allowed: boolean; members: number; links?: number; plan?: string;
  layers?: { from: string; to: string; links: number }[];
  edges?: { supplier: string; customer: string; supplier_layer: string; customer_layer: string; quote: string; said_on: string | null; doc_url: string; stated_by: string }[];
  outside?: { name: string; symbol: string | null; links: number; members: string[] }[];
}
export interface QueueRow {
  id: string; region: string; stated_by: string; counterparty: string; direction: string; quote: string; said_on: string | null; doc_url: string;
  candidates: { symbol: string; name: string | null }[];
}
export interface SupplyAdmin { on: boolean; ai_cap: number; ai_used: number; queue: QueueRow[]; waiting: number }

/** The card's sections, in this order; one with no link is left out. */
export const GROUPS: { id: LinkGroup; title: string }[] = [
  { id: "names_customers", title: "Names as customers" }, { id: "named_supplier_by", title: "Named as a supplier by" },
  { id: "names_suppliers", title: "Names as suppliers" }, { id: "named_customer_by", title: "Named as a customer by" }];

/** The links of one group, in the order the server gave (newest first). */
export const inGroup = (items: CompanyLink[], g: LinkGroup) => items.filter((i) => i.group === g);

/** "2 more links are on the Basic plan" for the rows a plan doesn't show. */
export function lockedText(n: number, plan: string) {
  return `${n} more link${n === 1 ? " is" : "s are"} on the ${plan} plan, each with its quote and source.`;
}

/** The facts line under a name: "Order win · Rs 450 crore". */
export function factsLine(i: CompanyLink) {
  return [i.basis, i.amount].filter(Boolean).join(" · ");
}

/** The CSV rows the Pro download holds: the same facts the card shows. */
export const CSV_HEAD = ["Section", "Company", "Symbol", "Basis", "Amount", "Said on", "Quote", "Document", "Link"];
export function csvRows(items: CompanyLink[]) {
  return items.map((i) => [i.relation, i.name, i.symbol ?? "", i.basis, i.amount ?? "", i.said_on ?? "", i.quote, i.doc_title ?? "", i.doc_url]);
}
