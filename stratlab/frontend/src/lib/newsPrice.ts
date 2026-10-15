/** The currency a My stocks item's price is in: the item's own, else its market's, so the page prints "₹925.40" or "$341.27"
 * as the email does (R28-005). An item of no known market has no sign: never a guessed ₹ (R29B-002: "NVDA ₹221.30"). */
export const itemCurrency = (region: string | null | undefined, currency?: string | null): "USD" | "INR" | null =>
  currency === "USD" || currency === "INR" ? currency : region === "US" ? "USD" : region === "IN" ? "INR" : null;
