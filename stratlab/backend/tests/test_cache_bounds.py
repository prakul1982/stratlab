"""Caches stay bounded in memory: the whole-market audit walks every company, and an item count alone let large
responses (SEC company facts, page HTML, candles) fill the server's memory until it was killed."""
from app.intel.net import SizedDict, TTLCache, approx_size


def test_ttl_cache_is_bounded_by_size_not_only_count():
    c = TTLCache(max_items=10_000, max_bytes=1_000_000)
    for i in range(500):
        c.set(i, "x" * 20_000, ttl=600)                  # 500 x 20 KB = 10 MB offered
    assert c.bytes <= 1_000_000 and len(c._d) < 60
    assert c.get(499) is not None and c.get(0) is None   # the newest kept, the oldest dropped


def test_ttl_cache_skips_one_huge_value_and_counts_given_sizes():
    c = TTLCache(max_items=10, max_bytes=1_000)
    c.set("big", "y", ttl=60, size=5_000)
    assert c.get("big") is None and c.bytes == 0
    c.set("a", "z", ttl=60, size=100)
    c.set("a", "z", ttl=60, size=100)                    # replacing an entry doesn't double count it
    assert c.bytes == 100


def test_sized_dict_keeps_the_dict_shape_and_stays_bounded():
    d = SizedDict(max_items=1000, max_bytes=500_000)
    for i in range(200):
        d[i] = (0.0, [{"t": j, "o": 1.0, "c": 2.0} for j in range(100)])
    assert d.bytes <= 500_000 and len(d) < 200 and 199 in d
    assert d.get(199)[1][0]["t"] == 0 and d.get(-1) is None
    assert d.pop(199)[0] == 0.0 and 199 not in d


def test_approx_size_grows_with_content_and_stops_early_on_huge_values():
    assert approx_size("a" * 1000) > approx_size("a")
    huge = [{"k": i} for i in range(200_000)]
    assert approx_size(huge) > 1_000_000                 # extrapolated past the node budget, not undercounted
