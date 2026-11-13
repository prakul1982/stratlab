"""Release 43.1: the data checks count margins filed in whole points among the margins there are. A company with no EBITDA margin
(most insurers) filed none, in whole points or otherwise; the live Insurance deck said "3 of the 1 EBITDA margins are filed in whole
points" because its rows' filing precision was counted without a margin to go with it."""
from app.intel import theme_data as D


def test_whole_points_never_exceed_the_margins_counted():
    rows = [{"symbol": "A", "name": "A", "ebitda": 12.0, "net": 5.0, "ebitda_dp": 0},
            {"symbol": "B", "name": "B", "ebitda": None, "net": None, "ebitda_dp": 0},
            {"symbol": "C", "name": "C", "ebitda": None, "net": None, "ebitda_dp": 0},
            {"symbol": "D", "name": "D", "ebitda": 7.5, "net": 3.0, "ebitda_dp": 1}]
    ch = D.data_checks(rows, [], {"sections": {}})
    assert (ch["whole_points"], ch["with_ebitda"]) == (1, 2)
    assert ch["whole_points"] <= ch["with_ebitda"]


def test_no_margin_at_all_makes_no_precision_claim():
    rows = [{"symbol": s, "name": s, "ebitda": None, "net": None, "ebitda_dp": 0} for s in "XYZ"]
    ch = D.data_checks(rows, [], {"sections": {}})
    assert (ch["whole_points"], ch["with_ebitda"]) == (0, 0)
    assert not D.mostly_whole(ch["whole_points"], ch["with_ebitda"])
