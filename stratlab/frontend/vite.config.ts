import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { publicFonts } from "./scripts/publicFonts.mjs";
import { rewriteProxy } from "./scripts/rewriteProxy.mjs";
import { seoPages } from "./scripts/seoPages.mjs";
import { buildStamp } from "./scripts/buildStamp.mjs";

// Production forwards /stocks, /sitemap.xml, /sitemaps, /v and /c to the API (vercel.json); `vite` and `vite preview` do the
// same, to the API the app is pointed at (scripts/rewriteProxy.mjs). Those API pages use the site's fonts at /fonts
// (scripts/publicFonts.mjs).
const forwarded = rewriteProxy();

export default defineConfig({
  plugins: [react(), publicFonts(), seoPages()],
  // which build this bundle is (Admin → System shows it beside the server's: R24-009)
  define: { __APP_BUILD__: JSON.stringify(buildStamp()) },
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
            { name: "boot", test: /src[\\/]lib[\\/](entry|config|http|returnTo)\.ts$/ },
            // (the public pages use them too: none of them may import the account code below)
            // the consent banner and its settings too (ADS-1): every page draws it, so it rides in this file rather than adding its own
            { name: "common", test: /src[\\/](lib[\\/](brand|format|marketHours|rotating|lazyRetry|ads|adsConfig|track|plans)|components[\\/](Icons|Logo|ui|Tracking))\.tsx?$/ },
            // the signed-in app's own start-up: server calls with a login, and the account state. A visitor never downloads it
            // the two kit pieces that read the account (a plan note, the company picker): apart from the rest of the kit, which the public pages use
            // the two the landing page uses (the billing switch and the sign-in panel), on their own so the landing page stays small
            { name: "kit-lite", includeDependenciesRecursively: false, test: /src[\\/](components[\\/]kit[\\/](Seg|Dialog)\.tsx|lib[\\/]focusTrap\.ts)$/ },
            // the kit pieces the public pages draw (the library, a shared verdict, the policies, the sign-in gate), on their
            // own: in the rest of the kit's file they brought the sign-in library and the account code with them, some
            // forty files and 100 kB a visitor's /library waited for (R8V-013); the market chips and the card's details fold are here too (MO-5)
            { name: "kit-public", includeDependenciesRecursively: false, test: /src[\\/]components[\\/]kit[\\/](Badge|Card|ChipBar|DataTable|Disclosure|Stat|States|Form|PageHeader|LinkCard|Signed|Spark)\.tsx$/ },
            { name: "kit", includeDependenciesRecursively: false, test: /src[\\/](components[\\/]kit[\\/](?!index|Notice|StockPicker|Seg|Dialog)[^\\/]+\.tsx?|lib[\\/]dateInput\.ts)$/ },
            { name: "kit-account", includeDependenciesRecursively: false, test: /src[\\/]components[\\/]kit[\\/](Notice|StockPicker)\.tsx$/ },
            { name: "account", includeDependenciesRecursively: false, test: /src[\\/](lib[\\/](api|app)|components[\\/]CompanySearch)\.tsx?$/ },
          ],
        },
      },
    },
  },
});
