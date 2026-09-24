import { pct } from "../lib/format";
import type { Experiment, Notebook } from "../lib/types";

/* A 1200×630 image of a verdict, sized for WhatsApp, X and LinkedIn previews. */
export async function downloadShareImage(nb: Notebook, e: Experiment) {
  await document.fonts.ready;
  const W = 1200, H = 630, c = document.createElement("canvas");
  c.width = W * 2; c.height = H * 2;
  const g = c.getContext("2d")!;
  g.scale(2, 2);
  const colors = { paper: "#F5F1E8", rule: "#EAE3D3", ink: "#1D1B17", muted: "#5C574D", blue: "#1F4FB5", orange: "#B4500F" };
  g.fillStyle = colors.paper; g.fillRect(0, 0, W, H);
  g.fillStyle = colors.rule;
  for (let y = 34; y < H; y += 34) g.fillRect(0, y, W, 1);

  const v = e.verdict;
  const tone = v.verdict === "edge" ? colors.blue : v.verdict === "luck" || v.verdict === "no_edge" ? colors.orange : colors.ink;
  g.fillStyle = colors.ink; g.font = "600 28px Fraunces, Georgia, serif"; g.fillText("StratLab", 64, 84);
  g.fillStyle = colors.muted; g.font = "500 16px 'IBM Plex Mono', monospace"; g.textAlign = "right";
  g.fillText(`${nb.name} · ${e.instrument.symbol}`.toUpperCase().slice(0, 60), W - 64, 82);
  g.textAlign = "left";
  g.fillText(`VERDICT AFTER ${v.total} HONESTY CHECKS`, 64, 200);
  g.fillStyle = tone; g.font = "400 104px Fraunces, Georgia, serif";
  g.fillText(v.headline, 60, 300, W - 120);

  g.fillStyle = "#2E2B25"; g.font = "400 25px Fraunces, Georgia, serif";
  const words = (nb.question || "").split(" ");
  let line = "", y = 352;
  for (const w of words) {
    if (g.measureText(line + w).width > W - 140 && line) { g.fillText(line.trim(), 64, y); line = ""; y += 34; if (y > 400) break; }
    line += w + " ";
  }
  if (y <= 400) g.fillText(line.trim(), 64, y);

  const unseen = v.checks.find((c) => c.id === "unseen")?.data;
  const nearby = v.checks.find((c) => c.id === "nearby")?.data;
  const stats: [string, string][] = [
    [unseen ? pct(unseen.unseen_ret) : pct(e.stats.ret), unseen ? "on years it never saw" : "total return"],
    [nearby ? `${nearby.profitable} of ${nearby.total}` : `${v.passed} of ${v.total}`, nearby ? "nearby settings profitable" : "checks passed"],
    [String(e.stats.n), "trades, after costs"],
  ];
  let x = 64;
  for (const [big, small] of stats) {
    g.fillStyle = colors.ink; g.font = "400 44px Fraunces, Georgia, serif"; g.fillText(big, x, 540);
    g.fillStyle = colors.muted; g.font = "400 16px 'IBM Plex Sans', sans-serif"; g.fillText(small, x, 568);
    x += Math.max(g.measureText(small).width, 200) + 48;
  }
  g.fillStyle = colors.ink; g.font = "500 18px 'IBM Plex Mono', monospace"; g.textAlign = "right";
  g.fillText("stratlab.studio", W - 64, 566);

  const blob: Blob = await new Promise((r) => c.toBlob((b) => r(b!), "image/png"));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `stratlab-${nb.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-v${e.v}.png`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 3000);
}
