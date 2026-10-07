import { asDate, pct } from "../lib/format";
import { MARK_RATIO, markSvg } from "../lib/brand";
import type { CheckStatus, Experiment, Notebook } from "../lib/types";

/* A 1200×630 card of a verdict, sized for WhatsApp, X and LinkedIn previews. */

export const W = 1200, H = 630, PAD = 64;
export const THEMES = {
  light: { paper: "#F5F1E8", card: "#FFFDF7", rule: "#EAE3D3", line: "#DCD3C0", ink: "#1D1B17", ink2: "#2E2B25", muted: "#6B665B",
    blue: "#1F4FB5", blueSoft: "#DCE5F7", orange: "#B4500F", orangeSoft: "#F6E2D2", chip: "#ECE6D8", shade: "rgba(180,80,15,0.07)" },
  dark: { paper: "#161513", card: "#1E1D1A", rule: "#1F1E1B", line: "#34312A", ink: "#F2EDE3", ink2: "#DCD6CA", muted: "#A39C8C",
    blue: "#7FA2F0", blueSoft: "#1E2A45", orange: "#EE8A4A", orangeSoft: "#3A2518", chip: "#2A2823", shade: "rgba(238,138,74,0.08)" },
};
export type Theme = typeof THEMES.light;

export interface CardData {
  meta: string;            // "EMA 20/50 CROSSOVER · BTC/USD"
  context: string;         // "DAILY CANDLES · SEP 2022 – SEP 2026 · LONG"
  headline: string;
  tone: "blue" | "orange" | "ink";
  reason: string;
  checks: { title: string; status: CheckStatus }[];
  passed: number; total: number;
  stats: [string, string][];
  equity: (number | null)[]; hold: (number | null)[]; split: number | null;
}

const SHORT: Record<string, string> = { unseen: "Unseen data", nearby: "Nearby settings", shuffle: "Bad-luck drawdown", sample: "Enough trades" };
const month = (iso: string) => asDate(iso).toLocaleDateString("en-GB", { month: "short", year: "numeric" }).toUpperCase();
const TF_WORD: Record<string, string> = { "1d": "DAILY", "1h": "1-HOUR", "15m": "15-MINUTE", "5m": "5-MINUTE" };

export function cardFromExperiment(nb: Notebook, e: Experiment): CardData {
  const v = e.verdict, s = e.stats;
  const unseen = v.checks.find((c) => c.id === "unseen");
  const side = e.strategy.side === "both" ? "LONG AND SHORT" : e.strategy.side === "short" ? "SHORT" : "LONG";
  const g = e.group;
  const where = g ? `${g.name} · ${g.members.length} INSTRUMENTS` : e.instrument.symbol;
  const stats: [string, string][] = [
    [pct(s.ret), "return after costs"],
    [pct(s.buy_hold_ret), g ? "buy and hold, equal weight" : "buy and hold"],
  ];
  if (g) stats.push([`${g.members.filter((m) => m.pnl > 0).length} of ${g.members.length}`, "members profitable"]);
  else if (unseen?.data && unseen.status !== "skip") stats.push([pct(unseen.data.unseen_ret), "on years it never saw"]);
  stats.push([String(s.n), s.n === 1 ? "trade" : "trades"]);
  return {
    meta: `${nb.name} · ${where}`.toUpperCase(),
    context: [`${TF_WORD[e.tf] ?? e.tf} CANDLES`, e.range?.from ? `${month(e.range.from)} – ${month(e.range.to)}` : null, side,
      g ? `UP TO ${g.max_open} AT ONCE` : null].filter(Boolean).join(" · "),
    headline: v.headline,
    tone: v.verdict === "edge" ? "blue" : v.verdict === "luck" || v.verdict === "no_edge" ? "orange" : "ink",
    reason: v.summary || nb.question || "",
    checks: v.checks.map((c) => ({ title: SHORT[c.id] ?? c.title, status: c.status })),
    passed: v.passed, total: v.checks.length || v.total,
    stats,
    equity: e.series?.equity ?? [], hold: e.series?.buy_hold ?? [], split: e.series?.split ?? null,
  };
}

export function loadMark(): Promise<HTMLImageElement> {
  return new Promise((ok, bad) => {
    const im = new Image();
    im.onload = () => ok(im); im.onerror = bad;
    im.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(markSvg());
  });
}

