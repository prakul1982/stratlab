/* The share-link calls (backend/app/share.py); the words about them are in researchShare.ts, which loads without the app. */
import { api } from "./api";
import type { Region } from "./research";
import type { ShareList, ShareMade } from "./researchShare";

export const researchShareApi = {
  deep: (region: Region, symbol: string) => api<ShareMade>(`/research/share/deep/${region}/${encodeURIComponent(symbol)}`, { method: "POST" }),
  theme: (region: Region, q: string) => api<ShareMade>(`/research/share/theme?q=${encodeURIComponent(q)}&region=${region}`, { method: "POST" }),
  list: () => api<ShareList>("/research/shares"),
  off: (token: string) => api<{ on: boolean }>(`/research/shares/${encodeURIComponent(token)}`, { method: "DELETE" }),
};
