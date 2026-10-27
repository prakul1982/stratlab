"""The Cost Inflation Index (section 48, Explanation (v)): the CBDT's yearly figure, base year FY 2001-02 = 100, used to
index the cost of a long-term asset sold before 23 July 2024 (RC3M-007). Keyed by the financial year's first year, so
2024 is FY 2024-25. The series is CBDT Notification No. 44/2017 (base 2001-02) and the yearly notifications after it;
the figures to FY 2024-25 (363) are the notified ones, FY 2025-26 (376) is the latest."""

CII = {2001: 100, 2002: 105, 2003: 109, 2004: 113, 2005: 117, 2006: 122, 2007: 129, 2008: 137, 2009: 148, 2010: 167,
       2011: 184, 2012: 200, 2013: 220, 2014: 240, 2015: 254, 2016: 264, 2017: 272, 2018: 280, 2019: 289, 2020: 301,
       2021: 317, 2022: 331, 2023: 348, 2024: 363, 2025: 376}


def ratio(bought_fy: int, sold_fy: int) -> float | None:
    """The index of the sale's year over the index of the year the asset was bought (cost x this = indexed cost), or None
    when either year is outside the table (an asset bought before 1 April 2001 is indexed from its 1 April 2001 value,
    which no file has)."""
    b, s = CII.get(bought_fy), CII.get(sold_fy)
    return None if b is None or s is None else s / b