/** Trim to fit a width, ending in "…" when anything was cut. */
export function fit(g: CanvasRenderingContext2D, text: string, max: number): string {
  if (g.measureText(text).width <= max) return text;
  let t = text;
  while (t.length > 1 && g.measureText(t + "…").width > max) t = t.slice(0, -1);
  return t.trimEnd() + "…";
}

/** Word-wrap into at most `lines` lines, the last one ending in "…" if the text runs on. */
function wrap(g: CanvasRenderingContext2D, text: string, max: number, lines: number): string[] {
  const words = text.split(/\s+/).filter(Boolean), out: string[] = [];
  let cur = "";
  for (let i = 0; i < words.length; i++) {
    const next = cur ? cur + " " + words[i] : words[i];
    if (g.measureText(next).width <= max) { cur = next; continue; }
    if (out.length === lines - 1) { out.push(fit(g, cur + " " + words.slice(i).join(" "), max)); return out; }
    out.push(cur); cur = words[i];
  }
  if (cur) out.push(cur);
  return out;
}

export function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

function chart(g: CanvasRenderingContext2D, c: Theme, d: CardData, x: number, y: number, w: number, h: number) {
  g.fillStyle = c.card; g.strokeStyle = c.line; g.lineWidth = 1;
  roundRect(g, x, y, w, h, 16); g.fill(); g.stroke();
  const eq = d.equity, hold = d.hold, n = eq.length;
  const vals = [...eq, ...hold].filter((v): v is number => v != null && isFinite(v));
  if (n < 2 || !vals.length) return;
  const px = x + 20, py = y + 44, pw = w - 40, ph = h - 64;
  const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
  const X = (i: number) => px + (pw * i) / (n - 1), Y = (v: number) => py + ph - ((v - lo) / span) * ph;
  if (d.split != null && d.split > 0 && d.split < n) {
    g.fillStyle = c.shade; g.fillRect(X(d.split), py - 8, px + pw - X(d.split), ph + 16);
    g.fillStyle = c.muted; g.font = "500 12px 'IBM Plex Mono', monospace"; g.textAlign = "right";
    g.fillText("SHADED: UNSEEN YEARS", x + w - 20, y + 26); g.textAlign = "left";
  }
  const line = (series: (number | null)[], color: string, width: number, dash: number[]) => {
    g.strokeStyle = color; g.lineWidth = width; g.setLineDash(dash); g.beginPath();
    let started = false;
    series.forEach((v, i) => { if (v == null) return; if (!started) { g.moveTo(X(i), Y(v)); started = true; } else g.lineTo(X(i), Y(v)); });
    g.stroke(); g.setLineDash([]);
  };
  line(hold, c.muted, 1.5, [5, 5]);
  line(eq, c.ink, 2.5, []);
  g.font = "500 13px 'IBM Plex Sans', sans-serif"; g.fillStyle = c.ink; g.fillText("— Strategy", x + 20, y + 26);
  g.fillStyle = c.muted; g.fillText("- - Buy and hold", x + 120, y + 26);
}

