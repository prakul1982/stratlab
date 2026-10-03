/* Sharing a link: the phone's own share sheet where there is one, and the clipboard on a computer. */

/** A touch phone or tablet with a share sheet (a desktop browser may have navigator.share too, but copying is
 *  what people expect there). */
export const canShareSheet = () => typeof navigator.share === "function" && matchMedia("(pointer: coarse)").matches;

export type Shared = "shared" | "copied" | "cancelled" | "shown";

/** Share a link (and, on a phone that takes them, an image with it). "shown" means neither the share sheet nor the
 *  clipboard was allowed, so the caller should show the link for the person to copy by hand. */
export async function shareLink(o: { url: string; title: string; text: string; file?: File | null }): Promise<Shared> {
  if (canShareSheet()) {
    const withFile = o.file && navigator.canShare?.({ files: [o.file] }) ? { files: [o.file] } : {};
    try { await navigator.share({ title: o.title, text: `${o.text} ${o.url}`, url: o.url, ...withFile }); return "shared"; }
    catch (x) { if ((x as Error).name === "AbortError") return "cancelled"; }
  }
  try { await navigator.clipboard.writeText(o.url); return "copied"; } catch { return "shown"; }
}

/** Save a picture to the device. */
export function download(blob: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 3000);
}

/** The site's address for links people share (the local app in development and tests). */
export const siteUrl = () => (location.hostname === "localhost" || location.hostname === "127.0.0.1" ? location.origin : "https://stratlab.studio");

/* Invite links: a code from /?ref=CODE is kept until the person has signed in, then sent once. */
const REF_KEY = "stratlab.ref";
const REF = /^[A-Za-z0-9_-]{12}$/;

/** On any page load: remember an invite code from the address, and take it out of the address bar. */
export function captureRef() {
  try {
    const u = new URL(location.href);
    const code = u.searchParams.get("ref");
    if (!code) return;
    if (REF.test(code)) localStorage.setItem(REF_KEY, code);
    u.searchParams.delete("ref");
    history.replaceState(history.state, "", u.pathname + (u.search === "?" ? "" : u.search) + u.hash);
  } catch { /* storage off: the invite just isn't counted */ }
}

/** The kept invite code, once: it's forgotten as it's read. */
export function takeRef(): string | null {
  try {
    const code = localStorage.getItem(REF_KEY);
    localStorage.removeItem(REF_KEY);
    return code && REF.test(code) ? code : null;
  } catch { return null; }
}
