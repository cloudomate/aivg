"""Unit tests for ``streamasm.IncrementalUnitAssembler`` (feature 007).

The locally-provable slice of FR-001/FR-003 + the U1 immutable-prefix /
retraction invariant. Streaming wiring, the Hermes interrupt, and real agent
output are host-only / host-proven (constitution V) and NOT exercised here.

Contracts A1–A5 (specs/007-live-agent-streaming/contracts/
streaming-conversation.md).
"""

from aivg_core.webrtc.streamasm import IncrementalUnitAssembler
from aivg_core.webrtc.textseg import iter_sentences


def _drip_cumulative(text: str):
    """Feed ``text`` one character at a time as a growing cumulative draft;
    return every unit emitted (in order)."""
    a = IncrementalUnitAssembler()
    out: list[str] = []
    for i in range(1, len(text) + 1):
        out.extend(a.push(text[:i]))
    out.extend(a.flush())
    return out


# --- A1: only newly-complete units; partial tail buffered -----------------

def test_complete_unit_emitted_partial_buffered():
    a = IncrementalUnitAssembler()
    assert a.push("The quick brown fox jumps. The lazy") == [
        "The quick brown fox jumps."
    ]
    # The trailing "The lazy" has no boundary yet → buffered, not returned.
    assert a.push("The quick brown fox jumps. The lazy dog is") == []
    assert a.push("The quick brown fox jumps. The lazy dog is asleep. ") == [
        "The lazy dog is asleep."
    ]


# --- A2: cumulative never re-emits; no duplicates --------------------------

def test_cumulative_growth_no_duplicates():
    a = IncrementalUnitAssembler()
    seen: list[str] = []
    seen += a.push("First full sentence here. ")
    seen += a.push("First full sentence here. Second full sentence here. ")
    seen += a.push(
        "First full sentence here. Second full sentence here. Third one too. "
    )
    assert seen == [
        "First full sentence here.",
        "Second full sentence here.",
        "Third one too.",
    ]
    assert seen == sorted(set(seen), key=seen.index)  # no dup, order kept


# --- A2: append/delta input equivalent to cumulative ----------------------

def test_append_delta_equivalent_to_cumulative():
    full = "Sentence number one is here. Second sentence follows here. Done now okay."
    cumulative = _drip_cumulative(full)

    a = IncrementalUnitAssembler()
    deltas = [
        "Sentence number one is here. ",
        "Second sentence follows here. ",
        "Done now okay.",
    ]
    delta_out: list[str] = []
    for d in deltas:
        delta_out.extend(a.push(d))
    delta_out.extend(a.flush())

    assert delta_out == cumulative == iter_sentences(full)


# --- A3: no finalized non-whitespace text lost; order preserved -----------

def test_lossless_and_ordered_vs_whole_segmentation():
    full = (
        "Sentence number one is here. Sentence number two follows. "
        "Third sentence ends it."
    )
    assert _drip_cumulative(full) == iter_sentences(full)


# --- A4: flush remainder + idempotent + empty -----------------------------

def test_flush_returns_remainder_then_idempotent():
    a = IncrementalUnitAssembler()
    assert a.push("Buffered words without any terminator yet") == []
    assert a.flush() == ["Buffered words without any terminator yet"]
    assert a.flush() == []  # idempotent
    assert a.push("ignored after finalize. ") == []  # closed


def test_empty_and_whitespace_yield_nothing():
    a = IncrementalUnitAssembler()
    assert a.push("") == []
    assert a.push("   ") == []
    assert a.push("\n  \t ") == []
    assert a.flush() == []
    assert a.flush() == []


def test_flush_with_final_text_extends_not_unsays():
    a = IncrementalUnitAssembler()
    assert a.push("Intro sentence here. Tail without") == [
        "Intro sentence here."
    ]
    assert a.flush(final_text="Intro sentence here. Tail without an end") == [
        "Tail without an end"
    ]
    assert a.flush() == []


# --- U1: immutable prefix — never un-say / re-emit a returned unit ---------

def test_revised_tail_accepted_spoken_prefix_never_reemitted():
    a = IncrementalUnitAssembler()
    assert a.push("All systems are nominal. Proceeding to") == [
        "All systems are nominal."
    ]
    # Source retracts the un-spoken tail and replaces it — allowed, but the
    # already-spoken first unit is NOT re-emitted.
    assert a.push("All systems are nominal. Aborting the launch now.") == []
    assert a.flush() == ["Aborting the launch now."]


def test_shorter_retraction_of_spoken_text_is_ignored():
    a = IncrementalUnitAssembler()
    assert a.push("This is a complete sentence here. ") == [
        "This is a complete sentence here."
    ]
    # A draft shorter than what was already spoken cannot un-say it.
    assert a.push("This is") == []
    assert a.flush() == []


# --- partial-token safety: decimals & abbreviations mid-stream ------------

def test_decimal_not_split_midstream():
    a = IncrementalUnitAssembler()
    assert a.push("The value is 3.") == []          # ambiguous tail buffered
    assert a.push("The value is 3.14 exactly here. ") == [
        "The value is 3.14 exactly here."
    ]


def test_abbreviation_not_split_midstream():
    a = IncrementalUnitAssembler()
    assert a.push("Please ask Dr. ") == []          # "Dr." is not a boundary
    assert a.push("Please ask Dr. Smith about this now. ") == [
        "Please ask Dr. Smith about this now."
    ]


def test_newline_is_a_hard_boundary():
    a = IncrementalUnitAssembler()
    assert a.push("First line with enough text\nsecond line buffered") == [
        "First line with enough text"
    ]
    assert a.flush() == ["second line buffered"]
