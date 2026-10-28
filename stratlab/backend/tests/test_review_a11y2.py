"""A11Y-2 (28 Oct 2026): accessibility of the pages the API draws (company pages, directories, blog), held in place. The browser checks are in
frontend/e2e/a11y.spec.ts and public-pages.spec.ts; these are the facts about the page source that a browser check can't see."""
from app import stock_pages


def test_the_chart_is_a_slider_over_the_closes_a_screen_reader_can_use_in_browse_mode():
    js = stock_pages.CHART_JS
    # a picture with key handlers keeps its arrow keys from a screen reader in browse mode; a slider is handed them and says its value
    assert 'role: "slider"' in js and 'role: "img"' not in js
    for part in ('"aria-valuemin": 1', '"aria-valuemax": n', '"aria-valuenow": n', '"aria-valuetext": reading(s, n - 1)'):
        assert part in js, part
    # each arrow key moves the value, and the day and its close are what it says; leaving the chart puts it back to the latest close
    assert 'function say(i) { svg.setAttribute("aria-valuenow", i + 1); svg.setAttribute("aria-valuetext", reading(s, i)); }' in js
    assert "      say(i);\n" in js and "state.at = -1; say(n - 1); }" in js
    # the arrow keys are not also written to the polite region (the slider's value is said already: twice would be spoken twice)
    assert "announce" not in js
    # a range switch says what the new range shows, once
    assert 'live.textContent = chg.textContent + note.textContent' in js


def test_the_pages_style_keeps_taps_44px_and_stills_motion_for_people_who_ask():
    css = stock_pages.STYLE
    assert "nav.links[data-az] a{min-width:44px" in css                      # the A to Z letters were 40px wide
    assert "footer.site nav a{padding:12px 0;min-height:44px;min-width:44px}" in css      # "Blog" and "Plans" in the footer were 28 and 35px wide
    assert "@media (prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important;animation:none!important;scroll-behavior:auto!important}}" in css
    assert "main:focus,[data-ads]:focus{outline:none}" in css                # a section the page puts focus on is not a control: no ring round all of it
