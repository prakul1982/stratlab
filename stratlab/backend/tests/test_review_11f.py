"""Review 11f: StratLab exports import as they were; an imported instrument with no id asks which instrument."""
import json

from app import importer
from tests.test_notebooks import api  # noqa


def cond(i):
    return {"l": {"t": "ema", "p": 10 + i}, "op": "xa", "r": {"t": "ema", "p": 30 + i}, "w": 1.5}


def big(n=12, text=4000, members=50):
    s = {"name": "Big", "tf": "1d", "text": "x" * text, "entry": [cond(i) for i in range(n)], "exit": [cond(i) for i in range(n)],
         "side": "both", "shortEntry": [cond(i) for i in range(n)], "shortExit": [cond(i) for i in range(n)]}
    body = {"strategy": s}
    if members:
        body["group"] = {"id": "custom", "name": "G", "market": "IN", "members": [{"symbol": f"SYM{i}"} for i in range(members)], "maxOpen": 5}
    return body


def test_big_export_is_compact_and_imports_as_it_was(api):
    r = api.post("/export/strategy", json=big())
    assert r.status_code == 200
    assert "\n" not in r.text
    r2 = api.post("/import/strategy", json={"text": r.text, "filename": "Big.json"})
    assert r2.status_code == 200, r2.text
    out = r2.json()
    assert out["source"] == "stratlab" and out["used_ai"] is False
    assert len(out["strategy"]["entry"]) == 12 and len(out["group"]["members"]) == 50


def test_export_over_the_old_limit_is_accepted():
    text = json.dumps({"format": "stratlab-strategy-v1", "pad": "y" * 30000, "strategy": big(1, 10, 0)["strategy"]})
    assert len(text) > 20000
    from app.models import ImportReq
    ImportReq(text=text)


def test_broken_stratlab_json_is_a_bad_import_not_text_for_the_ai(api):
    r = api.post("/export/strategy", json=big(3, 100, 0))
    cut = r.text[: len(r.text) // 2]
    assert importer.detect(cut) == "stratlab"
    r2 = api.post("/import/strategy", json={"text": cut, "filename": "x.json"})
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "bad_import"


def test_instrument_object_without_id_is_not_given():
    s = big(1, 10, 0)["strategy"]
    out = importer.from_json(json.dumps({"format": "stratlab-strategy-v1", "instrument": {"symbol": "X"}, "strategy": s}))
    assert out["instrument_id"] is None
    assert "instrument" not in out["mentioned"]
    out = importer.from_json(json.dumps({"format": "stratlab-strategy-v1", "instrument": {"id": "IN:1", "symbol": "X"}, "strategy": s}))
    assert out["instrument_id"] == "IN:1" and "instrument" in out["mentioned"]


def test_st_s2_seed_and_scan_template_share_a_position_cap():
    from app import library_seed, scan
    seed = {**library_seed.RISK, **library_seed.STRATEGIES["st-s2"]["body"]["risk"]}
    assert seed["maxAlloc"] == scan.ST_S2["risk"]["maxAlloc"] == 20
