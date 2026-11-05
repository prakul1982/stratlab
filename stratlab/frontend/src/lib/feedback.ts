/* Help & feedback's words and the few facts sent with a report, kept free of React so the unit tests read them directly. */

export type FeedbackType = "broken" | "not_working" | "idea";

/** [value, label, short label for a narrow screen]: the server's own three (backend/app/feedback.py TYPES). */
export const FEEDBACK_TYPES: [FeedbackType, string, string][] = [
  ["broken", "Something's broken", "Broken"],
  ["not_working", "A feature isn't working", "Not working"],
  ["idea", "Idea for a new feature", "Idea"],
];

/** The words' limit, the server's own (feedback.MAX_TEXT). */
export const FEEDBACK_MAX = 2000;

/** "Chrome 130 on Android": the browser and system in a few words, never the whole user-agent string. */
export function browserLine(ua: string): string {
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad|iPod/.test(ua) ? "iOS" : /Mac OS X/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows"
    : /CrOS/.test(ua) ? "ChromeOS" : /Linux/.test(ua) ? "Linux" : "another system";
  const hit = ua.match(/Edg\/(\d+)/) ? ["Edge", ua.match(/Edg\/(\d+)/)![1]]
    : ua.match(/OPR\/(\d+)/) ? ["Opera", ua.match(/OPR\/(\d+)/)![1]]
    : ua.match(/SamsungBrowser\/(\d+)/) ? ["Samsung Internet", ua.match(/SamsungBrowser\/(\d+)/)![1]]
    : ua.match(/Firefox\/(\d+)/) ? ["Firefox", ua.match(/Firefox\/(\d+)/)![1]]
    : ua.match(/(?:Chrome|CriOS)\/(\d+)/) ? ["Chrome", ua.match(/(?:Chrome|CriOS)\/(\d+)/)![1]]
    : ua.match(/Version\/(\d+).*Safari/) ? ["Safari", ua.match(/Version\/(\d+).*Safari/)![1]]
    : ["A browser", ""];
  return `${hit[0]}${hit[1] ? ` ${hit[1]}` : ""} on ${os}`;
}

export type FeedbackRow = {
  id: string; at: string; type: FeedbackType; text: string; path: string; version: string; browser: string; screen: string;
  plan: string; signed_in: boolean; reply: boolean; reply_to: string | null; status: "new" | "seen" | "fixed";
};
