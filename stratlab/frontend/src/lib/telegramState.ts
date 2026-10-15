/** What the Telegram box in Alerts settings shows: nothing saved, edited but not saved, saved and confirmed, or saved and
 * waiting for the code StratLab sends to the chat. */
export type TelegramState = "none" | "unsaved" | "verified" | "confirm";

export function telegramState(saved: string | null, typed: string, verified: boolean): TelegramState {
  const chat = (saved || "").trim().toLowerCase();
  if (typed.trim().toLowerCase() !== chat) return "unsaved";
  if (!chat) return "none";
  return verified ? "verified" : "confirm";
}
