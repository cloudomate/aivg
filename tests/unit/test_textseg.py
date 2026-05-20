"""Feature 006 / US1: the locally-provable slice of FR-002 (contract S1–S7).

The streaming pipeline + real audio are host-proven (constitution V); the
deterministic sentence segmentation is fully exercised here.
"""

import pytest

from aivg_core.webrtc.textseg import MAX_CHARS, iter_sentences


def _nonws(s: str) -> str:
    return "".join(s.split())


def test_empty_and_whitespace_yield_no_units():
    assert iter_sentences("") == []
    assert iter_sentences("   \n\t  ") == []
    assert iter_sentences(None or "") == []


def test_basic_sentence_split_in_order():
    units = iter_sentences(
        "Drink water before bed. Keep the room cool and dark. "
        "Avoid screens for an hour."
    )
    assert len(units) == 3
    assert units[0].startswith("Drink water")
    assert units[1].startswith("Keep the room")
    assert units[2].startswith("Avoid screens")


def test_question_and_exclamation_are_boundaries():
    # "?" and "!" are boundaries; the sub-MIN_CHARS "Yes!" correctly merges
    # forward (no choppy one-word audio), so this yields 2 units, not 3.
    units = iter_sentences(
        "Are you really sure about that? Yes! Let us proceed onward now."
    )
    assert len(units) == 2
    assert units[0].endswith("?")
    assert "Yes!" in units[1] and units[1].endswith("now.")


def test_decimal_is_not_split():
    units = iter_sentences("The value of pi is about 3.14 in this context here.")
    assert len(units) == 1
    assert "3.14" in units[0]


@pytest.mark.parametrize("abbr", ["e.g.", "i.e.", "Mr.", "Dr.", "etc.", "vs.", "U.S."])
def test_abbreviation_does_not_end_a_sentence(abbr):
    units = iter_sentences(
        f"This applies broadly {abbr} to many similar cases in practice."
    )
    assert len(units) == 1, f"{abbr} should not split: {units}"


def test_newline_is_a_boundary():
    units = iter_sentences("First line of the reply\nSecond line of the reply")
    assert len(units) == 2


def test_short_fragment_merges_forward():
    # "OK." is < MIN_CHARS → must merge into the next unit, not be its own.
    units = iter_sentences("OK. Here is the actual detailed answer you wanted.")
    assert len(units) == 1
    assert units[0].startswith("OK.")


def test_trailing_short_fragment_merges_into_previous():
    units = iter_sentences("Here is a sufficiently long first sentence to keep. Sure.")
    assert len(units) == 1
    assert units[0].endswith("Sure.")


def test_runon_without_punctuation_is_hard_split_under_cap():
    runon = " ".join(["word"] * 200)  # ~1000 chars, no boundary
    units = iter_sentences(runon)
    assert len(units) >= 2
    assert all(len(u) <= MAX_CHARS for u in units)


def test_no_nonwhitespace_text_is_lost_or_reordered():
    text = (
        "Mr. Smith went to the U.S. on 3.14 business. Then he returned home! "
        "Was it worth it? Absolutely yes indeed."
    )
    units = iter_sentences(text)
    assert _nonws(" ".join(units)) == _nonws(text)


def test_single_short_reply_is_one_unit():
    units = iter_sentences("It is four.")
    assert units == ["It is four."]
