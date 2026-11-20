"""Lane e83 (Release 82): theme-engine items from LIVE19A/B and the R81 decks. Each test fails before its fix and passes after, except those
marked as guards."""
from app.intel import sector_metrics as SM


# ---------- 3. LIVE19A-002/005: the FFO a REIT reports, read from the row that is the FFO itself ----------
# Each excerpt is the filing's own text (FY2025 10-K, SEC EDGAR), as StratLab reads it (sec.html_text, spaces joined)
ESSEX_10K = (
    "The table below is a reconciliation of net income available to common stockholders to FFO and Core FFO for the periods presented ($ in "
    "thousands, except per share amounts): Year Ended December 31, 2025 2024 2023 Net income available to common stockholders $ 669,666 $ "
    "741,522 $ 405,825 Adjustments: Depreciation and amortization 607,542 580,220 548,438 Gains not included in FFO (305,043) (386,138) "
    "(59,238) Casualty loss — — 433 Impairment loss from unconsolidated co-investments 12,634 3,726 33,700 Depreciation and amortization from "
    "unconsolidated co-investments 56,848 66,943 71,745 Noncontrolling interest related to Operating Partnership units 23,649 26,414 14,284 "
    "Depreciation attributable to third party ownership and other (160) 31,191 (1,474) Funds from operations attributable to common "
    "stockholders and unitholders $ 1,065,136 $ 1,063,878 $ 1,013,713 FFO per share-diluted $ 15.98 $ 15.99 $ 15.24 Non-core items: "
    "Expensed acquisition and investment related costs $ 25 $ 72 $ 595")
AMT_10K = (
    "Year Ended December 31, Percent Change 2025 vs 2024 2025 2024 Net income (1) $ 2,628.5 $ 2,280.2 15 % Real estate related depreciation, "
    "amortization and accretion 1,899.6 1,879.6 1 Losses from sale or disposal of real estate and real estate related impairment charges (2) "
    "83.5 91.6 (9) Adjustments and distributions for unconsolidated affiliates and noncontrolling interests (3) (450.7) (352.7) 28 Adjustments "
    "for discontinued operations (4) — 1,334.5 (100) Nareit FFO attributable to American Tower Corporation common stockholders $ 4,160.9 $ "
    "5,233.2 (20) % Straight-line revenue (101.0) (277.6) (64)")
KIMCO_10K = (
    "Depreciation and amortization - real estate related 153,001 154,905 622,530 598,741 Noncontrolling interests (1) (756 ) (783 ) (3,009 ) "
    "(3,150 ) FFO available to the Company’s common shareholders (3) (4) $ 294,327 $ 286,901 $ 1,194,094 $ 1,112,076 Weighted average shares "
    "outstanding for FFO calculations: Basic 673,914 673,676 675,050 671,561")
BXP_10K = (
    "Noncontrolling interests in property partnerships 75,181 67,516 78,661 Funds from Operations (FFO) attributable to the Operating "
    "Partnership common unitholders (including BXP, Inc.) 1,209,636 1,248,026 1,274,568 Less: Noncontrolling interest—common units of the "
    "Operating Partnership’s share of funds from operations 120,601 127,548 130,771 Funds from Operations attributable to BXP, Inc. $ "
    "1,089,035 $ 1,120,478 $ 1,143,797")
PLD_10K = (
    "(in millions) Net earnings attributable to common stockholders $ 3,322 $ 3,726 Add (deduct) NAREIT defined adjustments: Real estate "
    "related depreciation and amortization 2,588 2,506 NAREIT defined FFO attributable to common stockholders/unitholders $ 5,680 $ 5,795 "
    "Add (deduct) our modified adjustments: FFO, as modified by Prologis attributable to common stockholders/unitholders $ 5,779 $ 5,741 "
    "Core FFO attributable to common stockholders/unitholders $ 5,561 $ 5,305")
