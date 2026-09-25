import { api } from "./api";

/** Installing StratLab on a phone or computer, and turning on its notifications. */
type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };
let deferred: InstallEvent | null = null;
const listeners = new Set<() => void>();

export function registerPwa() {
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e as InstallEvent; listeners.forEach((f) => f()); });
  window.addEventListener("appinstalled", () => { deferred = null; listeners.forEach((f) => f()); });
  window.addEventListener("load", () => { navigator.serviceWorker.register("/sw.js").catch(() => undefined); });
}

export const onInstallChange = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f); }; };
export const canInstall = () => !!deferred;
export const installed = () => matchMedia("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true;
export const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent);
export const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

export async function install(): Promise<boolean> {
  if (!deferred) return false;
  await deferred.prompt();
  const { outcome } = await deferred.userChoice;
  deferred = null;
  listeners.forEach((f) => f());
  return outcome === "accepted";
}

const keyBytes = (b64: string) => {
  const s = atob((b64 + "=".repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
};

async function current(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.getRegistration();
  return reg ? reg.pushManager.getSubscription() : null;
}

export async function pushOnHere(): Promise<boolean> {
  if (!pushSupported()) return false;
  try { return !!(await current()); } catch { return false; }
}

/** Ask permission, subscribe this device and tell the server. Returns a sentence when it can't. */
export async function enablePush(): Promise<string | null> {
  if (!pushSupported()) return isIos() && !installed()
    ? "On an iPhone, first add StratLab to your Home Screen (Share → Add to Home Screen), then open it from there and turn notifications on."
    : "This browser can't show notifications.";
  const k = await api<{ enabled: boolean; key: string | null }>("/push/key");
  if (!k.enabled || !k.key) return "Phone notifications aren't set up on the server yet.";
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return "Notifications are blocked for StratLab. Allow them in your browser or phone settings, then try again.";
  const reg = await navigator.serviceWorker.ready;
  let sub: PushSubscription;
  try { sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(k.key) }); }
  catch { return "This browser couldn't reach its notification service. Try again, or use Chrome, Edge or Firefox (on an iPhone, the installed app)."; }
  await api("/push/subscribe", { method: "POST", body: { subscription: sub.toJSON() } });
  return null;
}

export async function disablePush() {
  const sub = await current();
  if (!sub) return;
  await api("/push/unsubscribe", { method: "POST", body: { subscription: sub.toJSON() } }).catch(() => undefined);
  await sub.unsubscribe();
}
