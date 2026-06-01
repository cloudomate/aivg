"""Strip markdown formatting and emoji/smileys before TTS synthesis.

Reply text from upstream LLMs frequently contains markdown (`**bold**`,
backtick code, headers, links) and emoji/ASCII smileys. Most TTS engines
either literally pronounce the punctuation ("asterisk bold asterisk") or
produce 0-frame audio for codepoints they can't render. Spec 009 deferred
to Hermes's own ``_strip_markdown_for_tts`` and explicitly excluded emoji
handling — this module is the small post-pass that catches both, applied
between the Hermes strip and the synthesis call (`platforms/hermes/bridge.py`).

Pure stdlib. Idempotent: f(f(x)) == f(x).
"""

from __future__ import annotations

import os
import re

# Runtime toggle. Default ON. Sources of truth (lowest → highest priority):
#   1. module default (True)
#   2. SatelliteAdapterConfig.tts_text_filter — pushed in via set_enabled()
#      at adapter startup (see aivg_core/adapter.py).
#   3. AIVG_DISABLE_TTS_TEXT_FILTER=1 — env-var hard-override so an operator
#      can flip behaviour on a running host without editing config.
_enabled: bool = True


def set_enabled(value: bool) -> None:
    """Push the configured value (typically from SatelliteAdapterConfig)."""
    global _enabled
    _enabled = bool(value)


def is_enabled() -> bool:
    """Effective state: env-var override beats the configured value."""
    raw = os.environ.get("AIVG_DISABLE_TTS_TEXT_FILTER", "")
    if raw and raw not in ("0", "false", "False", "no"):
        return False
    return _enabled

# Unicode emoji ranges. Not exhaustive — covers the blocks TTS engines
# stumble over in practice (faces, hand signs, animals, food, transport,
# misc symbols, dingbats, flags, supplemental symbols, transport).
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F700-\U0001F77F"   # alchemical
    "\U0001F780-\U0001F7FF"   # geometric ext
    "\U0001F800-\U0001F8FF"   # arrows-c
    "\U0001F900-\U0001F9FF"   # supplemental symbols & pictographs
    "\U0001FA00-\U0001FA6F"   # chess / symbols & pictographs ext-a
    "\U0001FA70-\U0001FAFF"   # symbols & pictographs ext-b
    "\U00002600-\U000026FF"   # misc symbols
    "\U00002700-\U000027BF"   # dingbats
    "\U0001F1E6-\U0001F1FF"   # regional indicators (flags)
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U0000200D"              # ZWJ — emoji sequences
    "]+",
    flags=re.UNICODE,
)

# ASCII smileys / emoticons. Conservative: anchored at a word boundary or
# whitespace so we don't mangle `(a)` -> empty or eat C++ `::`. Sorted long
# tokens first so `:-)` matches before `:)`.
_SMILEY_RE = re.compile(
    r"(?<![\w])(?:"
    r":-?\)|:-?\(|:-?D|:-?P|:-?p|:-?\||:-?/|:-?\\|:-?\*|:-?o|:-?O|"
    r";-?\)|;-?D|;-?P|"
    r"X-?D|x-?D|"
    r"<3|</3|"
    r"\^_\^|\^\.\^|>_<|-_-|T_T|o_O|O_o"
    r")(?![\w])",
)

# Markdown patterns we strip. Hermes's _strip_markdown_for_tts is the
# first pass; this catches what slips through (e.g. fenced code blocks,
# images, raw URLs, headers that lost their leading newline).
_MD_FENCED_CODE = re.compile(r"```[\s\S]*?```")
_MD_INLINE_CODE = re.compile(r"`([^`]+)`")
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_AUTOLINK = re.compile(r"<((?:https?|ftp)://[^>]+)>")
_MD_BARE_URL = re.compile(r"\b(?:https?|ftp)://\S+")
_MD_BOLD_ITALIC = re.compile(r"(\*{1,3}|_{1,3})(\S(?:.*?\S)?)\1")
_MD_STRIKE = re.compile(r"~~([^~]+)~~")
_MD_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
_MD_BLOCKQUOTE = re.compile(r"(?m)^\s{0,3}>\s?")
_MD_HRULE = re.compile(r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_MD_LIST_BULLET = re.compile(r"(?m)^\s*[-*+]\s+")
_MD_LIST_NUMBER = re.compile(r"(?m)^\s*\d+[.)]\s+")
_MD_TABLE_PIPE = re.compile(r"(?m)^\s*\|.*\|\s*$")
_MD_HTML_TAG = re.compile(r"<[^<>]+>")

_WHITESPACE = re.compile(r"[ \t]+")
_NEWLINES = re.compile(r"\n{2,}")


def strip_markdown(text: str) -> str:
    """Best-effort markdown removal targeting TTS-unfriendly tokens.

    Order matters: fenced code first so its content isn't matched by
    inline rules; links before bold so the URL doesn't get scanned for
    emphasis markers.
    """
    if not text:
        return text
    text = _MD_FENCED_CODE.sub(" ", text)
    text = _MD_IMAGE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_AUTOLINK.sub(r"\1", text)
    text = _MD_BARE_URL.sub(" ", text)
    text = _MD_INLINE_CODE.sub(r"\1", text)
    text = _MD_TABLE_PIPE.sub(" ", text)
    text = _MD_HRULE.sub(" ", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BLOCKQUOTE.sub("", text)
    text = _MD_LIST_BULLET.sub("", text)
    text = _MD_LIST_NUMBER.sub("", text)
    text = _MD_STRIKE.sub(r"\1", text)
    # Bold/italic last so we don't strip emphasis markers inside links/code.
    text = _MD_BOLD_ITALIC.sub(r"\2", text)
    text = _MD_HTML_TAG.sub(" ", text)
    return text


def strip_emoji(text: str) -> str:
    """Remove Unicode emoji and ASCII smileys."""
    if not text:
        return text
    text = _EMOJI_RE.sub(" ", text)
    text = _SMILEY_RE.sub(" ", text)
    return text


def clean_for_tts(text: str) -> str:
    """Pipeline: markdown -> emoji -> whitespace collapse.

    No-ops if the filter is disabled (see ``set_enabled`` / env-var
    ``AIVG_DISABLE_TTS_TEXT_FILTER``). Returns the text with empty
    leading/trailing whitespace removed. Caller is responsible for the
    "empty after strip -> skip this unit" decision (see ``_EmptyAfterStrip``
    in the Hermes bridge).
    """
    if not text:
        return text
    if not is_enabled():
        return text
    text = strip_markdown(text)
    text = strip_emoji(text)
    text = _WHITESPACE.sub(" ", text)
    text = _NEWLINES.sub("\n", text)
    return text.strip()
