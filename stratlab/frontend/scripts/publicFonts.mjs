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
  ["ibm-plex-sans-latin-400-normal.woff2", "@fontsource/ibm-plex-sans"],
  ["ibm-plex-sans-latin-600-normal.woff2", "@fontsource/ibm-plex-sans"],
  ["montserrat-latin-300-normal.woff2", "@fontsource/montserrat"],
  ["montserrat-latin-800-normal.woff2", "@fontsource/montserrat"],
];

export const fontSource = (file, pkg) => path.join(root, "node_modules", pkg, "files", file);

export function publicFonts() {
  return {
    name: "stratlab-public-fonts",
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
