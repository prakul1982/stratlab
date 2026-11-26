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


def _paras(s):
    return [str(p) for b in s.blocks if b["kind"] == "text" for p in b.get("paras") or []]


def test_a_layer_page_points_only_at_what_the_page_it_names_shows():
    # the live decks: "What the marks on its rows mean, and who is in its figures: p. 28", where p. 28 (Method and sources) has the key to the
    # marks and no layer's list of who is in its figures
    slides, _ = deck.theme_plan(_view())
    layers = [s for s in slides if s.title.startswith("Layer ")]
    assert layers
    said = " ".join(p for s in layers for p in _paras(s))
    assert "who is in its figures: p." not in said
    assert deck.MARKS_POINTER in said and deck.REASON_WHERE in said
    method = next(s for s in slides if s.title.startswith(deck.METHOD_TITLE))
    flat = " ".join(" ".join(deck._cell_text(x) for x in r) for b in method.blocks for r in b.get("rows") or [] if not isinstance(r, dict))
    assert "A word in brackets after a company's" in flat and "on the theme's page in StratLab" in flat
