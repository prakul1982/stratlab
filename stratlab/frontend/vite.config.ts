import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
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
