"""Which build of the server is running (R24-009: Admin showed no build, /health had no version and /version was a 404),
from what the host sets in the environment. Railway sets RAILWAY_GIT_COMMIT_SHA, RAILWAY_GIT_BRANCH, RAILWAY_DEPLOYMENT_ID
and RAILWAY_ENVIRONMENT_NAME on every deploy from GitHub; it has no build time, so BUILD_TIME is read when the deploy sets
it, and the time this server started is given beside it. Only these names are read: never a key, token or any other
variable, so nothing secret can come out."""
import os
import re
from datetime import datetime, timezone

STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")

SHA_VARS = ("RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT_SHA", "SOURCE_COMMIT", "COMMIT_SHA")
BRANCH_VARS = ("RAILWAY_GIT_BRANCH", "GIT_BRANCH")
_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_SAFE = re.compile(r"^[\w./@+-]{1,80}$")


def _first(names, env) -> str | None:
    for n in names:
        v = (env.get(n) or "").strip()
        if v:
            return v
    return None


def info(env=None) -> dict:
    """{"sha", "short", "branch", "built_at", "started_at", "environment", "deployment"}: whatever the host gave, else None.
    A value that doesn't look like what it should be (a sha of hex digits, a plain branch name) is left out."""
    env = os.environ if env is None else env
    sha = (_first(SHA_VARS, env) or "").lower()
    sha = sha if _SHA.match(sha) else None
    branch = _first(BRANCH_VARS, env)
    built = _first(("BUILD_TIME",), env)
    try:
        built = datetime.fromisoformat(built.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(timespec="seconds") if built else None
    except ValueError:
        built = None
    environment, deployment = env.get("RAILWAY_ENVIRONMENT_NAME"), env.get("RAILWAY_DEPLOYMENT_ID")
    return {"sha": sha, "short": sha[:7] if sha else None, "branch": branch if branch and _SAFE.match(branch) else None,
            "built_at": built, "started_at": STARTED_AT,
            "environment": environment if environment and _SAFE.match(environment) else None,
            "deployment": deployment if deployment and _SAFE.match(deployment) else None}
