/** "1 of your stocks is waiting to be read", "3 of your stocks are waiting…" (R29B-023). */
export const waitingLine = (n: number): string =>
  `${n} of your stocks ${n === 1 ? "is" : "are"} waiting to be read: they are read each evening after they're filed.`;
