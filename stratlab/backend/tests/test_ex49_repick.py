"""Lane ex49 (Release 49), owner ask (a): an owner-only switch that clears a theme's stored industry pick so the AI picks again.

Before this release production had no such switch: lanes cv47 and cl48 could only advise "delete the stored setting
theme:industries:US:consumer-retail". POST /admin/themes/industries/repick {region, theme} clears that setting (generic: any market, any
theme), drops the theme's checked maps kept under the old pick (so the next read checks the theme again on a new pick, not a day later),
and writes one audit line. Admin only."""
import json

import pytest
from fastapi.testclient import TestClient

from app import admin, computed, db, main
from app.intel import ai as A
from app.intel import theme_base as B
from app.intel import theme_routes as TR
from tests.test_r19_library import Store


@pytest.fixture
def store(monkeypatch):
    s = Store()
    monkeypatch.setattr(db, "get_setting", lambda k: s.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: s.__setitem__(k, v))
    monkeypatch.setattr(db, "update_setting", s.update_setting)
    monkeypatch.setattr(db, "delete_setting", lambda k: s.pop(k, None))
    computed.reset_for_tests()
    A._missed.clear()
    yield s
    main.app.dependency_overrides.pop(admin.admin_profile, None)
    main.app.dependency_overrides.pop(main.current_profile, None)


KEY = "theme:industries:US:consumer-retail"
PICK = {"at": "2026-11-01T10:00:00+00:00", "industries": ["Retail-Retail Stores, Nec", "Retail-Variety Stores"], "rules": 45}


def kept_check(region, theme, gen, rules):
    key = (region, theme.lower(), gen, rules)
    A.keep("sector_checked3", key, {"value_chain": [], "placements": {"checked": True}, "generated_at": gen}, 24 * 3600)
    return key


def test_the_owner_clears_a_stored_pick_and_the_ai_picks_again_on_the_next_read(store):
    store[KEY] = json.dumps(PICK)
    store["theme:industries:US:semiconductors"] = json.dumps(PICK)          # another theme's pick stays
    mine = kept_check("US", "Consumer retail", 1794127179, B.RULES)
    other = kept_check("US", "Semiconductors", 1794127179, B.RULES)
    c = TestClient(main.app)
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "_plan": "pro", "plan": "pro"}
    assert c.post("/admin/themes/industries/repick", json={"region": "US", "theme": "Consumer retail"}).status_code == 403     # admin only
    assert store.get(KEY)
    main.app.dependency_overrides[admin.admin_profile] = lambda: {"id": "ad", "email": "owner@example.com"}
    got = c.post("/admin/themes/industries/repick", json={"region": "us", "theme": "Consumer retail"}).json()
    assert got["ok"] and got["cleared"] and got["region"] == "US" and got["theme"] == "consumer-retail"
    assert got["industries"] == PICK["industries"] and got["picked_at"] == PICK["at"] and got["checked_maps_dropped"] == 1
    assert KEY not in store and "theme:industries:US:semiconductors" in store
    assert A.get("sector_checked3", mine) is None and A.get("sector_checked3", other) is not None
    # the audit line: kept (newest last) and in the server's log
    log = json.loads(store[TR.REPICK_LOG])
    assert log[-1]["by"] == "owner@example.com" and log[-1]["theme"] == "consumer-retail" and log[-1]["industries"] == PICK["industries"]
    # the next read: no pick stored, so the AI is asked (and its pick kept under today's rules)
    asked = []

    def ask(system, text):
        asked.append(text)
        return {"industries": ["Retail-Family Clothing Stores"]}
    rows = [{"symbol": "GAP", "industry": "Retail-Family Clothing Stores"}, {"symbol": "X", "industry": "Retail-Retail Stores, Nec"}]
    out = B.industries_for("US", "Consumer retail", rows, ask, db.get_setting, db.set_setting)
    assert asked and out["how"] == "ai" and json.loads(store[KEY])["rules"] == B.RULES
    # nothing stored: said so, nothing broken
    again = c.post("/admin/themes/industries/repick", json={"region": "US", "theme": "Nothing stored here"}).json()
    assert again["ok"] and not again["cleared"] and "No industry pick is stored" in again["message"]
    assert c.post("/admin/themes/industries/repick", json={"region": "EU", "theme": "x"}).status_code == 400
    assert len(json.loads(store[TR.REPICK_LOG])) == 2


def test_a_kept_pick_is_used_without_the_switch(store):
    # the switch is the only thing that clears it: a read with the pick stored asks no AI (cv47's PICK_RULES)
    store[KEY] = json.dumps({**PICK, "at": "2026-11-12T10:00:00+00:00"})
    rows = [{"symbol": "X", "industry": "Retail-Retail Stores, Nec"}]
    out = B.industries_for("US", "Consumer retail", rows, lambda s, t: pytest.fail("asked"), db.get_setting, db.set_setting,
                           now=B.datetime(2026, 11, 13, tzinfo=B.timezone.utc))
    assert out["how"] == "ai" and out["industries"] == ["Retail-Retail Stores, Nec"]
