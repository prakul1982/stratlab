"""Round 51: an AI comparison never stops mid-sentence."""
from app.intel.grounding import whole_sentences


def test_a_read_cut_by_a_cap_or_the_model_ends_at_a_sentence():
    assert whole_sentences("Reliance grew 9.7% in FY26. Reliance uses Jun 2026 vs Jun 2025, while TCS uses Sep 2026", 700) == "Reliance grew 9.7% in FY26."
    assert whole_sentences("A is 2.5x B. C is fine.", 700) == "A is 2.5x B. C is fine."
    long = "One. " * 200
    out = whole_sentences(long, 700)
    assert len(out) <= 700 and out.endswith(".")
    assert whole_sentences("no ending at all", 700) == ""
