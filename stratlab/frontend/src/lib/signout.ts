import { sessionKey } from "./config";
import { leavePush } from "./pwa";
import { writeViewAs } from "./viewAs";

type Auth = { signOut: (o: { scope: "local" | "global" | "others" }) => Promise<{ error: unknown }> };

/** "Sign out": this device only, and it always ends signed out. The sign-in library's own default scope signs out every
 * device, and "Sign out everywhere" is the one button that means that. The library hands back an error (the network
 * dropped) instead of throwing and then leaves the saved sign-in where it was, so the button seemed to do nothing: then
 * the saved sign-in is removed here and the page reloaded, which comes up signed out. */
export async function signOutHere(auth: Auth, reload: () => void = () => location.reload()): Promise<void> {
  await leavePush();
  let failed = false;
  try { failed = !!(await auth.signOut({ scope: "local" })).error; } catch { failed = true; }
  if (!failed) return;
  try { localStorage.removeItem(sessionKey()); } catch { /* storage off: nothing saved to remove */ }
  writeViewAs(null);                   // the sign-out event that would have cleared it never came
  reload();
}
