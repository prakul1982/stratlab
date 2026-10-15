/** The currency a My stocks item's price is in: its market's, so the page prints "₹925.40" or "$341.27" as the email does (R28-005). */
export const itemCurrency = (region: string | null | undefined): "USD" | "INR" => (region === "US" ? "USD" : "INR");
