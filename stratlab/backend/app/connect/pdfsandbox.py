"""Reads an untrusted statement PDF in a child process with a memory and a time limit.

A PDF a few hundred kilobytes long can unpack to gigabytes (a zip-bomb stream), and reading it in the server's own process
would use all its memory and take the API down for everyone. Here the read happens in a separate Python process (pdfchild.py)
with RLIMIT_AS, RLIMIT_CPU and a wall-clock timeout, started with an empty environment (no keys, no database address). The
child hands back casparser's own JSON, which is loaded into casparser's typed models again here; nothing is unpickled.

Used for every read of a CAS PDF: the statement inbox, the manual upload and the mutual-funds import."""
import json
import os
import subprocess
import sys

MEMORY_LIMIT = 1536 * 1024 * 1024        # address space of the child (a 5 MB statement needs a fraction of this)
CPU_SECONDS = 60
WALL_SECONDS = 90
MAX_OUTPUT = 64 * 1024 * 1024
CHILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdfchild.py")


class SandboxError(Exception):
    """The child failed. `kind`: "password", "parse" (not a statement), "limit" (too big or too slow) or "other"."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def _limits():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ImportError, ValueError, OSError):
        pass


def run(data: bytes, password: str) -> dict:
    """casparser's result as a dict. Raises SandboxError."""
    args = [sys.executable, "-I", CHILD]
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                                preexec_fn=_limits if os.name == "posix" else None, close_fds=True)
    except OSError:
        raise SandboxError("other") from None
    try:
        out, _ = proc.communicate(json.dumps({"pw": password or ""}).encode() + b"\n" + data, timeout=WALL_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise SandboxError("limit") from None
    except OSError:                                          # the child ended before it read everything
        proc.kill()
        proc.communicate()
        raise SandboxError("limit") from None
    if proc.returncode != 0 or not out or len(out) > MAX_OUTPUT:
        raise SandboxError("limit")                          # killed by a limit (memory, time) or crashed
    try:
        res = json.loads(out)
    except ValueError:
        raise SandboxError("other") from None
    if not isinstance(res, dict):
        raise SandboxError("other")
    if "ok" not in res:
        raise SandboxError(str(res.get("err") or "other"))
    try:
        doc = json.loads(res["ok"])
    except (ValueError, TypeError):
        raise SandboxError("other") from None
    if not isinstance(doc, dict):
        raise SandboxError("other")
    return doc


def read_cas(data: bytes, password: str):
    """casparser's typed result (CASData for CAMS and KFintech, NSDLCASData for NSDL and CDSL). Raises SandboxError."""
    from casparser.types import CASData, NSDLCASData
    doc = run(data, password)
    try:
        return (CASData if "folios" in doc else NSDLCASData).model_validate(doc)
    except Exception:
        raise SandboxError("other") from None
