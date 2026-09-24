/* The StratLab mark: an S made of a green and a red candlestick, split by a white ribbon.
   One source for the app, the share image and the static icons in public/. */
export const MARK_VIEWBOX = "254 174 156 382";
export const MARK_RATIO = 156 / 382;

export const MARK = {
  ribbon: "M266,308C268,322 300,338 330,352C370,372 400,392 404,418C408,432 394,448 390,460C390,440 360,416 320,396C285,378 262,362 257,343C254,330 258,316 266,308Z",
  greenWick: { x: 381, y: 177, width: 10, height: 56 },
  green: "M345,252C310,268 266,290 266,308C268,322 300,338 330,352C370,372 400,392 404,418V234Q404,230 400,230H361Q357,230 357,234V348L345,342Z",
  redWick: { x: 277, y: 455, width: 11, height: 98 },
  red: "M257,343C262,362 285,378 320,396C362,416 391,436 390,460C390,480 350,510 316,530V405L306,399V453Q306,457 302,457H261Q257,457 257,453Z",
};

export const MARK_COLORS = {
  green: [["0", "#16CC8F"], [".55", "#0C8A5C"], ["1", "#063B28"]],
  red: [["0", "#FF585E"], [".5", "#E6333C"], ["1", "#930C17"]],
  greenWick: "#12C48A",
  redWick: "#FF444B",
  ribbon: "#FFFFFF",
} as const;

/** The mark as a standalone SVG string (for canvas drawing and static icons). */
export function markSvg(): string {
  const stops = (s: readonly (readonly string[])[]) => s.map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join("");
  const r = (w: { x: number; y: number; width: number; height: number }, fill: string) =>
    `<rect x="${w.x}" y="${w.y}" width="${w.width}" height="${w.height}" rx="1.5" fill="${fill}"/>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${MARK_VIEWBOX}">`
    + `<defs><linearGradient id="g" gradientUnits="userSpaceOnUse" x1="392" y1="228" x2="300" y2="365">${stops(MARK_COLORS.green)}</linearGradient>`
    + `<linearGradient id="r" gradientUnits="userSpaceOnUse" x1="285" y1="525" x2="345" y2="395">${stops(MARK_COLORS.red)}</linearGradient></defs>`
    + `<path fill="${MARK_COLORS.ribbon}" d="${MARK.ribbon}"/>${r(MARK.greenWick, MARK_COLORS.greenWick)}<path fill="url(#g)" d="${MARK.green}"/>`
    + `${r(MARK.redWick, MARK_COLORS.redWick)}<path fill="url(#r)" d="${MARK.red}"/></svg>`;
}
