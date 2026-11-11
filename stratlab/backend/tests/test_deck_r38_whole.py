"""R38: names are never cut or broken inside a word when a whole form of them fits (the live R36 Semiconductors deck)."""
from app import deck


def test_foreign_legal_endings_are_left_off_a_label_before_any_of_it_is_cut():
    assert "NXP Semiconductors" in deck.label_forms("NXP Semiconductors N.V.")
    assert "STMicroelectronics" in deck.label_forms("STMicroelectronics N.V.")
    assert "Siemens" in deck.label_forms("Siemens AG")
    assert "Banco Santander" in deck.label_forms("Banco Santander, S.A.")
    # capitals only: an English last word is not a legal ending
    assert deck.label_forms("Bank of America") == ["Bank of America"]
    assert all(f != "Oasis" for f in deck.label_forms("Oasis Ab"))


def test_a_table_cell_word_is_never_broken_inside_when_the_table_has_room():
    head = ["Company", "Revenue", "EBITDA margin", "Net margin", "ROCE", "Year"]
    rows = [["Texas Instruments Inc", "$17.7 bn", "44.9%", "28.3%", "19.9%", "Dec 2025"],
            ["Analog Devices Inc", "$9.4 bn", "30.3%", "18.1%", "7.2%", "Oct 2025"]]
    b = {"head": head, "rows": rows, "widths": [0.9, 1.6, 1.6, 1.6, 1.6, 1.6]}
    lay = deck.table_layout(b, 7.0, 3.0)
    cw = lay["widths"][0]
    for r in rows:
        for line in deck.wrap(r[0], lay["size"], cw - 0.2):
            assert line in r[0].split() or " " in line or line in r[0], line
        words = r[0].split()
        assert all(any(wd == part or wd in part.split() for part in deck.wrap(r[0], lay["size"], cw - 0.2)) for wd in words)
