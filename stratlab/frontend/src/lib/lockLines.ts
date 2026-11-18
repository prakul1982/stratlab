/** One plan note for a card whose parts each keep something back for a plan: the parts joined in one sentence when they name the same plan,
 * else each its own note (LIVE13B-007). */
export function lockLines(locks: ({ what: string; plan: string } | null)[]): string[] {
  const got = locks.filter((l): l is { what: string; plan: string } => !!l);
  const plans = [...new Set(got.map((l) => l.plan))];
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
  return plans.map((p) => {
    const parts = got.filter((l) => l.plan === p).map((l) => l.what);
    return `${cap(parts.length > 1 ? `${parts.slice(0, -1).join("; ")}; and ${parts[parts.length - 1]}` : parts[0])} are on the ${p} plan.`;
  });
}

