"""Round 36 (16 Oct, visitor pages): the /stocks lists show company names as the company pages do."""
from app import stock_pages


def test_a_re_registration_mark_and_a_mixed_case_ending_are_tidied():
    assert stock_pages.proper_name("COSTCO WHOLESALE CORP /NEW") == "Costco Wholesale Corp"
    assert stock_pages.proper_name("ELI LILLY & Co") == "Eli Lilly & Co"
    assert stock_pages.proper_name("TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD") == "Taiwan Semiconductor Manufacturing Co Ltd"
    assert stock_pages.proper_name("ExxonMobil Holdings Corp") == "ExxonMobil Holdings Corp"
    assert stock_pages.proper_name("Apple Inc.") == "Apple Inc."


def test_the_company_lists_use_the_tidy_name():
    html = stock_pages._links("us", [("COST", "COSTCO WHOLESALE CORP /NEW"), ("NVDA", "NVIDIA CORP"), ("XYZ", "XYZ")])
    assert "Costco Wholesale Corp (COST)" in html and "NVIDIA Corp (NVDA)" in html
    assert "/NEW" not in html and ">XYZ<" in html


def test_indian_names_keep_their_acronyms():
    html = stock_pages._links("in", [("ITC", "ITC LTD"), ("ICICIBANK", "ICICI Bank Ltd")])
    assert "ITC LTD (ITC)" in html and "ICICI Bank Ltd (ICICIBANK)" in html
