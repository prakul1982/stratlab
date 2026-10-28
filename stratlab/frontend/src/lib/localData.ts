import { IMPORTED, OPTIONS_DRAFT, OPTIONS_NOTES } from "./options";
import { forgetPersisted } from "./persist";
import { PINS_KEY } from "./pins";
import { clearUploads } from "./upload";

/** What this browser kept for the person who just signed out: uploaded CSVs, pinned pages, a strategy imported for the
 * Options page and the structure being built there (RC6-011: the next person on a shared device was offered the last one's draft). None of it is account data on the server, but the next person on a shared device shouldn't see it. */
export function clearLocalData() {
  clearUploads();
  forgetPersisted(PINS_KEY);
  try { sessionStorage.removeItem(IMPORTED); } catch { /* storage off */ }
  try { localStorage.removeItem(OPTIONS_DRAFT); localStorage.removeItem(OPTIONS_NOTES); } catch { /* storage off */ }
}
