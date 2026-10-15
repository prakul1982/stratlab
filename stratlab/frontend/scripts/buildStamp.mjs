// The frontend's own build, stamped into the bundle (R24-009: no build or version was visible anywhere). From what Vercel sets
// while it builds (VERCEL_GIT_COMMIT_SHA, VERCEL_GIT_COMMIT_REF, VERCEL_ENV), only those names: never a key or token.

const SHA = /^[0-9a-f]{7,40}$/;
const SAFE = /^[\w./@+-]{1,80}$/;

/** {sha, ref, env, built_at}: the commit, its branch, the Vercel environment and when this bundle was built. */
export function buildStamp(env = process.env, now = new Date()) {
  const sha = String(env.VERCEL_GIT_COMMIT_SHA ?? env.GIT_COMMIT_SHA ?? "").trim().toLowerCase();
  const ref = String(env.VERCEL_GIT_COMMIT_REF ?? "").trim();
  const where = String(env.VERCEL_ENV ?? "").trim();
  return { sha: SHA.test(sha) ? sha : null, ref: SAFE.test(ref) ? ref : null, env: SAFE.test(where) ? where : null, built_at: now.toISOString() };
}
