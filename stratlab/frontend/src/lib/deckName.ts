/* A deck's file name people can read in their Downloads (owner, 5 Nov: "the naming of the pdf can you fix that"):
 * "StratLab - India Defence theme (India) - 5 Nov 2026.pdf", "StratLab - Reliance Industries deep dive - 5 Nov 2026.pptx".
 * Plain ASCII only: Chrome saves a name with a dash like "–" as "download" (and some file systems refuse such characters too); accents
 * lose their marks, characters no file system takes are dropped, and the day is India's. Its own small file: the share helper rides in
 * the landing page. */
const BAD = /[\\/:*?"<>|\u0000-\u001f]+/g;

export function deckDay(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" }).format(now).replace(/\bSept\b/, "Sep");
}

export function deckFileName(title: string, format: "pdf" | "pptx", now: Date = new Date()): string {
  const clean = title.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[–—]/g, "-").replace(/[^\x20-\x7e]+/g, " ")
    .replace(BAD, " ").replace(/\s+/g, " ").trim().slice(0, 120) || "StratLab deck";
  return `StratLab - ${clean} - ${deckDay(now)}.${format}`;
}
