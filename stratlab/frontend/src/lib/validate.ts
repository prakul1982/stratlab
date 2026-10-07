/** Checking what's typed in a form before it's sent, and reading the server's own checks back onto the fields, so a
 * problem is said under the box it belongs to, with the limit named ("Enter at most 1,00,00,00,000"), instead of a
 * toast saying something somewhere is out of range. Pure functions (tested in unit/review-r1.test.mjs). */

export type Limits = {
  /** The lowest value allowed; `above: true` makes it "more than". */
  min?: number; above?: boolean;
  max?: number;
  whole?: boolean;
  optional?: boolean;
  /** Written in front of the limit in a message: "₹", "$"; or after it: "%". */
  unit?: string;
};

/** A limit as the message writes it: Indian grouping, the unit in place ("₹1,00,000", "60%"). */
export function limitText(v: number, unit = ""): string {
  const n = v.toLocaleString("en-IN", { maximumFractionDigits: 4 });
  return unit === "%" ? `${n}%` : unit === "% / yr" ? `${n}% a year` : unit ? `${unit}${n}` : n;
}

/** What's wrong with a number typed in a box, or null when it's fine. Commas are allowed ("1,00,000"). */
export function numberProblem(text: string, lim: Limits = {}): string | null {
  const t = text.trim().replace(/,/g, "");
  if (!t) return lim.optional ? null : "Fill this in.";
  const n = Number(t);
  if (!Number.isFinite(n)) return "Enter a number, like 10.";
  if (lim.whole && !Number.isInteger(n)) return "Enter a whole number.";
  if (lim.min != null && (lim.above ? n <= lim.min : n < lim.min)) {
    return lim.above ? `Enter more than ${limitText(lim.min, lim.unit)}.` : `Enter ${limitText(lim.min, lim.unit)} or more.`;
  }
  if (lim.max != null && n > lim.max) return `Enter at most ${limitText(lim.max, lim.unit)}.`;
  return null;
}

/** The problems of a whole form: field key → message, only for the fields with one. */
export function problems<K extends string>(checks: Record<K, string | null>): Partial<Record<K, string>> {
  const out: Partial<Record<K, string>> = {};
  for (const k of Object.keys(checks) as K[]) if (checks[k]) out[k] = checks[k]!;
  return out;
}

type Invalid = { loc?: (string | number)[]; type?: string; msg?: string; ctx?: Record<string, unknown> };

/** One of the server's checks (a 422's list) in plain words, with its limit. */
export function invalidText(it: Invalid): string {
  const c = it.ctx ?? {};
  const num = (k: string) => (typeof c[k] === "number" ? limitText(c[k] as number) : String(c[k] ?? ""));
  switch (it.type) {
    case "less_than_equal": return `Enter at most ${num("le")}.`;
    case "less_than": return `Enter less than ${num("lt")}.`;
    case "greater_than_equal": return `Enter ${num("ge")} or more.`;
    case "greater_than": return `Enter more than ${num("gt")}.`;
    case "string_too_long": return `Use at most ${num("max_length")} characters.`;
    case "string_too_short": return "Fill this in.";
    case "missing": return "Fill this in.";
    case "float_parsing": case "int_parsing": case "float_type": case "int_type": return "Enter a number, like 10.";
    case "int_from_float": return "Enter a whole number.";
    default: return "Check this value.";
  }
}

/** The field a server check is about: the last name in its location ("body", "items", 0, "qty" → "qty"). */
export const invalidField = (it: Invalid): string | null => [...(it.loc ?? [])].reverse().find((x): x is string => typeof x === "string" && x !== "body") ?? null;

/** The server's 422 list as field → message (the first problem of each field). */
export function serverProblems(items: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!Array.isArray(items)) return out;
  for (const it of items as Invalid[]) {
    const f = invalidField(it);
    if (f && !out[f]) out[f] = invalidText(it);
  }
  return out;
}

/** A field's key in words for a message that can't sit under its box ("tenure_months" → "tenure months"). */
export const fieldWords = (k: string) => ({ qty: "quantity", avg: "average price", dom: "day of the month" } as Record<string, string>)[k] ?? k.replace(/_/g, " ");
