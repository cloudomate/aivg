"""Feature 009 — the TTS markdown-strip SEAM is wired correctly.

Locally provable slice (constitution V): we do NOT re-test Hermes's real
``_strip_markdown_for_tts`` (Hermes-owned, host-proven by the live spoken
test). We assert the WIRING in ``HermesV013Bridge.tts_synthesize``:

- the text is run through ``tools.tts_tool._strip_markdown_for_tts`` and
  its result — not the raw text — is what reaches ``text_to_speech_tool``
  (contracts H1/H2/H3, FR-001/FR-002/FR-003);
- if the strip helper is unavailable / raises, the RAW text is synthesised
  (contract H6, FR-008 — never worse than today);
- if stripping leaves nothing speakable (code-only / URL-only unit), no
  synthesis happens and the unit is skipped via a generic exception the
  callers already swallow (contract H5, FR-007 — no zero-length audio).

The lazy ``from tools.tts_tool import ...`` inside ``tts_synthesize._work``
is satisfied by a fake ``tools.tts_tool`` injected into ``sys.modules``.
"""

import json
import sys
import types
from contextlib import contextmanager

import pytest

from hermes_satellite_adapter.hermes_bridge import (
    AllProvidersUnavailable,
    HermesV013Bridge,
    SessionCtx,
    _EmptyAfterStrip,
    _UnitSynthFailed,
)

pytestmark = pytest.mark.asyncio

_CTX = SessionCtx(device_id="d", session_id="s")


@contextmanager
def _fake_tts(strip_fn, tts_fn):
    """Inject a fake ``tools.tts_tool`` (with ``_strip_markdown_for_tts``
    and ``text_to_speech_tool``) for the duration of the block, then fully
    restore ``sys.modules`` so the rest of the suite is untouched."""
    saved = {k: sys.modules.get(k) for k in ("tools", "tools.tts_tool")}
    pkg = types.ModuleType("tools")
    pkg.__path__ = []  # mark as package
    mod = types.ModuleType("tools.tts_tool")
    if strip_fn is not None:
        mod._strip_markdown_for_tts = strip_fn
    mod.text_to_speech_tool = tts_fn
    pkg.tts_tool = mod
    sys.modules["tools"] = pkg
    sys.modules["tools.tts_tool"] = mod
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _tts_writing(tmp_path, recorder):
    """A fake ``text_to_speech_tool`` that records its input and returns a
    Hermes-shaped JSON result pointing at a real wav file."""
    wav = tmp_path / "out.wav"
    wav.write_bytes(b"WAVBYTES")

    def _tts(text):
        recorder.append(text)
        return json.dumps({"success": True, "file_path": str(wav)})

    return _tts, b"WAVBYTES"


async def test_stripped_text_reaches_synth_not_raw(tmp_path):
    """H1/H2/H3 — _strip_markdown_for_tts is applied and its OUTPUT (never
    the raw text) is what text_to_speech_tool receives; bytes returned."""
    seen_strip, seen_tts = [], []

    def _strip(text):
        seen_strip.append(text)
        return "CLEAN::" + text.replace("**", "")

    tts_fn, expected = _tts_writing(tmp_path, seen_tts)
    raw = "**bold** and a [link](http://x.y/z)"

    with _fake_tts(_strip, tts_fn):
        out = await HermesV013Bridge().tts_synthesize(raw, ctx=_CTX)

    assert seen_strip == [raw]                       # strip saw the raw text
    assert seen_tts == ["CLEAN::bold and a [link](http://x.y/z)"]  # synth saw STRIPPED
    assert raw not in seen_tts                        # raw never synthesised
    assert out == expected


async def test_raw_fallback_when_strip_raises(tmp_path):
    """H6/FR-008 — if the Hermes helper raises, the RAW text is synthesised
    (never worse than today, no turn failure)."""
    seen_tts = []

    def _strip(_text):
        raise RuntimeError("boom in hermes helper")

    tts_fn, expected = _tts_writing(tmp_path, seen_tts)
    raw = "**still spoken** even if strip breaks"

    with _fake_tts(_strip, tts_fn):
        out = await HermesV013Bridge().tts_synthesize(raw, ctx=_CTX)

    assert seen_tts == [raw]      # fell back to the raw, un-stripped text
    assert out == expected


async def test_empty_after_strip_skips_without_synth(tmp_path):
    """H5/FR-007 — stripping leaves only whitespace → no synthesis, raise
    a generic _EmptyAfterStrip (NOT AllProvidersUnavailable) so the
    callers' existing per-unit ``except Exception: continue`` skips it."""
    seen_tts = []
    tts_fn, _ = _tts_writing(tmp_path, seen_tts)

    with _fake_tts(lambda _t: "   \n  ", tts_fn):
        with pytest.raises(_EmptyAfterStrip):
            await HermesV013Bridge().tts_synthesize("# \n\n", ctx=_CTX)

    assert seen_tts == []         # nothing synthesised for an empty unit


async def test_code_or_url_only_unit_is_removed_and_skipped(tmp_path):
    """US2 (FR-005/H3/H5) — a code-only / URL-only unit is fully removed by
    the reused helper (here: strip → "") so it is skipped, not spoken; no
    stand-in phrase (clarify Q4)."""
    seen_tts = []
    tts_fn, _ = _tts_writing(tmp_path, seen_tts)

    with _fake_tts(lambda _t: "", tts_fn):
        with pytest.raises(_EmptyAfterStrip):
            await HermesV013Bridge().tts_synthesize(
                "```python\nprint(1)\n```", ctx=_CTX
            )

    assert seen_tts == []


def _tts_returning(payload_obj):
    def _tts(_text):
        return json.dumps(payload_obj)
    return _tts


async def test_per_unit_render_failure_is_skippable_not_fatal():
    """REGRESSION (the "100-line story stopped after the intro" defect):
    Hermes's text_to_speech_tool CATCHES a Piper render failure and returns
    success:false. That is a per-unit failure — it MUST raise the skippable
    _UnitSynthFailed (caught by callers' `except Exception: continue`), NOT
    the fatal AllProvidersUnavailable that `agent_stream` re-raises and
    which killed the rest of the answer (FR-007)."""
    bad = _tts_returning(
        {"success": False, "error": "TTS generation failed (piper): # channels not specified"}
    )
    with _fake_tts(lambda t: t, bad):
        with pytest.raises(_UnitSynthFailed):
            await HermesV013Bridge().tts_synthesize("line 42.", ctx=_CTX)
        # and it must NOT be the fatal type
        with pytest.raises(_UnitSynthFailed):
            try:
                await HermesV013Bridge().tts_synthesize("line 42.", ctx=_CTX)
            except AllProvidersUnavailable:  # pragma: no cover - must not happen
                pytest.fail("per-unit render failure misclassified as fatal")


async def test_genuine_provider_outage_is_still_fatal():
    """FR-008 — a real provider/dependency outage stays
    AllProvidersUnavailable so the turn fails perceptibly (not silent)."""
    outage = _tts_returning(
        {"success": False, "error": "Piper provider selected but 'piper-tts' package not installed"}
    )
    with _fake_tts(lambda t: t, outage):
        with pytest.raises(AllProvidersUnavailable):
            await HermesV013Bridge().tts_synthesize("hello there.", ctx=_CTX)
