"""deck96 (owner, 26 Nov: "ok go ahead"): every live theme deck checked for the classes of problem the Alcoholic beverages deck had
(Releases 90-92), each one found fixed as a rule for every theme."""
import copy
import functools

from app import deck
from tests.alcobev_fixture import alco_view


@functools.lru_cache(maxsize=None)
def _alco():
    return alco_view()


def _view():
    return copy.deepcopy(_alco())


def _texts(slides, title):
    out = []
    for s in slides:
        if s.title.startswith(title):
            for b in s.blocks:
                for r in b.get("rows") or []:
                    out += [deck._cell_text(x) for x in ([] if isinstance(r, dict) else r)]
    return out


def test_a_whole_company_mark_is_said_once_in_size_and_shape():
    # the live Capital goods deck: "Larsen & Toubro Limited (whole company) (whole company)" in Size and shape
    v = _view()
    big = v["sections"]["size"]["biggest"]
    big[0]["whole"] = True
    v["company_wide"] = sorted(set(v.get("company_wide") or []) | {big[0]["symbol"]})
    slides, _ = deck.theme_plan(v)
    cells = _texts(slides, "Size and shape")
    assert any("(whole company)" in c for c in cells), cells[:6]
    assert not any("(whole company) (whole company)" in c for c in cells), cells[:6]
