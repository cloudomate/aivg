"""Sentence segmentation for streaming spoken replies — stdlib only.

Constitution I (NON-NEGOTIABLE): this is **text chunking + ordering** only.
It performs NO ASR, NO TTS, NO agent reasoning, and is NOT a VAD / endpoint
detector (Hermes owns authoritative endpointing). It exists so the reply can
be spoken sentence-by-sentence; each unit's audio is still produced by Hermes
TTS through the existing bridge seam.

Deterministic and dependency-free so it is the locally unit-testable slice of
feature 006 (mirrors feature 005's ``media.py``); the streaming pipeline and
real audio are host-proven (constitution V).
"""

from __future__ import annotations

import re
from typing import List

# Tunables (research D5). Conservative defaults; adjustable without contract
# change. MIN_CHARS avoids choppy one-word audio; MAX_CHARS lets a punctuation-
# less run-on still start playing early instead of waiting for the whole reply.
MIN_CHARS = 12
MAX_CHARS = 200

# Short tokens that end in '.' but do NOT end a sentence.
_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "no", "inc",
    "ltd", "co", "etc", "e.g", "i.e", "a.m", "p.m", "u.s", "u.k", "fig",
    "approx", "dept", "est", "min", "max", "vol", "p", "pp",
}

# Sentence-ending punctuation followed by whitespace/EOL is a candidate split.
_BOUNDARY = re.compile(r"([.?!]+)(\s+|$)")


def _last_token(text: str) -> str:
    """The whitespace-delimited token ending at the candidate '.' (lowered,
    trailing punctuation stripped) — used for the abbreviation guard."""
    seg = text.rstrip()
    if not seg:
        return ""
    tok = seg.split()[-1]
    return tok.rstrip(".?!").lower()


def _raw_sentences(text: str) -> List[str]:
    """First pass: split on sentence punctuation + newlines, honouring the
    decimal guard (3.14) and the abbreviation guard (e.g., Mr.)."""
    out: List[str] = []
    buf: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        buf.append(ch)
        if ch == "\n":
            out.append("".join(buf))
            buf = []
            i += 1
            continue
        if ch in ".?!":
            run = ch
            j = i + 1
            while j < n and text[j] in ".?!":
                run += text[j]
                buf.append(text[j])
                j += 1
            after = text[j] if j < n else ""
            before = text[i - 1] if i > 0 else ""
            is_decimal = (
                ch == "." and len(run) == 1 and before.isdigit() and after.isdigit()
            )
            is_abbrev = (
                ch == "." and len(run) == 1
                and _last_token("".join(buf)[:-1]) in _ABBREV
            )
            ends = (after == "" or after.isspace())
            if ends and not is_decimal and not is_abbrev:
                out.append("".join(buf))
                buf = []
            i = j
            continue
        i += 1
    if buf:
        out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


def _hard_split(unit: str) -> List[str]:
    """Split a boundary-less run-on into <=MAX_CHARS pieces at the last space
    before the cap so playback can begin without the whole reply."""
    if len(unit) <= MAX_CHARS:
        return [unit]
    pieces: List[str] = []
    rest = unit
    while len(rest) > MAX_CHARS:
        cut = rest.rfind(" ", 0, MAX_CHARS)
        if cut <= 0:
            cut = MAX_CHARS
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return [p for p in pieces if p]


def iter_sentences(text: str) -> List[str]:
    """Segment ``text`` into ordered speakable units.

    - splits on sentence punctuation / newlines (decimal + abbreviation safe)
    - merges a sub-``MIN_CHARS`` unit into the following one (no choppy audio);
      a trailing short fragment merges into the previous unit
    - hard-splits a punctuation-less run-on at ``MAX_CHARS``
    - preserves all non-whitespace text in order
    - empty / whitespace-only input → ``[]``
    """
    if not text or not text.strip():
        return []

    raw: List[str] = []
    for s in _raw_sentences(text):
        raw.extend(_hard_split(s))

    merged: List[str] = []
    for s in raw:
        if merged and len(merged[-1]) < MIN_CHARS:
            merged[-1] = f"{merged[-1]} {s}"
        else:
            merged.append(s)
    # A trailing too-short fragment joins the previous unit.
    if len(merged) >= 2 and len(merged[-1]) < MIN_CHARS:
        tail = merged.pop()
        merged[-1] = f"{merged[-1]} {tail}"
    return merged
