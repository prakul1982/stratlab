import { MARK_RATIO } from "../lib/brand";
import { H, loadMark, PAD, roundRect, fit, THEMES, W } from "./shareImage";

/* A 1200×630 card of one company's facts, sized for WhatsApp, X and LinkedIn previews. Drawn the way verdict cards
   are; the words and numbers come from the company's public page (GET /cards/company/...), never from AI. */

export interface CompanyCard {
  region: "IN" | "US"; symbol: string; name: string; sector: string; exchange: string;
  price: string | null; range: string | null; as_of: string | null;
  facts: [string, string][];
  page: string;
}

export async function renderCompanyCard(d: CompanyCard, theme: "light" | "dark" = "light"): Promise<Blob> {
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

  // logo, and which company
  let lx = PAD;
  if (mark) { g.drawImage(mark, lx, 38, 42 * MARK_RATIO, 42); lx += 42 * MARK_RATIO + 8; }
  g.fillStyle = c.ink; g.font = "800 26px Montserrat, sans-serif"; g.fillText("Strat", lx, 70);
  lx += g.measureText("Strat").width; g.font = "300 26px Montserrat, sans-serif"; g.fillText("Lab", lx, 70);
  lx += g.measureText("Lab").width + 32;
  g.fillStyle = c.muted; g.font = "500 15px 'IBM Plex Mono', monospace"; g.textAlign = "right";
  g.fillText(fit(g, ["COMPANY FACTS", d.exchange, d.symbol].filter(Boolean).join(" · ").toUpperCase(), W - PAD - lx), W - PAD, 68);
  g.textAlign = "left";

  // sector and name
  const inner = W - PAD * 2;
  g.fillStyle = c.muted; g.font = "500 15px 'IBM Plex Mono', monospace";
  g.fillText(fit(g, (d.sector || (d.region === "US" ? "Listed in the US" : "Listed in India")).toUpperCase(), inner), PAD, 140);
  let size = 72;
  g.font = `400 ${size}px Fraunces, Georgia, serif`;
  while (g.measureText(d.name).width > inner && size > 40) { size -= 4; g.font = `400 ${size}px Fraunces, Georgia, serif`; }
  g.fillStyle = c.ink; g.fillText(fit(g, d.name, inner), PAD - 3, 150 + size);

  // price and the 1-year range
  const py = 150 + size + 90;
  let px = PAD;
  if (d.price) {
    g.fillStyle = c.ink; g.font = "400 48px Fraunces, Georgia, serif"; g.fillText(d.price, px, py);
    const w = g.measureText(d.price).width;
    g.fillStyle = c.muted; g.font = "400 14px 'IBM Plex Sans', sans-serif";
    g.fillText(d.as_of ? `Last price, ${d.as_of}` : "Last price", px, py + 24);
    px += Math.max(w, 160) + 56;
  }
  if (d.range) {
    g.fillStyle = c.ink2; g.font = "400 30px Fraunces, Georgia, serif"; g.fillText(fit(g, d.range, W - PAD - px), px, py);
    g.fillStyle = c.muted; g.font = "400 14px 'IBM Plex Sans', sans-serif"; g.fillText("1-year range (low to high)", px, py + 24);
  }

  // the key facts, in boxes
  const facts = d.facts.slice(0, 4);
  if (facts.length) {
    const gap = 16, bw = (inner - gap * (facts.length - 1)) / facts.length, by = py + 64, bh = 100;
    facts.forEach(([label, value], i) => {
      const bx = PAD + i * (bw + gap);
      g.fillStyle = c.card; g.strokeStyle = c.line; g.lineWidth = 1;
      roundRect(g, bx, by, bw, bh, 14); g.fill(); g.stroke();
      g.fillStyle = c.ink; g.font = "400 34px Fraunces, Georgia, serif"; g.fillText(fit(g, value, bw - 36), bx + 18, by + 50);
      g.fillStyle = c.muted; g.font = "400 14px 'IBM Plex Sans', sans-serif"; g.fillText(fit(g, label, bw - 36), bx + 18, by + 76);
    });
  }

  // footer
  g.fillStyle = c.ink2; g.font = "600 15px 'IBM Plex Sans', sans-serif"; g.fillText("Facts, not advice.", PAD, 602);
  const fw = g.measureText("Facts, not advice.").width;
  g.fillStyle = c.muted; g.font = "400 13px 'IBM Plex Sans', sans-serif";
  g.fillText("From reported results and daily prices. Past prices don't predict future returns.", PAD + fw + 10, 602);
  g.fillStyle = c.ink; g.font = "500 17px 'IBM Plex Mono', monospace"; g.textAlign = "right";
  g.fillText("stratlab.studio", W - PAD, 602);
  g.textAlign = "left";

  return new Promise((r) => cv.toBlob((b) => r(b!), "image/png"));
}