export async function renderCard(d: CardData, theme: "light" | "dark" = "light"): Promise<Blob> {
  await Promise.all(["800 30px Montserrat", "300 30px Montserrat", "400 30px Fraunces", "500 16px 'IBM Plex Mono'", "400 16px 'IBM Plex Sans'"]
    .map((f) => document.fonts.load(f))).catch(() => {});
  await document.fonts.ready;
  const mark = await loadMark().catch(() => null);
  const c = THEMES[theme];
  const cv = document.createElement("canvas");
  cv.width = W * 2; cv.height = H * 2;
  const g = cv.getContext("2d")!;
  g.scale(2, 2);
  g.fillStyle = c.paper; g.fillRect(0, 0, W, H);
  g.fillStyle = c.rule;
  for (let y = 34; y < H; y += 34) g.fillRect(0, y, W, 1);

  // logo and what was tested
  let lx = PAD;
  if (mark) { g.drawImage(mark, lx, 38, 42 * MARK_RATIO, 42); lx += 42 * MARK_RATIO + 8; }
  g.fillStyle = c.ink; g.font = "800 26px Montserrat, sans-serif"; g.fillText("Strat", lx, 70);
  lx += g.measureText("Strat").width; g.font = "300 26px Montserrat, sans-serif"; g.fillText("Lab", lx, 70);
  lx += g.measureText("Lab").width + 32;
  g.fillStyle = c.muted; g.font = "500 15px 'IBM Plex Mono', monospace"; g.textAlign = "right";
  g.fillText(fit(g, d.meta, W - PAD - lx), W - PAD, 68);
  g.textAlign = "left";

  // the verdict, left column
  const left = 640;
  g.fillStyle = c.muted; g.font = "500 14px 'IBM Plex Mono', monospace";
  g.fillText(fit(g, d.context, left), PAD, 142);
  const tone = d.tone === "blue" ? c.blue : d.tone === "orange" ? c.orange : c.ink;
  let size = 84;
  g.font = `400 ${size}px Fraunces, Georgia, serif`;
  while (g.measureText(d.headline).width > left && size > 48) { size -= 4; g.font = `400 ${size}px Fraunces, Georgia, serif`; }
  g.fillStyle = tone; g.fillText(d.headline, PAD - 3, 142 + 16 + size);
  g.fillStyle = c.ink2; g.font = "400 22px Fraunces, Georgia, serif";
  const ry = 142 + 16 + size + 44;
  wrap(g, d.reason, left, 3).forEach((ln, i) => g.fillText(ln, PAD, ry + i * 30));

  // the equity chart, right column
  chart(g, c, d, PAD + left + 36, 104, W - PAD - (PAD + left + 36), 270);

  // the four checks
  g.fillStyle = c.muted; g.font = "500 13px 'IBM Plex Mono', monospace";
  g.fillText(`${d.total} HONESTY CHECKS · ${d.passed} PASSED`, PAD, 418);
  let bx = PAD;
  const badge: Record<CheckStatus, [string, string, string]> = {
    pass: [c.blueSoft, c.blue, "Passed"], fail: [c.orangeSoft, c.orange, "Failed"], warn: [c.chip, c.ink2, "Warning"], skip: [c.chip, c.muted, "Skipped"],
  };
  for (const ch of d.checks) {
    const [bg, fg, word] = badge[ch.status];
    g.font = "600 15px 'IBM Plex Sans', sans-serif";
    const tw = g.measureText(ch.title).width;
    g.font = "500 13px 'IBM Plex Sans', sans-serif";
    const sw = g.measureText(word).width;
    const bw = tw + sw + 42;
    g.fillStyle = bg; roundRect(g, bx, 432, bw, 38, 19); g.fill();
    g.fillStyle = c.ink; g.font = "600 15px 'IBM Plex Sans', sans-serif"; g.fillText(ch.title, bx + 16, 456);
    g.fillStyle = fg; g.font = "600 13px 'IBM Plex Sans', sans-serif"; g.fillText(word, bx + 26 + tw, 456);
    bx += bw + 10;
  }

  // the numbers
  let sx = PAD;
  for (const [big, small] of d.stats) {
    g.fillStyle = c.ink; g.font = "400 36px Fraunces, Georgia, serif"; g.fillText(big, sx, 540);
    g.fillStyle = c.muted; g.font = "400 14px 'IBM Plex Sans', sans-serif"; g.fillText(small, sx, 562);
    sx += Math.max(g.measureText(small).width, 150) + 44;
  }

  // footer
  g.fillStyle = c.muted; g.font = "400 12px 'IBM Plex Sans', sans-serif";
  g.fillText("Research and paper trading only. Past results don't predict future returns. Not investment advice.", PAD, 602);
  g.fillStyle = c.ink; g.font = "500 17px 'IBM Plex Mono', monospace"; g.textAlign = "right";
  g.fillText("stratlab.studio", W - PAD, 602);
  g.textAlign = "left";

  return new Promise((r) => cv.toBlob((b) => r(b!), "image/png"));
}

const slug = (s: string) => s.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase() || "verdict";

/** Share a verdict: the phone's share sheet where there is one, otherwise a download (and a copy on the clipboard). */
export async function shareVerdict(nb: Notebook, e: Experiment, theme: "light" | "dark", link?: string | null): Promise<"shared" | "saved" | "cancelled"> {
  const blob = await renderCard(cardFromExperiment(nb, e), theme);
  const file = new File([blob], `stratlab-${slug(nb.name)}-v${e.v}.png`, { type: "image/png" });
  const touch = matchMedia("(pointer: coarse)").matches;
  const text = `${e.verdict.headline} ${nb.name} on ${e.instrument.symbol}, tested on StratLab.${link ? " " + link : ""}`;
  if (touch && navigator.canShare?.({ files: [file] })) {
    try { await navigator.share({ files: [file], title: "StratLab verdict", text }); return "shared"; }
    catch (x) { if ((x as Error).name === "AbortError") return "cancelled"; }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = file.name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 3000);
  try { await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]); } catch { /* not allowed here; the download is enough */ }
  return "saved";
}
