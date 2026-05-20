"""Incremental speakable-unit assembly for end-to-end streaming — stdlib only.

Constitution I (NON-NEGOTIABLE): this is **text accumulation + ordering**
only. It performs NO ASR, NO TTS, NO agent reasoning, and is NOT a VAD /
endpoint detector. It turns a sequence of streaming reply updates (the growing
agent draft) into ordered, COMPLETE speakable units as soon as each is final,
buffering an incomplete trailing sentence until more text arrives or the reply
is finalized. Each unit's audio is still produced by Hermes TTS through the
existing bridge seam (feature 006 pipeline).

Deterministic and dependency-free so it is the locally unit-testable slice of
feature 007 (mirrors feature 005 ``media.py`` / feature 006 ``textseg.py``);
the draft-streaming hook wiring, the Hermes interrupt, and real agent
streaming are host-only and host-proven (constitution V).

Contract: ``specs/007-live-agent-streaming/contracts/streaming-conversation.md``
(A1–A5); data-model ``IncrementalUnitAssembler``.
"""

from __future__ import annotations

from typing import List

from .textseg import _ABBREV, _last_token, iter_sentences

__all__ = ["IncrementalUnitAssembler"]


def _stable_cut(text: str) -> int:
    """Index after the last *completed* sentence boundary in ``text``.

    ``text[:cut]`` is the **stable prefix** safe to segment into final units;
    ``text[cut:]`` is an in-progress tail that must be buffered (FR-003 — no
    half-sentence audio). Boundary detection mirrors
    ``textseg._raw_sentences`` (decimal guard ``3.14``; abbreviation guard
    ``e.g.``; ``\\n`` is a hard boundary) with ONE deliberate difference: a
    sentence-final ``.?!`` is "complete" only when followed by real
    whitespace, never at end-of-string — a token sitting at the very end of
    the current draft may still be mid-emission (``"... 3."`` → ``"... 3.14"``),
    so it stays buffered until the next update or ``flush()`` proves it final.
    """
    cut = 0
    sent_start = 0  # start of the current in-progress sentence
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            i += 1
            cut = i
            sent_start = i
            continue
        if ch in ".?!":
            run = ch
            j = i + 1
            while j < n and text[j] in ".?!":
                run += text[j]
                j += 1
            after = text[j] if j < n else ""
            before = text[i - 1] if i > 0 else ""
            is_decimal = (
                ch == "." and len(run) == 1 and before.isdigit() and after.isdigit()
            )
            is_abbrev = (
                ch == "." and len(run) == 1
                and _last_token(text[sent_start:i]) in _ABBREV
            )
            # EOL (after == "") is NOT a completion while streaming — the
            # token may still be growing. Only whitespace after the run ends
            # the sentence.
            ends = after != "" and after.isspace()
            if ends and not is_decimal and not is_abbrev:
                cut = j
                while cut < n and text[cut].isspace():
                    cut += 1
                sent_start = cut
            i = j
            continue
        i += 1
    return cut


class IncrementalUnitAssembler:
    """Turn streaming reply updates into ordered complete speakable units.

    ``push(draft)`` accepts the latest update — either the **cumulative**
    draft so far (Hermes ``send_draft`` semantics) or an **append delta**
    (both handled: a delta that does not extend the accumulated text is
    appended) — and returns any newly-complete units not yet returned.
    ``flush()`` returns the buffered remainder once, on finalize.

    Invariants (contracts A1–A5):

    - A1 only newly-**complete** units; an incomplete trailing sentence is
      buffered, never returned.
    - A2 cumulative drafts never re-emit already-returned text; append/delta
      handled equivalently.
    - A3 order preserved; all returned units + ``flush()`` lose no finalized
      non-whitespace text and never reorder it.
    - A4 ``flush()`` returns the remainder; idempotent (2nd call → ``[]``);
      empty input anywhere → ``[]``.
    - A5 pure/deterministic, stdlib only, no STT/TTS/agent/VAD.

    Immutable prefix (spec edge "agent revises/retracts emitted text"; U1):
    once a unit has been returned it is never un-said or re-emitted. A later
    update that diverges from or is shorter than the already-consumed stable
    prefix yields nothing new — already-spoken audio cannot be unsaid; the
    assembler only ever moves forward.
    """

    __slots__ = ("_acc", "_consumed", "_done")

    def __init__(self) -> None:
        self._acc: str = ""      # reconstructed cumulative reply text
        self._consumed: int = 0  # len of the stable prefix already emitted
        self._done: bool = False

    def _absorb(self, draft: str) -> None:
        """Fold ``draft`` into the accumulated text, accepting cumulative
        snapshots OR append deltas, while never un-saying already-emitted
        (spoken) text.

        Decisions are made against the **already-consumed/spoken prefix**,
        not the full buffer, so a revision of the not-yet-spoken tail is
        accepted but a retraction of already-returned units is ignored
        (U1 / spec edge "agent revises/retracts emitted text")."""
        draft = draft or ""
        if not draft:
            return
        spoken = self._acc[:self._consumed]
        if draft.startswith(spoken):
            self._acc = draft              # valid cumulative (tail may revise)
        elif spoken.startswith(draft):
            return                         # shorter than spoken — cannot un-say
        else:
            self._acc = self._acc + draft  # append delta (extends the buffer)

    def push(self, draft: str) -> List[str]:
        """Accept the latest update; return newly-complete speakable units."""
        if self._done:
            return []
        self._absorb(draft)
        cut = _stable_cut(self._acc)
        if cut <= self._consumed:
            return []  # no new completed sentence beyond what we've emitted
        # Segment ONLY the freshly-stable region (whole sentences, since
        # _consumed and cut both sit on boundaries). This guarantees an
        # already-returned unit is never altered, re-emitted, or reordered
        # even though textseg may retro-merge a short trailing fragment.
        region = self._acc[self._consumed:cut]
        self._consumed = cut
        return iter_sentences(region)

    def flush(self, final_text: "str | None" = None) -> List[str]:
        """Finalize: return the buffered remainder as the last unit(s).

        Idempotent — a second (or late duplicate) finalize returns ``[]``.
        ``final_text`` (the full reply from the finalizing ``send()``) is
        used when it extends what was already consumed; it can only add
        text, never un-say an already-returned unit.
        """
        if self._done:
            return []
        self._done = True
        if final_text:
            self._absorb(final_text)
        remainder = self._acc[self._consumed:]
        self._consumed = len(self._acc)
        return iter_sentences(remainder)
