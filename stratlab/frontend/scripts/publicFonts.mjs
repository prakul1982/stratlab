// The site's fonts at fixed addresses (/fonts/<file>), for pages the API renders: the public company pages
// (backend/app/stock_pages.py) wear the site's own type, but can't know the hashed names the app's bundle gives its fonts.
// The build copies these few files from the installed font packages into dist/fonts; `vite` serves them from there too.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** [published file name, the package it comes from] */
export const PUBLIC_FONTS = [
  ["fraunces-latin-400-normal.woff2", "@fontsource/fraunces"],
  ["fraunces-latin-600-normal.woff2", "@fontsource/fraunces"],
  ["ibm-plex-sans-latin-400-normal.woff2", "@fontsource/ibm-plex-sans"],
  ["ibm-plex-sans-latin-500-normal.woff2", "@fontsource/ibm-plex-sans"],
  ["ibm-plex-sans-latin-600-normal.woff2", "@fontsource/ibm-plex-sans"],
  ["montserrat-latin-300-normal.woff2", "@fontsource/montserrat"],
  ["montserrat-latin-800-normal.woff2", "@fontsource/montserrat"],
];

export const fontSource = (file, pkg) => path.join(root, "node_modules", pkg, "files", file);

/** The app's own fonts the first screen draws with, asked for by index.html straight away: they arrived after the landing
 * page had drawn in the stand-in serif, and the 80 px heading re-wrapped and pushed the hero down (R80-007, CLS 0.13). */
const FIRST_SCREEN = /^assets\/(fraunces-latin-400-normal|fraunces-latin-600-normal|ibm-plex-sans-latin-400-normal|ibm-plex-sans-latin-600-normal)-[\w-]+\.woff2$/;

export function publicFonts() {
  return {
    name: "stratlab-public-fonts",
    transformIndexHtml: {
      order: "post",
      handler(_html, ctx) {
        if (!ctx.bundle) return [];
        return Object.keys(ctx.bundle).filter((f) => FIRST_SCREEN.test(f)).sort().map((f) => ({
          tag: "link", attrs: { rel: "preload", href: `/${f}`, as: "font", type: "font/woff2", crossorigin: "" }, injectTo: "head",
        }));
      },
    },
    generateBundle() {
      for (const [file, pkg] of PUBLIC_FONTS) this.emitFile({ type: "asset", fileName: `fonts/${file}`, source: fs.readFileSync(fontSource(file, pkg)) });
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const hit = PUBLIC_FONTS.find(([file]) => req.url === `/fonts/${file}`);
        if (!hit) return next();
        res.setHeader("Content-Type", "font/woff2");
        res.end(fs.readFileSync(fontSource(...hit)));
      });
    },
  };
}
