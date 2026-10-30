// Point the built app at the fake backend (the real config.js points at production). Clarity is off here: its consent card would sit
// over the pages every other test drives (e2e/ads.spec.ts turns it on, with the ads, for the tests of the question itself).
import { writeFileSync } from "node:fs";
writeFileSync(new URL("../dist/config.js", import.meta.url),
  `window.STRATLAB_CONFIG = {API_BASE:"${process.env.E2E_API ?? "http://127.0.0.1:8765"}",SUPABASE_URL:"https://demo.supabase.co",SUPABASE_ANON_KEY:"demo",CLARITY_PROJECT_ID:"",META_PIXEL_ID:""};\n`);
