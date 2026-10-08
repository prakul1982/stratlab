/** "≈ " before an amount that is the rupee charge converted at today's rate, while the card is charged in rupees (R7O-008).
 * No imports, so the unit tests load it alone. */
export function approx(row: { converted?: boolean } | undefined, chargedIn: string | undefined): string {
  return row?.converted && chargedIn === "INR" ? "≈ " : "";
}
