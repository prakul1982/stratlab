import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { publicFonts } from "./scripts/publicFonts.mjs";
import { rewriteProxy } from "./scripts/rewriteProxy.mjs";

// Production forwards /stocks, /sitemap.xml, /sitemaps, /v and /c to the API (vercel.json); `vite` and `vite preview` do the
// same, to the API the app is pointed at (scripts/rewriteProxy.mjs). Those API pages use the site's fonts at /fonts
// (scripts/publicFonts.mjs).
const forwarded = rewriteProxy();

export default defineConfig({
  plugins: [react(), publicFonts()],
  server: { proxy: forwarded },
  preview: { proxy: forwarded },
  build: {
    outDir: "dist",
    sourcemap: false,
    rolldownOptions: {
      output: {
        // the libraries every page needs get their own files: they rarely change, so browsers keep them across releases
        codeSplitting: {
          groups: [
            { name: "react", test: /node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/ },
            { name: "auth", test: /node_modules[\\/](@supabase|tslib)[\\/]/ },
            // small pieces nearly every page uses, in one file instead of many tiny ones
            { name: "common", test: /src[\\/](lib[\\/](api|app|brand|format|marketHours|rotating)|components[\\/](CompanySearch|Icons|Logo|ui))\.tsx?$/ },
          ],
        },
      },
    },
  },
});
