"""A PDF's page texts, read in a short-lived child process when the file is large (SECMEM item 2).

Reading a big PDF (an IPO offer document of 15-40 MB and 230 pages, a 20 MB investor deck) makes millions of small
objects for a few seconds. They are freed afterwards, but the server runs with the C allocator for every object
(PYTHONMALLOC=malloc, Procfile) and the heap they were spread over stays mostly in the process: Railway showed 1.2-2.1 GB
resident with ~120 MB of it Python's own (31 Oct, 4 Nov: /admin/memory?detail=true), growing on the days the offer
documents were read again after the reader changed and the Business updates ran over the NIFTY 100. A child process
gives all of it back when it exits, and its own address space is capped, so one odd file can't take the server down.
Small files (an exchange filing of a few pages) are read here as before: a process start costs more than they do."""

import io
import json
import os
import subprocess
import sys

SUBPROCESS_BYTES = 1024 * 1024         # files at least this big are read in a child process (a 1.2 MB file read 4 times kept 23 MB here)
CHILD_MEMORY_MB = 900                  # the child's address-space cap: past it the read fails, not the server
CHILD_TIMEOUT_S = 240

# The child: reads {"max_pages"} and the PDF from stdin, writes {"pages": [...], "count": n} or {"error": name}.
# It imports only pypdf (none of the app), under -I so nothing from the working directory or the environment loads.
CHILD = r"""
import io, json, resource, sys
mb = int(sys.argv[1])
try:
    resource.setrlimit(resource.RLIMIT_AS, (mb << 20, mb << 20))
except (ValueError, OSError):
    pass
raw = sys.stdin.buffer.read()
head, _, data = raw.partition(b"\n")
max_pages = json.loads(head)["max_pages"]
try:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    out = []
    for page in reader.pages[:max_pages]:
        try:
            out.append(page.extract_text() or "")
        except MemoryError:
            raise
        except Exception:                   # one bad page mustn't lose the document
            out.append(None)
    res = {"pages": out, "count": len(reader.pages)}
except MemoryError:
    res = {"error": "MemoryError"}
except Exception as e:
    res = {"error": type(e).__name__}
sys.stdout.write(json.dumps(res))
"""


class PdfUnreadable(Exception):
    """The PDF couldn't be read as a whole; the message names why (the reader's error, or the child's memory cap)."""


def _here(data: bytes, max_pages: int) -> tuple[list[str | None], int]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    out: list[str | None] = []
    for page in reader.pages[:max_pages]:
        try:
            out.append(page.extract_text() or "")
        except Exception:
            out.append(None)
    return out, len(reader.pages)


def _child(data: bytes, max_pages: int) -> tuple[list[str | None], int]:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TZ", "HOME")}
    try:
        r = subprocess.run([sys.executable, "-I", "-c", CHILD, str(CHILD_MEMORY_MB)],
                           input=json.dumps({"max_pages": max_pages}).encode() + b"\n" + data,
                           capture_output=True, timeout=CHILD_TIMEOUT_S, env=env)
    except subprocess.TimeoutExpired:
        raise PdfUnreadable("TimeoutExpired") from None
    try:
        res = json.loads(r.stdout or b"{}")
    except ValueError:
        res = {}
    if "pages" not in res:
        # a child killed by the cap or a signal leaves no answer: say so rather than reading it here after all
        raise PdfUnreadable(res.get("error") or f"exit {r.returncode}")
    return res["pages"], int(res["count"])


def page_texts(data: bytes, max_pages: int) -> tuple[list[str | None], int]:
    """(each of the first `max_pages` pages' text, None for a page that couldn't be read; the page count). Raises the
    reader's own error for a small file and PdfUnreadable for a large one that couldn't be read."""
    if len(data) < SUBPROCESS_BYTES:
        return _here(data, max_pages)
    try:
        return _child(data, max_pages)
    except OSError:                          # no process could be started (the host's limit): read it here
        return _here(data, max_pages)
