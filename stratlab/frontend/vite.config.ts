import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { publicFonts } from "./scripts/publicFonts.mjs";
import { rewriteProxy } from "./scripts/rewriteProxy.mjs";
import { seoPages } from "./scripts/seoPages.mjs";

// Production forwards /stocks, /sitemap.xml, /sitemaps, /v and /c to the API (vercel.json); `vite` and `vite preview` do the
// same, to the API the app is pointed at (scripts/rewriteProxy.mjs). Those API pages use the site's fonts at /fonts
// (scripts/publicFonts.mjs).
const forwarded = rewriteProxy();

export default defineConfig({
  plugins: [react(), publicFonts(), seoPages()],
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
            // what the entry point reads before anything else: no imports, so it stays out of the account code
            { name: "boot", test: /src[\\/]lib[\\/](entry|config|http)\.ts$/ },
            // (the public pages use them too: none of them may import the account code below)
            { name: "common", test: /src[\\/](lib[\\/](brand|format|marketHours|rotating)|components[\\/](Icons|Logo|ui))\.tsx?$/ },
            // the signed-in app's own start-up: server calls with a login, and the account state. A visitor never downloads it
            // the two kit pieces that read the account (a plan note, the company picker): apart from the rest of the kit, which the public pages use
            // the two the landing page uses (the billing switch and the sign-in panel), on their own so the landing page stays small
            { name: "kit-lite", includeDependenciesRecursively: false, test: /src[\\/](components[\\/]kit[\\/](Seg|Dialog)\.tsx|lib[\\/]focusTrap\.ts)$/ },
            { name: "kit", includeDependenciesRecursively: false, test: /src[\\/](components[\\/]kit[\\/](?!index|Notice|StockPicker|Seg|Dialog)[^\\/]+\.tsx?|lib[\\/]dateInput\.ts)$/ },
            { name: "kit-account", includeDependenciesRecursively: false, test: /src[\\/]components[\\/]kit[\\/](Notice|StockPicker)\.tsx$/ },
            { name: "account", includeDependenciesRecursively: false, test: /src[\\/](lib[\\/](api|app)|components[\\/]CompanySearch)\.tsx?$/ },
          ],
        },
      },
    },
  },
});
