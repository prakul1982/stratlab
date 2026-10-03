// Point the built app at the fake backend (the real config.js points at production).
import { writeFileSync } from "node:fs";
writeFileSync(new URL("../dist/config.js", import.meta.url),
  'window.STRATLAB_CONFIG = {API_BASE:"http://127.0.0.1:8765",SUPABASE_URL:"https://demo.supabase.co",SUPABASE_ANON_KEY:"demo"};\n');
