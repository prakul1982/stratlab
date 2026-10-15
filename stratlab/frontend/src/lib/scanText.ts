/** "Scanning 50 stocks…" once the group's size is known, else "Scanning…". */
export const scanningText = (count?: number) => (count ? `Scanning ${count} stock${count === 1 ? "" : "s"}…` : "Scanning…");

