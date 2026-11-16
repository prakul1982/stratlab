import { sessionKey } from "./config";
import { clearLocalData } from "./localData";
import { leavePush } from "./pwa";
import { writeViewAs } from "./viewAs";

/* A sign-out this page asked for (a Sign out button, "Sign out everywhere", a refused sign-in): set before the sign-in library
 * is told, so the app can tell it from a sign-in that ended on its own in the middle of a visit (the saved sign-in gone from this
 * browser), which the sign-in page then says in words ("You were signed out") instead of greeting a paying user with the
 * first-visit "Sign in to see …" wall (rel1, CX1 problem 3). */
let onPurpose = false;
export const signingOutOnPurpose = (): boolean => onPurpose;
export const markSignOutOnPurpose = (): void => { onPurpose = true; };

type Auth = { signOut: (o: { scope: "local" | "global" | "others" }) => Promise<{ error: unknown }> };

/** "Sign out": this device only, and it always ends signed out. The sign-in library's own default scope signs out every
 * device, and "Sign out everywhere" is the one button that means that. The library hands back an error (the network
 * dropped) instead of throwing and then leaves the saved sign-in where it was, so the button seemed to do nothing: then
 * the saved sign-in is removed here and the page reloaded, which comes up signed out. */
export async function signOutHere(auth: Auth, reload: () => void = () => location.reload()): Promise<void> {
  markSignOutOnPurpose();
  await leavePush();
  let failed = false;
  try { failed = !!(await auth.signOut({ scope: "local" })).error; } catch { failed = true; }
  if (!failed) return;
  try { localStorage.removeItem(sessionKey()); } catch { /* storage off: nothing saved to remove */ }
  clearLocalData();
  writeViewAs(null);                   // the sign-out event that would have cleared it never came
  reload();
}
