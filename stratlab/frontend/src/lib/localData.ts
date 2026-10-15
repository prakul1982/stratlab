import { IMPORTED } from "./options";
import { forgetPersisted } from "./persist";
import { PINS_KEY } from "./pins";
import { clearUploads } from "./upload";

/** What this browser kept for the person who just signed out: uploaded CSVs, pinned pages and a strategy imported for the
 * Options page. None of it is account data on the server, but the next person on a shared device shouldn't see it. */
export function clearLocalData() {
  clearUploads();
  forgetPersisted(PINS_KEY);
  try { sessionStorage.removeItem(IMPORTED); } catch { /* storage off */ }
}
