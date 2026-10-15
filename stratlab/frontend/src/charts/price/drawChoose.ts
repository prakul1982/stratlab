/* Which copy of a chart's drawings to show, local or the account's. No network here, so it can be tested alone. */
import type { Drawing } from "./drawGeo";

export interface Layout { tf?: string; range?: string; type?: string; volume?: boolean; hide_drawings?: boolean; studies?: { id: string; type: string; params: number[]; slot: number }[] }
/** `synced`: the account has held this copy (it was sent, or it came from the account). */
export interface Saved { drawings: Drawing[]; layout: Layout | null; at: number; dirty: boolean; synced?: boolean }

/** Which copy to show: an unsent local one newer than the account's wins (and is sent); otherwise the account's.
 *  A copy the account already held loses to an emptied account: another device cleared it. */
export function choose(local: Saved | null, remote: { drawings: Drawing[]; layout: Layout | null; at: number } | null):
  { use: { drawings: Drawing[]; layout: Layout | null }; send: boolean } {
  const has = (s: { drawings: Drawing[]; layout: Layout | null } | null) => !!s && (s.drawings.length > 0 || !!s.layout);
  if (!remote) return { use: local ?? { drawings: [], layout: null }, send: false };
  if (local && has(local) && (local.dirty ? local.at >= remote.at : !has(remote) && !local.synced)) return { use: local, send: true };
  if (local?.dirty && !has(local) && local.at >= remote.at) return { use: local, send: true };          // everything was deleted offline
  return { use: remote, send: false };
}