ARE_JV_10K = (
    "Straight-line rent and below-market lease revenue $ 2,723 $ 19,580 $ 139 $ 645 Funds from operations (4) $ 77,922 $ 320,030 $ 526 $ "
    "2,262 Refer to “ Joint venture financial information ” ... (in thousands) Unvested restricted stock awards (5,681) (8,696) (5,175) Funds "
    "from operations attributable to Alexandria Real Estate Equities, Inc.’s common stockholders – diluted (3) 1,310,607 1,431,750 1,577,598 "
    "... Funds from operations attributable to Alexandria Real Estate Equities, Inc.’s common stockholders – diluted, as adjusted $ 1,534,664")


def test_e83_essex_reported_ffo_is_the_years_ffo_row_never_the_gains_not_included_in_ffo():
    """LIVE19A-002: Essex "$305 m (reported)", P/FFO 56.80x, from "Gains not included in FFO (305,043)"; its 10-K: $1,065.1 m."""
    assert SM.reported_ffo(ESSEX_10K) == 1065.1
    got = SM.with_reported_ffo({"ffo": {"v": 977.7, "period": "Fiscal year to Dec 2025", "source": "derived"}}, ESSEX_10K, 1887.3)
    assert got["ffo"]["v"] == 1065.1 and got["ffo"]["basis"] == "reported" and got["ffo_derived"]["v"] == 977.7
    assert got["ffo_share"]["v"] == 56.4


def test_e83_american_tower_and_other_labels_of_reported_ffo_are_read():
    """LIVE19A-005: American Tower's "Nareit FFO attributable to American Tower Corporation common stockholders $ 4,160.9" (millions) was
    missed (shown derived $4.57 bn), as were Prologis' "NAREIT defined FFO", Kimco's year column and BXP's company row."""
    assert SM.reported_ffo(AMT_10K) == 4160.9
    assert SM.reported_ffo(PLD_10K) == 5680.0                       # never the "as modified" or Core rows
    assert SM.reported_ffo(BXP_10K) == 1089.0                       # never the noncontrolling units' "share of funds from operations"
    assert SM.reported_ffo(KIMCO_10K, near=1211.8) == 1194.1        # the year's column, not the quarter's, beside its derived FFO
    assert SM.reported_ffo("Public Storage (amounts in thousands) Eliminate items excluded from FFO: Real estate-related depreciation and "
                           "amortization 1,140,377 1,117,752 FFO allocable to common shares $ 2,780,451 $ 3,025,914 (8.1) %") == 2780.5
    assert SM.reported_ffo("(in thousands) Provision for impairment 78,553 191,185 FFO available to common stockholders and unitholders (2) "
                           "$ 2,399,032 $ 2,027,124 $ 1,915,747 Basic FFO per share and unit $ 6.94") == 2399.0
    assert SM.reported_ffo("(in thousands) distributions and dividends (4,503) (4,897) FFO of the Operating Partnership $ 4,663,305 $ "
                           "4,876,844 FFO allocable to limited partners 636,189 640,886") == 4663.3


def test_e83_a_joint_ventures_row_or_a_figure_far_from_the_derived_one_is_never_the_reported_ffo():
    assert SM.reported_ffo(ARE_JV_10K) == 1310.6                    # the company's own (attributable) row before a bare JV table row
    assert SM.reported_ffo("(in thousands) Funds from operations $ 77,922 $ 320,030", near=1500.0) is None
    assert SM.reported_ffo("(in thousands) Funds from operations $ 77,922", revenue=3026.6) is None          # 2.6% of revenue
    assert SM.REIT_V >= 3                                            # every property owner's piece read again


def test_e83_guards_camden_and_core_lines():
    """Guards: Camden's $744.8 m (e81) still read; Core, Normalized and per-share lines never."""
    from tests.test_e81 import CAMDEN_10K
    assert SM.reported_ffo(CAMDEN_10K) == 744.8
    assert SM.reported_ffo("(in thousands) Core FFO $ 762,551 and Normalized FFO $ 700,000 and FFO per diluted share $ 6.79") is None
    assert SM.reported_ffo("Computation of FFO and Normalized FFO: Net income available for Common Stockholders $ 386,492 $ 366,998") is None
