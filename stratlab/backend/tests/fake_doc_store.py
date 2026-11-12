"""doc_store.DocStore's methods over dicts, for tests that don't need Postgres and for the browser tests' fake world
(tests/visual_server.py). The search is a plain approximation of Postgres's websearch_to_tsquery: every word (a word's
plural or "-ing" form counts), "quoted phrases" as written, -word left out, "or" between two words; the extract is the
words around the first match, marked as ts_headline marks them."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

MAX_TRIES = 4


def _stem(w: str) -> str:
    w = w.lower()
    for end in ("ing", "ies", "es", "s", "ed"):
        if len(w) > len(end) + 2 and w.endswith(end):
            return w[: -len(end)]
    return w


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", text or "")


def parse(q: str) -> tuple[list[list[str]], list[str]]:
    """([[alternatives: each a phrase as a list of stems]], [excluded stems]): every group must match."""
    groups: list[list[list[str]]] = []
    excluded: list[str] = []
    pending_or = False
    for m in re.finditer(r'(-?)"([^"]+)"|(-?)(\S+)', q or ""):
        neg = m.group(1) or m.group(3)
        text = m.group(2) if m.group(2) is not None else m.group(4)
        if m.group(4) and m.group(4).lower() == "or" and not neg:
            pending_or = True
            continue
        stems = [_stem(w) for w in _words(text)]
        if not stems:
            continue
        if neg:
            excluded += stems
            continue
        if pending_or and groups:
            groups[-1].append(stems)
        else:
            groups.append([stems])
        pending_or = False
    return groups, excluded


def _has(stems: list[str], phrase: list[str]) -> int:
    for i in range(len(stems) - len(phrase) + 1):
        if stems[i:i + len(phrase)] == phrase:
            return i
    return -1


class MemoryDocStore:
    def __init__(self):
        self.docs: dict[int, dict] = {}
        self.chunks: dict[tuple[int, int], dict] = {}
        self.queue: dict[str, dict] = {}
        self.next_id = 1
        self.saved: list[str] = []

    # ---- the queue
    def enqueue(self, rows):
        n = 0
        for r in rows:
            if r["url"] in self.queue or any(d["url"] == r["url"] for d in self.docs.values()):
                continue
            self.queue[r["url"]] = {**{k: r.get(k) for k in ("url", "region", "symbol", "kind", "filed_at", "title", "company", "sector")},
                                    "tries": 0, "next_at": datetime.now(timezone.utc), "last_error": None}
            n += 1
        return n

    def due(self, limit):
        now = datetime.now(timezone.utc)
        rows = [q for q in self.queue.values() if q["tries"] < MAX_TRIES and q["next_at"] <= now]
        rows.sort(key=lambda q: (q["filed_at"], q["url"]), reverse=True)
        return [dict(q) for q in rows[:limit]]

    def retry(self, url, error, delay_s, give_up=False):
        q = self.queue.get(url)
        if q:
            q["tries"] = MAX_TRIES if give_up else q["tries"] + 1
            q["last_error"] = error
            q["next_at"] = datetime.now(timezone.utc) + timedelta(seconds=delay_s)

    def save(self, doc, chunks):
        old = [i for i, d in self.docs.items() if d["url"] == doc["url"]]
        for i in old:
            self.delete(i)
        i, self.next_id = self.next_id, self.next_id + 1
        self.docs[i] = {"id": i, **{k: doc.get(k) for k in ("region", "symbol", "company", "sector", "kind", "title", "filed_at", "url", "host",
                                                            "pages", "ocr")},
                        "link": doc.get("link") or doc["url"], "chunks": len(chunks), "chars": sum(len(t) for _, t in chunks),
                        "indexed_at": datetime.now(timezone.utc).isoformat()}
        for n, (page, text) in enumerate(chunks):
            self.chunks[(i, n)] = {"page": page, "body": text}
        self.queue.pop(doc["url"], None)
        self.saved.append(doc["url"])
        return i

    def delete(self, doc_id):
        self.docs.pop(doc_id, None)
        for k in [k for k in self.chunks if k[0] == doc_id]:
            self.chunks.pop(k)

    def stored_urls(self, urls):
        have = {d["url"] for d in self.docs.values()} | set(self.queue)
        return {u for u in urls if u in have}

    # ---- searching
    def _match(self, body: str, groups, excluded) -> tuple[int, int] | None:
        stems = [_stem(w) for w in _words(body)]
        if any(e in stems for e in excluded):
            return None
        first, score = None, 0
        for alts in groups:
            hits = [p for p in (_has(stems, a) for a in alts) if p >= 0]
            if not hits:
                return None
            first = min(hits) if first is None else min(first, min(hits))
            score += sum(1 for a in alts for s in stems if s in a)
        return (first or 0, score) if groups else None

    def search(self, q, region, symbols=None, kinds=None, sectors=None, frm=None, to=None, limit=400):
        groups, excluded = parse(q)
        rows = []
        for (i, n), c in self.chunks.items():
            d = self.docs[i]
            if d["region"] != region or (symbols and d["symbol"] not in symbols) or (kinds and d["kind"] not in kinds) \
                    or (sectors and d.get("sector") not in sectors) or (frm and d["filed_at"] < frm) or (to and d["filed_at"] > to):
                continue
            m = self._match(c["body"], groups, excluded)
            if m:
                rows.append((i, n, c["page"], float(m[1]), d["filed_at"]))
        rows.sort(key=lambda r: (-r[3], r[4] and -date.fromisoformat(r[4]).toordinal(), -r[0], r[1]))
        return {"rows": rows[:limit], "by_date": False}

    def headlines(self, q, keys):
        groups, _ = parse(q)
        want = {s for alts in groups for a in alts for s in a}
        out = {}
        for k in keys:
            c = self.chunks.get(tuple(k))
            if not c:
                continue
            words = c["body"].split()
            at = next((j for j, w in enumerate(words) if any(_stem(x) in want for x in _words(w))), 0)
            start = max(0, at - 10)
            frag = [f"\x02{w}\x03" if any(_stem(x) in want for x in _words(w)) else w for w in words[start:start + 35]]
            out[tuple(k)] = " ".join(frag)
        return out

    def documents(self, ids):
        return {i: dict(self.docs[i]) for i in ids if i in self.docs}

    def coverage(self):
        out = {}
        for d in self.docs.values():
            r = out.setdefault(d["region"], {"documents": 0, "companies": set(), "newest": None, "oldest": None, "kinds": {}})
            r["documents"] += 1
            r["companies"].add(d["symbol"])
            r["kinds"][d["kind"]] = r["kinds"].get(d["kind"], 0) + 1
            r["newest"] = max(filter(None, [r["newest"], d["filed_at"]]))
            r["oldest"] = min(filter(None, [r["oldest"], d["filed_at"]]))
        for r in out.values():
            r["companies"] = len(r["companies"])
        return out

    def sectors(self):
        out: dict[str, list[str]] = {}
        for d in self.docs.values():
            if d.get("sector") and d["sector"] not in out.setdefault(d["region"], []):
                out[d["region"]].append(d["sector"])
        return {k: sorted(v) for k, v in out.items()}

    def queue_stats(self):
        waiting = [q for q in self.queue.values() if q["tries"] < MAX_TRIES]
        failed = [q for q in self.queue.values() if q["tries"] >= MAX_TRIES]
        return {"waiting": len(waiting), "failed": len(failed), "due": len(self.due(10**6)),
                "bytes": sum(len(c["body"]) for c in self.chunks.values()),
                "failures": [{"symbol": q["symbol"], "title": q["title"], "error": q["last_error"]} for q in failed[:5]]}
